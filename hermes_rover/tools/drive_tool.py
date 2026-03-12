"""
Headless drive tool: publish Twist to /rover/cmd_vel via gz topic.
"""
import asyncio
import json
import subprocess
import time

from hermes_rover.telemetry import distance_from_origin, get_telemetry_snapshot

TOOL_SCHEMA = {
    "name": "drive_rover",
    "description": "Drive the rover with given linear and angular speed for a duration (headless, via gz topic).",
    "parameters": {
        "type": "object",
        "properties": {
            "linear_speed": {"type": "number", "description": "Forward speed (-1 to 1)."},
            "angular_speed": {"type": "number", "description": "Turn rate (-0.5 to 0.5).", "default": 0},
            "duration": {"type": "number", "description": "Seconds to drive before stopping.", "default": 2},
        },
        "required": ["linear_speed"],
    },
}

CMD_VEL_TOPIC = "/rover/cmd_vel"


def _publish_twist(linear_x: float, angular_z: float) -> None:
    payload = f"linear: {{x: {linear_x}, y: 0, z: 0}}, angular: {{x: 0, y: 0, z: {angular_z}}}"
    subprocess.run(
        ["gz", "topic", "-t", CMD_VEL_TOPIC, "-m", "gz.msgs.Twist", "-p", payload],
        capture_output=True,
        timeout=5,
    )


def _publish_for_duration(linear_x: float, angular_z: float, duration: float, hz: float = 10.0) -> None:
    """Publish cmd_vel repeatedly so Gazebo subscribers reliably receive commands."""
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


async def execute(
    *,
    linear_speed: float,
    angular_speed: float = 0,
    duration: float = 2,
    **_,
) -> str:
    linear = max(-1.0, min(1.0, float(linear_speed)))
    angular = max(-0.5, min(0.5, float(angular_speed)))
    duration = max(0.1, float(duration))

    try:
        await asyncio.to_thread(_publish_for_duration, linear, angular, duration, 10.0)
        await asyncio.to_thread(_publish_stop_burst)
        distance_estimate = abs(linear) * duration * 0.5  # rough m at low speed
        final_telemetry = get_telemetry_snapshot(prefer_bridge=True)
        return json.dumps({
            "status": "ok",
            "linear_speed": linear,
            "angular_speed": angular,
            "duration_s": duration,
            "distance_estimate_m": round(distance_estimate, 2),
            "telemetry_source": final_telemetry.get("source", "gz"),
            "position": final_telemetry.get("position", {}),
            "distance_from_origin": round(distance_from_origin(final_telemetry.get("position")), 3),
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"status": "error", "message": "gz topic timeout"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
