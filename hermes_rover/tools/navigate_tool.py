"""
Headless navigate tool: read odometry, drive in steps toward target, check sensors for hazards.
"""
import asyncio
import json
import math
import os
import re
import subprocess
import time

from hermes_rover.telemetry import LIDAR_TOPIC, distance_from_origin, get_telemetry_snapshot, read_topic

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

CMD_VEL_TOPIC = "/rover/cmd_vel"
ARRIVAL_DIST = 0.5
TURN_TOLERANCE_RAD = 0.18
LINEAR_STEP = 0.45
LINEAR_STEP_DURATION = 1.0
TURN_RATE = 0.35
TURN_STEP_MAX_DURATION = 1.2
POST_MOVE_SETTLE_SEC = 0.55
HAZARD_LIDAR_MIN = 1.0
PUBLISH_HZ = 10.0
STALL_STEP_LIMIT = max(4, int(os.environ.get("HERMES_NAV_STALL_STEPS", "8")))
STALL_PROGRESS_EPSILON = float(os.environ.get("HERMES_NAV_STALL_EPSILON_M", "0.08"))
NAV_TIMEOUT_SEC = max(15.0, float(os.environ.get("HERMES_NAV_TIMEOUT_SEC", "120")))
# Rover forward axis in the current Gazebo model points along -Y when yaw == 0.
FORWARD_AXIS_OFFSET_RAD = -math.pi / 2.0


def _normalize_angle(angle: float) -> float:
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


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


def _hazard_from_lidar(raw: str) -> bool:
    ranges = re.findall(r"range\s*:\s*([\d.e+-]+)|ranges\s*\[([\d.e+-]+)\]", raw)
    if not ranges:
        return False
    for r in ranges:
        val = float((r[0] or r[1]).strip())
        if 0.01 < val < HAZARD_LIDAR_MIN:
            return True
    return False


def _position_xy(snapshot: dict) -> tuple[float, float]:
    position = snapshot.get("position", {}) if isinstance(snapshot, dict) else {}
    return (
        float(position.get("x", 0.0)),
        float(position.get("y", 0.0)),
    )


def _yaw(snapshot: dict) -> float:
    orientation = snapshot.get("orientation", {}) if isinstance(snapshot, dict) else {}
    return float(orientation.get("yaw", 0.0))


async def execute(*, target_x: float, target_y: float, **_) -> str:
    try:
        started_at = time.monotonic()
        snapshot = get_telemetry_snapshot(prefer_bridge=True)
        x, y = _position_xy(snapshot)
        dist = math.hypot(target_x - x, target_y - y)
        if dist <= ARRIVAL_DIST:
            return json.dumps({
                "status": "ok",
                "message": "already at target",
                "position": {"x": round(x, 3), "y": round(y, 3)},
                "target": {"x": target_x, "y": target_y},
                "telemetry_source": snapshot.get("source", "gz"),
                "distance_from_origin": round(distance_from_origin(snapshot.get("position")), 3),
            })

        steps = 0
        best_dist = dist
        stalled_steps = 0
        max_steps = max(80, int(dist / max(0.1, LINEAR_STEP * LINEAR_STEP_DURATION)) * 4 + 8)
        while dist > ARRIVAL_DIST and steps < max_steps:
            snapshot = get_telemetry_snapshot(prefer_bridge=True)
            x, y = _position_xy(snapshot)
            current_yaw = _yaw(snapshot)
            current_heading = _normalize_angle(current_yaw + FORWARD_AXIS_OFFSET_RAD)
            target_heading = math.atan2(target_y - y, target_x - x)
            heading_error = _normalize_angle(target_heading - current_heading)

            if abs(heading_error) > TURN_TOLERANCE_RAD:
                turn_duration = min(
                    TURN_STEP_MAX_DURATION,
                    max(0.25, abs(heading_error) / max(0.01, TURN_RATE)),
                )
                turn_rate = TURN_RATE if heading_error > 0 else -TURN_RATE
                await _publish_for_duration(0.0, turn_rate, turn_duration, PUBLISH_HZ)
                await _publish_stop_burst()
                await asyncio.sleep(POST_MOVE_SETTLE_SEC)
            else:
                drive_duration = min(
                    LINEAR_STEP_DURATION,
                    max(0.3, dist / max(0.05, LINEAR_STEP)),
                )
                await _publish_for_duration(LINEAR_STEP, 0.0, drive_duration, PUBLISH_HZ)
                await _publish_stop_burst()
                await asyncio.sleep(POST_MOVE_SETTLE_SEC)

            snapshot = get_telemetry_snapshot(prefer_bridge=True)
            x, y = _position_xy(snapshot)
            dist = math.hypot(target_x - x, target_y - y)

            if dist < (best_dist - STALL_PROGRESS_EPSILON):
                best_dist = dist
                stalled_steps = 0
            else:
                stalled_steps += 1

            if bool(snapshot.get("hazard_detected", False)):
                return json.dumps({
                    "status": "hazard_stop",
                    "message": "tilt hazard",
                    "position": {"x": round(x, 3), "y": round(y, 3)},
                    "target": {"x": target_x, "y": target_y},
                    "steps": steps,
                    "telemetry_source": snapshot.get("source", "gz"),
                    "distance_from_origin": round(distance_from_origin(snapshot.get("position")), 3),
                })
            lidar_raw = read_topic(LIDAR_TOPIC, timeout_sec=2)
            if lidar_raw and _hazard_from_lidar(lidar_raw):
                return json.dumps({
                    "status": "hazard_stop",
                    "message": "obstacle in lidar",
                    "position": {"x": round(x, 3), "y": round(y, 3)},
                    "target": {"x": target_x, "y": target_y},
                    "steps": steps,
                    "telemetry_source": snapshot.get("source", "gz"),
                    "distance_from_origin": round(distance_from_origin(snapshot.get("position")), 3),
                })
            if stalled_steps >= STALL_STEP_LIMIT:
                return json.dumps({
                    "status": "error",
                    "message": "navigation stalled",
                    "position": {"x": round(x, 3), "y": round(y, 3)},
                    "target": {"x": target_x, "y": target_y},
                    "steps": steps,
                    "distance_remaining": round(dist, 3),
                    "telemetry_source": snapshot.get("source", "gz"),
                    "distance_from_origin": round(distance_from_origin(snapshot.get("position")), 3),
                })
            if (time.monotonic() - started_at) >= NAV_TIMEOUT_SEC:
                return json.dumps({
                    "status": "error",
                    "message": "navigation timeout",
                    "position": {"x": round(x, 3), "y": round(y, 3)},
                    "target": {"x": target_x, "y": target_y},
                    "steps": steps,
                    "distance_remaining": round(dist, 3),
                    "telemetry_source": snapshot.get("source", "gz"),
                    "distance_from_origin": round(distance_from_origin(snapshot.get("position")), 3),
                })
            steps += 1

        snapshot = get_telemetry_snapshot(prefer_bridge=True)
        x, y = _position_xy(snapshot)
        dist = math.hypot(target_x - x, target_y - y)
        return json.dumps({
            "status": "ok",
            "position": {"x": round(x, 3), "y": round(y, 3)},
            "target": {"x": target_x, "y": target_y},
            "distance_remaining": round(dist, 3),
            "steps": steps,
            "telemetry_source": snapshot.get("source", "gz"),
            "distance_from_origin": round(distance_from_origin(snapshot.get("position")), 3),
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "message": "gz topic timeout"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
