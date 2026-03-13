"""
Headless sensor bridge: polls gz topics (odometry, IMU) every 500ms, exposes HTTP API.
No rclpy; subprocess gz topic only. Port 8765.
"""
from concurrent.futures import ThreadPoolExecutor
import math
import os
import re
import subprocess
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

ODOM_TOPIC = "/rover/odometry"
IMU_TOPIC = "/rover/imu"
CMD_VEL_TOPIC = "/rover/cmd_vel"
WORLD_NAME = os.environ.get("HERMES_GZ_WORLD_NAME", "mars_surface")
STATS_TOPIC = f"/world/{WORLD_NAME}/stats"
POLL_INTERVAL = float(os.environ.get("HERMES_BRIDGE_POLL_INTERVAL_SEC", "0.5"))
HAZARD_TILT_RAD = 0.35
TOPIC_TIMEOUT_SEC = float(os.environ.get("HERMES_BRIDGE_TOPIC_TIMEOUT_SEC", "2.0"))
SIM_CONNECTED_GRACE_SEC = float(os.environ.get("HERMES_BRIDGE_SIM_GRACE_SEC", "6.0"))
_TOPIC_POOL = ThreadPoolExecutor(max_workers=3)

_state_lock = threading.Lock()
_state = {
    "position": {"x": 0.0, "y": 0.0, "z": 0.0},
    "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
    "velocity": {"linear": 0.0, "angular": 0.0},
    "hazard_detected": False,
    "uptime_seconds": 0.0,
    "sim_connected": False,
    "_start_time": None,
    "_last_ok_time": 0.0,
}


def _read_topic(topic: str, timeout_sec: float = TOPIC_TIMEOUT_SEC) -> str:
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-t", topic, "-n", "1"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return (result.stdout or "").strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return ""


def _parse_odom(raw: str) -> tuple[dict, dict]:
    """Return (position {x,y,z}, velocity {linear, angular})."""
    pos = {"x": 0.0, "y": 0.0, "z": 0.0}
    vel = {"linear": 0.0, "angular": 0.0}
    if not raw:
        return pos, vel
    # position { x: ... y: ... z: ... }
    m = re.search(
        r"position\s*\{\s*x:\s*([\d.e+-]+)\s*y:\s*([\d.e+-]+)\s*z:\s*([\d.e+-]+)",
        raw,
        re.I | re.S,
    )
    if m:
        pos["x"], pos["y"], pos["z"] = float(m.group(1)), float(m.group(2)), float(m.group(3))
    else:
        m2 = re.search(r"position\s*\{\s*x:\s*([\d.e+-]+)\s*y:\s*([\d.e+-]+)", raw, re.I | re.S)
        if m2:
            pos["x"], pos["y"] = float(m2.group(1)), float(m2.group(2))
    # linear { x: ... } -> use x as linear speed magnitude
    lm = re.search(r"linear\s*\{\s*x:\s*([\d.e+-]+)", raw, re.I | re.S)
    if lm:
        vel["linear"] = float(lm.group(1))
    am = re.search(r"angular\s*\{\s*z:\s*([\d.e+-]+)", raw, re.I | re.S)
    if am:
        vel["angular"] = float(am.group(1))
    return pos, vel


def _quat_to_rpy(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    """Quaternion (x,y,z,w) to roll, pitch, yaw in radians."""
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sinp = 2 * (w * y - z * x)
    pitch = math.asin(max(-1, min(1, sinp)))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def _parse_imu(raw: str) -> tuple[dict, bool]:
    """Return (orientation {roll, pitch, yaw}, hazard_detected)."""
    orient = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
    hazard = False
    if not raw:
        return orient, hazard
    # Find the "orientation {" block first
    block_match = re.search(r'orientation\s*\{([^}]*)\}', raw, re.I | re.S)
    if block_match:
        block = block_match.group(1)
        # Extract x, y, z, w only from within that block; default x,y,z to 0.0, w to 1.0
        mx = re.search(r'\bx:\s*([\d.e+-]+)', block)
        my = re.search(r'\by:\s*([\d.e+-]+)', block)
        mz = re.search(r'\bz:\s*([\d.e+-]+)', block)
        mw = re.search(r'\bw:\s*([\d.e+-]+)', block)
        x = float(mx.group(1)) if mx else 0.0
        y = float(my.group(1)) if my else 0.0
        z = float(mz.group(1)) if mz else 0.0
        w = float(mw.group(1)) if mw else 1.0
        orient["roll"], orient["pitch"], orient["yaw"] = _quat_to_rpy(x, y, z, w)
        tilt = math.acos(max(-1, min(1, 1 - 2 * (x * x + y * y))))
        hazard = tilt > HAZARD_TILT_RAD
    return orient, hazard


def _publish_twist(linear_x: float, angular_z: float) -> None:
    payload = f"linear: {{x: {linear_x}, y: 0, z: 0}}, angular: {{x: 0, y: 0, z: {angular_z}}}"
    subprocess.run(
        ["gz", "topic", "-t", CMD_VEL_TOPIC, "-m", "gz.msgs.Twist", "-p", payload],
        capture_output=True,
        timeout=5,
    )


def _publish_for_duration(linear_x: float, angular_z: float, duration: float, hz: float = 10.0) -> None:
    """Publish cmd_vel repeatedly so motion commands are not dropped."""
    duration = max(0.0, float(duration))
    hz = max(1.0, float(hz))
    interval = 1.0 / hz
    end = time.monotonic() + duration
    while time.monotonic() < end:
        _publish_twist(linear_x, angular_z)
        time.sleep(interval)


def _publish_stop_burst() -> None:
    for _ in range(3):
        _publish_twist(0.0, 0.0)
        time.sleep(0.05)


def _poll_once() -> None:
    odom_future = _TOPIC_POOL.submit(_read_topic, ODOM_TOPIC, TOPIC_TIMEOUT_SEC)
    imu_future = _TOPIC_POOL.submit(_read_topic, IMU_TOPIC, TOPIC_TIMEOUT_SEC)
    stats_future = _TOPIC_POOL.submit(_read_topic, STATS_TOPIC, TOPIC_TIMEOUT_SEC)

    odom_raw = odom_future.result()
    imu_raw = imu_future.result()
    stats_raw = stats_future.result()
    pos, vel = _parse_odom(odom_raw) if odom_raw else (None, None)
    orient, hazard = _parse_imu(imu_raw)
    any_ok = bool(odom_raw or imu_raw or stats_raw)
    cycle_now = time.monotonic()

    with _state_lock:
        if pos is not None and vel is not None:
            _state["position"] = pos
            _state["velocity"] = vel
        if imu_raw:
            _state["orientation"] = orient
            _state["hazard_detected"] = hazard
        if _state["_start_time"] is not None:
            _state["uptime_seconds"] = round(cycle_now - _state["_start_time"], 2)
        if any_ok:
            _state["_last_ok_time"] = cycle_now
        _state["sim_connected"] = (cycle_now - _state["_last_ok_time"]) < SIM_CONNECTED_GRACE_SEC


def _poller_loop() -> None:
    while True:
        _poll_once()
        time.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with _state_lock:
        _state["_start_time"] = time.monotonic()
        _state["_last_ok_time"] = 0.0
    t = threading.Thread(target=_poller_loop, daemon=True)
    t.start()
    yield
    # no shutdown join; daemon thread exits with process


app = FastAPI(title="Rover Sensor Bridge", lifespan=lifespan)


@app.get("/")
def get_state():
    """Latest position, orientation, velocity, hazard_detected, uptime_seconds."""
    with _state_lock:
        return {
            "position": dict(_state["position"]),
            "orientation": dict(_state["orientation"]),
            "velocity": dict(_state["velocity"]),
            "hazard_detected": _state["hazard_detected"],
            "uptime_seconds": _state["uptime_seconds"],
            "sim_connected": _state["sim_connected"],
        }


@app.get("/state")
def get_state_alias():
    """Backward-compatible alias for clients probing /state."""
    return get_state()


@app.get("/sensors")
def get_sensors_alias():
    """Backward-compatible alias for clients probing /sensors."""
    return get_state()


@app.get("/health")
def health():
    with _state_lock:
        sim_connected = _state["sim_connected"]
    return {"status": "ok", "sim_connected": sim_connected}


class DriveBody(BaseModel):
    linear: float
    angular: float
    duration: float


@app.post("/drive")
def drive(body: DriveBody):
    """Publish Twist for duration, then stop. Returns {status: 'completed'}."""
    linear = max(-1.0, min(1.0, float(body.linear)))
    angular = max(-0.5, min(0.5, float(body.angular)))
    duration = max(0.0, float(body.duration))
    _publish_for_duration(linear, angular, duration, hz=10.0)
    _publish_stop_burst()
    return {"status": "completed"}
