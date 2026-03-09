"""
Check rover hazards (tilt, storm) via bridge GET / and HazardDetector.
"""
import json
import os

from hermes_rover.hazard_detector import HazardDetector

TOOL_SCHEMA = {
    "name": "check_hazards",
    "description": "Check rover hazards: tilt (from IMU), dust storm. Returns hazard list and recommended actions.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}


async def execute(**kwargs) -> str:
    bridge_url = os.environ.get("BRIDGE_URL", "http://localhost:8765")
    detector = HazardDetector(bridge_url=bridge_url)
    hazards = await detector.get_all_hazards()
    actions = []
    for h in hazards:
        actions.append(h.get("action", "Stop and assess."))
    return json.dumps({
        "hazards": hazards,
        "recommended_actions": actions if actions else ["No hazards detected. Safe to proceed."],
    })
