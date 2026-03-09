"""
Headless sensor tool: read IMU, odometry, lidar via gz topic -e -t TOPIC -n 1.
"""
import json
import subprocess

TOOL_SCHEMA = {
    "name": "read_sensors",
    "description": "Read rover sensors (imu, odometry, lidar) via gz topic (headless).",
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
    "odometry": "/rover/odometry",
    "imu": "/world/mars_surface/model/perseverance/link/base_link/sensor/imu/imu",
    "lidar": "/rover/lidar",
}


def _read_topic(topic: str, timeout_sec: float = 3) -> str:
    result = subprocess.run(
        ["gz", "topic", "-e", "-t", topic, "-n", "1"],
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if result.returncode != 0:
        return result.stderr or result.stdout or ""
    return result.stdout or ""


async def execute(*, sensors: list, **_) -> str:
    if not sensors:
        return json.dumps({"status": "ok", "readings": {}})
    readings = {}
    for s in sensors:
        name = s if isinstance(s, str) else str(s)
        name = name.lower().strip()
        if name not in SENSOR_TOPICS:
            readings[name] = {"error": "unknown sensor"}
            continue
        topic = SENSOR_TOPICS[name]
        try:
            raw = _read_topic(topic)
            readings[name] = {"topic": topic, "raw": raw.strip()[:2000]}
        except subprocess.TimeoutExpired:
            readings[name] = {"topic": topic, "error": "timeout"}
        except Exception as e:
            readings[name] = {"topic": topic, "error": str(e)}
    return json.dumps({"status": "ok", "readings": readings})
