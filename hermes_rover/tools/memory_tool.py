"""
Rover memory tool: check_area, save_discovery, recall_sessions, save_behavior, get_behaviors.
"""
import json

from hermes_rover.memory import memory_manager

memory_manager.init_db()

TOOL_SCHEMA = {
    "name": "rover_memory",
    "description": "Mars rover extended memory: check area for hazards, save discoveries, recall sessions, save/get learned behaviors.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check_area", "save_discovery", "recall_sessions", "save_behavior", "get_behaviors"],
                "description": "Action: check_area, save_discovery, recall_sessions, save_behavior, get_behaviors.",
            },
            "x": {"type": "number", "description": "X coordinate (m)."},
            "y": {"type": "number", "description": "Y coordinate (m)."},
            "radius": {"type": "number", "description": "Radius for check_area (m). Default 10."},
            "hazard_type": {"type": "string", "description": "Type of hazard (save_discovery)."},
            "terrain_type": {"type": "string", "description": "Type of terrain (save_discovery)."},
            "severity": {"type": "string", "description": "Hazard severity (save_discovery)."},
            "description": {"type": "string", "description": "Description (save_discovery)."},
            "traversability": {"type": "number", "description": "Terrain traversability 0-1 (save_discovery)."},
            "notes": {"type": "string", "description": "Notes for terrain (save_discovery)."},
            "trigger": {"type": "string", "description": "Trigger condition (save_behavior)."},
            "behavior_action": {"type": "string", "description": "Action for learned behavior (save_behavior)."},
            "session_id": {"type": "string", "description": "Session ID for save_behavior."},
        },
        "required": ["action"],
    },
}


async def execute(**kwargs) -> str:
    action = kwargs.get("action")
    if not action:
        return json.dumps({"error": "action required"})
    if action == "check_area":
        x = float(kwargs.get("x", 0))
        y = float(kwargs.get("y", 0))
        radius = float(kwargs.get("radius", 10.0))
        hazards = memory_manager.get_nearby_hazards(x, y, radius)
        terrain = memory_manager.get_nearby_terrain(x, y, radius)
        return json.dumps({"hazards": hazards, "terrain": terrain})
    if action == "save_discovery":
        x = float(kwargs.get("x", 0))
        y = float(kwargs.get("y", 0))
        if "hazard_type" in kwargs and kwargs["hazard_type"]:
            memory_manager.log_hazard(
                x=x,
                y=y,
                hazard_type=str(kwargs.get("hazard_type", "unknown")),
                severity=str(kwargs.get("severity", "medium")),
                description=str(kwargs.get("description", "")),
                session_id=str(kwargs.get("session_id", "")),
            )
            return json.dumps({"status": "ok", "saved": "hazard"})
        if "terrain_type" in kwargs and kwargs["terrain_type"]:
            memory_manager.log_terrain(
                x=x,
                y=y,
                terrain_type=str(kwargs["terrain_type"]),
                traversability=float(kwargs.get("traversability", 0.5)),
                notes=str(kwargs.get("notes", "")),
            )
            return json.dumps({"status": "ok", "saved": "terrain"})
        return json.dumps({"error": "provide hazard_type or terrain_type for save_discovery"})
    if action == "recall_sessions":
        limit = int(kwargs.get("limit", 50))
        sessions = memory_manager.get_sessions(limit=limit)
        return json.dumps({"sessions": sessions})
    if action == "save_behavior":
        trigger = str(kwargs.get("trigger", ""))
        behavior_action = str(kwargs.get("behavior_action", ""))
        if not trigger or not behavior_action:
            return json.dumps({"error": "trigger and behavior_action required for save_behavior"})
        memory_manager.log_learned_behavior(
            trigger=trigger,
            action=behavior_action,
            session_id=str(kwargs.get("session_id", "")),
        )
        return json.dumps({"status": "ok", "saved": "behavior"})
    if action == "get_behaviors":
        behaviors = memory_manager.get_learned_behaviors()
        return json.dumps({"behaviors": behaviors})
    return json.dumps({"error": f"unknown action: {action}"})
