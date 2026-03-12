"""
Headless sensor tool: read IMU, odometry, lidar via gz topic -e -t TOPIC -n 1.
"""
import json

from hermes_rover.telemetry import (
    IMU_TOPIC,
    LIDAR_TOPIC,
    ODOM_TOPIC,
    get_telemetry_snapshot,
    read_topic,
)

TOOL_SCHEMA = {
    "name": "read_sensors",
    "description": "Read rover sensors (imu, odometry, lidar) with bridge-backed telemetry when available.",
    "parameters": {
        "type": "object",
        "properties": {
            "sensors": {
                "type": "array",
                "items": {"type": "string", "enum": ["imu", "odometry", "lidar"]},
                "description": "Which sensors to read.",
            },
        },
        "required": ["sensors"],
    },
}


SENSOR_TOPICS = {
    "odometry": ODOM_TOPIC,
    "imu": IMU_TOPIC,
    "lidar": LIDAR_TOPIC,
}


async def execute(*, sensors: list, **_) -> str:
    if not sensors:
        return json.dumps({"status": "ok", "readings": {}})
    readings = {}
    snapshot = get_telemetry_snapshot(prefer_bridge=True)
    source = str(snapshot.get("source") or "gz")
    for s in sensors:
        name = s if isinstance(s, str) else str(s)
        name = name.lower().strip()
        if name not in SENSOR_TOPICS:
            readings[name] = {"error": "unknown sensor"}
            continue
        topic = SENSOR_TOPICS[name]
        if name == "odometry":
            readings[name] = {
                "topic": topic,
                "source": source,
                "parsed": {
                    "position": snapshot.get("position", {}),
                    "velocity": snapshot.get("velocity", {}),
                },
            }
            continue
        if name == "imu":
            readings[name] = {
                "topic": topic,
                "source": source,
                "parsed": {
                    "orientation": snapshot.get("orientation", {}),
                    "hazard_detected": bool(snapshot.get("hazard_detected", False)),
                },
            }
            continue

        raw = read_topic(topic)
        readings[name] = {
            "topic": topic,
            "source": "gz",
            "raw": raw.strip()[:2000],
        }

    return json.dumps({
        "status": "ok",
        "telemetry_source": source,
        "telemetry": snapshot,
        "readings": readings,
    })
