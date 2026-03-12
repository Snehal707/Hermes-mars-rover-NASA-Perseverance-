"""
Shared rover telemetry helpers.

These helpers prefer the bridge HTTP snapshot so dashboard/API/tool reads
converge on the same rover state. Direct gz topic parsing remains as fallback.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import urllib.error
import urllib.request

ODOM_TOPIC = "/rover/odometry"
IMU_TOPIC = "/rover/imu"
LIDAR_TOPIC = "/rover/lidar"


def _bridge_url() -> str:
    return os.environ.get("BRIDGE_URL", "http://localhost:8765").rstrip("/")


def read_topic(topic: str, timeout_sec: float = 3) -> str:
    try:
        result = subprocess.run(
            ["gz", "topic", "-e", "-t", topic, "-n", "1"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if result.returncode != 0:
            return result.stderr or result.stdout or ""
        return result.stdout or ""
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return ""


def parse_odom(raw: str) -> tuple[dict, dict]:
    pos = {"x": 0.0, "y": 0.0, "z": 0.0}
    vel = {"linear": 0.0, "angular": 0.0}
    if not raw:
        return pos, vel

    match = re.search(
        r"position\s*\{\s*x:\s*([\d.e+-]+)\s*y:\s*([\d.e+-]+)\s*z:\s*([\d.e+-]+)",
        raw,
        re.I | re.S,
    )
    if match:
        pos["x"], pos["y"], pos["z"] = float(match.group(1)), float(match.group(2)), float(match.group(3))
    else:
        partial = re.search(r"position\s*\{\s*x:\s*([\d.e+-]+)\s*y:\s*([\d.e+-]+)", raw, re.I | re.S)
        if partial:
            pos["x"], pos["y"] = float(partial.group(1)), float(partial.group(2))

    linear_match = re.search(r"linear\s*\{\s*x:\s*([\d.e+-]+)", raw, re.I | re.S)
    if linear_match:
        vel["linear"] = float(linear_match.group(1))
    angular_match = re.search(r"angular\s*\{\s*z:\s*([\d.e+-]+)", raw, re.I | re.S)
    if angular_match:
        vel["angular"] = float(angular_match.group(1))
    return pos, vel


def quat_to_rpy(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sinp = 2 * (w * y - z * x)
    pitch = math.asin(max(-1, min(1, sinp)))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def parse_imu(raw: str) -> tuple[dict, bool]:
    orient = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
    hazard = False
    if not raw:
        return orient, hazard

    block_match = re.search(r"orientation\s*\{([^}]*)\}", raw, re.I | re.S)
    if not block_match:
        return orient, hazard

    block = block_match.group(1)
    mx = re.search(r"\bx:\s*([\d.e+-]+)", block)
    my = re.search(r"\by:\s*([\d.e+-]+)", block)
    mz = re.search(r"\bz:\s*([\d.e+-]+)", block)
    mw = re.search(r"\bw:\s*([\d.e+-]+)", block)
    x = float(mx.group(1)) if mx else 0.0
    y = float(my.group(1)) if my else 0.0
    z = float(mz.group(1)) if mz else 0.0
    w = float(mw.group(1)) if mw else 1.0
    orient["roll"], orient["pitch"], orient["yaw"] = quat_to_rpy(x, y, z, w)
    tilt = math.acos(max(-1, min(1, 1 - 2 * (x * x + y * y))))
    hazard = tilt > 0.35
    return orient, hazard


def fetch_bridge_telemetry(timeout_sec: float = 1.5) -> dict | None:
    req = urllib.request.Request(
        f"{_bridge_url()}/",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict) or "position" not in payload:
        return None
    out = dict(payload)
    out["source"] = "bridge"
    return out


def direct_telemetry_snapshot() -> dict:
    odom_raw = read_topic(ODOM_TOPIC)
    imu_raw = read_topic(IMU_TOPIC)
    position, velocity = parse_odom(odom_raw)
    orientation, hazard = parse_imu(imu_raw)
    return {
        "position": position,
        "orientation": orientation,
        "velocity": velocity,
        "hazard_detected": hazard,
        "uptime_seconds": 0.0,
        "sim_connected": bool(odom_raw or imu_raw),
        "source": "gz",
    }


def get_telemetry_snapshot(prefer_bridge: bool = True, timeout_sec: float = 1.5) -> dict:
    if prefer_bridge:
        bridge = fetch_bridge_telemetry(timeout_sec=timeout_sec)
        if bridge is not None:
            return bridge
    return direct_telemetry_snapshot()


def distance_from_origin(position: dict | None) -> float:
    if not isinstance(position, dict):
        return 0.0
    try:
        x = float(position.get("x", 0.0))
        y = float(position.get("y", 0.0))
        z = float(position.get("z", 0.0))
    except Exception:
        return 0.0
    return math.sqrt(x * x + y * y + z * z)
