"""
Headless navigate tool: read odometry, drive in steps toward target, check sensors for hazards.
"""
import asyncio
import json
import math
import re
import subprocess
import time

TOOL_SCHEMA = {
    "name": "navigate_to",
    "description": "Navigate rover to target x,y using odometry and drive in steps; stop if hazard detected.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_x": {"type": "number", "description": "Target X position (m)."},
            "target_y": {"type": "number", "description": "Target Y position (m)."},
        },
        "required": ["target_x", "target_y"],
    },
}

ODOM_TOPIC = "/rover/odometry"
CMD_VEL_TOPIC = "/rover/cmd_vel"
STEP_DURATION = 2.0
ARRIVAL_DIST = 0.5
LINEAR_STEP = 0.3
HAZARD_LIDAR_MIN = 1.0
HAZARD_TILT_RAD = 0.4
PUBLISH_HZ = 10.0
YAW_ALIGN_TOL = 0.25  # radians (~14 degrees)
YAW_TURN_RATE = 0.4  # rad/s


def _read_topic(topic: str, timeout_sec: float = 3) -> str:
    result = subprocess.run(
        ["gz", "topic", "-e", "-t", topic, "-n", "1"],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def _parse_position_from_odom(raw: str):
    x, y = 0.0, 0.0
    pos = re.search(r"position\s*\{\s*x:\s*([\d.e+-]+)\s*y:\s*([\d.e+-]+)", raw, re.I | re.S)
    if pos:
        x, y = float(pos.group(1)), float(pos.group(2))
    else:
        for m in re.finditer(r"x:\s*([\d.e+-]+)|y:\s*([\d.e+-]+)", raw):
            if m.group(1):
                x = float(m.group(1))
            if m.group(2):
                y = float(m.group(2))
    return (x, y)


def _parse_yaw_from_odom(raw: str) -> float:
    """Approximate yaw from quaternion orientation in odometry."""
    orient = re.search(
        r"orientation\s*\{[^}]*x:\s*([\d.e+-]+)[^}]*y:\s*([\d.e+-]+)[^}]*z:\s*([\d.e+-]+)[^}]*w:\s*([\d.e+-]+)",
        raw,
        re.I | re.S,
    )
    if not orient:
        return 0.0
    x = float(orient.group(1))
    y = float(orient.group(2))
    z = float(orient.group(3))
    w = float(orient.group(4))
    # Yaw from quaternion (x, y, z, w)
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


def _publish_twist(linear_x: float, angular_z: float) -> None:
    payload = f"linear: {{x: {linear_x}, y: 0, z: 0}}, angular: {{x: 0, y: 0, z: {angular_z}}}"
    subprocess.run(
        ["gz", "topic", "-t", CMD_VEL_TOPIC, "-m", "gz.msgs.Twist", "-p", payload],
        capture_output=True,
        timeout=5,
    )


async def _publish_for_duration(linear_x: float, angular_z: float, duration: float, hz: float = PUBLISH_HZ) -> None:
    duration = max(0.0, float(duration))
    hz = max(1.0, float(hz))
    interval = 1.0 / hz
    end = time.monotonic() + duration
    while time.monotonic() < end:
        _publish_twist(linear_x, angular_z)
        await asyncio.sleep(interval)


async def _publish_stop_burst() -> None:
    for _ in range(3):
        _publish_twist(0.0, 0.0)
        await asyncio.sleep(0.05)


async def _align_yaw_toward_target(x: float, y: float, target_x: float, target_y: float) -> None:
    """Rotate in place until rover faces the target within tolerance."""
    dx = target_x - x
    dy = target_y - y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return
    desired_yaw = math.atan2(dy, dx)

    raw_odom = _read_topic(ODOM_TOPIC)
    current_yaw = _parse_yaw_from_odom(raw_odom)
    diff = (desired_yaw - current_yaw + math.pi) % (2 * math.pi) - math.pi
    if abs(diff) <= YAW_ALIGN_TOL:
        return

    direction = 1.0 if diff > 0 else -1.0
    duration = min(4.0, abs(diff) / max(YAW_TURN_RATE, 1e-3))
    await _publish_for_duration(0.0, direction * YAW_TURN_RATE, duration, PUBLISH_HZ)
    await _publish_stop_burst()


def _hazard_from_lidar(raw: str) -> bool:
    ranges = re.findall(r"range\s*:\s*([\d.e+-]+)|ranges\s*\[([\d.e+-]+)\]", raw)
    if not ranges:
        return False
    for r in ranges:
        val = float((r[0] or r[1]).strip())
        if 0.01 < val < HAZARD_LIDAR_MIN:
            return True
    return False


def _hazard_from_imu(raw: str) -> bool:
    orient = re.search(r"orientation\s*\{[^}]*x:\s*([\d.e+-]+)[^}]*y:\s*([\d.e+-]+)[^}]*z:\s*([\d.e+-]+)", raw, re.I | re.S)
    if not orient:
        return False
    x, y, z = float(orient.group(1)), float(orient.group(2)), float(orient.group(3))
    tilt = math.acos(max(-1, min(1, 2 * (x * x + y * y + z * z) - 1)))
    return tilt > HAZARD_TILT_RAD


async def execute(*, target_x: float, target_y: float, **_) -> str:
    try:
        raw_odom = _read_topic(ODOM_TOPIC)
        x, y = _parse_position_from_odom(raw_odom)
        dist = math.hypot(target_x - x, target_y - y)
        if dist <= ARRIVAL_DIST:
            return json.dumps({
                "status": "ok",
                "message": "already at target",
                "position": {"x": round(x, 3), "y": round(y, 3)},
                "target": {"x": target_x, "y": target_y},
            })

        steps = 0
        max_steps = max(50, int(dist / (LINEAR_STEP * STEP_DURATION)) + 5)
        while dist > ARRIVAL_DIST and steps < max_steps:
            await _align_yaw_toward_target(x, y, target_x, target_y)
            await _publish_for_duration(LINEAR_STEP, 0.0, STEP_DURATION, PUBLISH_HZ)
            await _publish_stop_burst()
            await asyncio.sleep(0.15)

            raw_odom = _read_topic(ODOM_TOPIC)
            x, y = _parse_position_from_odom(raw_odom)
            dist = math.hypot(target_x - x, target_y - y)

            imu_raw = _read_topic("/world/mars_surface/model/perseverance/link/base_link/sensor/imu/imu", timeout_sec=2)
            if imu_raw and _hazard_from_imu(imu_raw):
                return json.dumps({
                    "status": "hazard_stop",
                    "message": "tilt hazard",
                    "position": {"x": round(x, 3), "y": round(y, 3)},
                    "target": {"x": target_x, "y": target_y},
                    "steps": steps,
                })
            lidar_raw = _read_topic("/rover/lidar", timeout_sec=2)
            if lidar_raw and _hazard_from_lidar(lidar_raw):
                return json.dumps({
                    "status": "hazard_stop",
                    "message": "obstacle in lidar",
                    "position": {"x": round(x, 3), "y": round(y, 3)},
                    "target": {"x": target_x, "y": target_y},
                    "steps": steps,
                })
            steps += 1

        return json.dumps({
            "status": "ok",
            "position": {"x": round(x, 3), "y": round(y, 3)},
            "target": {"x": target_x, "y": target_y},
            "distance_remaining": round(dist, 3),
            "steps": steps,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "message": "gz topic timeout"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
