#!/usr/bin/env python3
"""Deterministic learned-behavior smoke test using real mission_agent logic."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("HERMES_PROJECT_ROOT", str(REPO_ROOT))

from hermes_rover import mission_agent  # noqa: E402
from hermes_rover.memory import memory_manager  # noqa: E402


def _tool_exchange(tool_name: str, args: dict, result: dict, call_id: str) -> list[dict]:
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": call_id,
                    "call_id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(args),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(result),
        },
    ]


def _latest_behavior_for_session(session_id: str) -> dict | None:
    matches = [
        row for row in memory_manager.get_learned_behaviors()
        if str(row.get("source_session") or "") == session_id
    ]
    return matches[-1] if matches else None


def main() -> int:
    memory_manager.init_db()
    session_id = f"behavior-test-{uuid.uuid4().hex[:8]}"
    context_signature = "intent:explore | hazard:hazard_off | obstacle:obstacle_clear_ge_1m"

    original_followup = mission_agent._run_behavior_followup_sync
    mission_agent._run_behavior_followup_sync = lambda *args, **kwargs: {"messages": []}
    try:
        first_result = {
            "completed": True,
            "partial": False,
            "messages": [
                *_tool_exchange(
                    "read_sensors",
                    {"sensors": ["imu", "odometry"]},
                    {"status": "ok"},
                    "call-1",
                ),
                *_tool_exchange(
                    "rover_memory",
                    {"action": "check_area", "x": 0.0, "y": 0.0},
                    {"hazards": [], "terrain": []},
                    "call-2",
                ),
                *_tool_exchange(
                    "drive_rover",
                    {"linear_speed": 0.0, "angular_speed": 0.2, "duration": 0.5},
                    {"status": "ok"},
                    "call-3",
                ),
                *_tool_exchange(
                    "drive_rover",
                    {"linear_speed": 0.2, "angular_speed": 0.0, "duration": 0.8},
                    {"status": "ok"},
                    "call-4",
                ),
            ],
        }
        first_preflight = {
            "session_id": session_id,
            "context_signature": context_signature,
            "preferred_behaviors": [],
        }
        first_info = mission_agent._apply_behavior_learning(
            "Autonomous mission: sensor check, short turn, short forward move, stop.",
            "behavior-test-user",
            first_result,
            0,
            first_preflight,
        )

        saved_behavior = _latest_behavior_for_session(session_id)
        if saved_behavior is None:
            print(json.dumps({
                "ok": False,
                "error": "No learned behavior was saved.",
                "first_info": first_info,
            }, indent=2))
            return 1

        second_result = {
            "completed": True,
            "partial": False,
            "messages": [
                *_tool_exchange(
                    "read_sensors",
                    {"sensors": ["imu", "odometry"]},
                    {"status": "ok"},
                    "call-5",
                ),
                *_tool_exchange(
                    "rover_memory",
                    {"action": "check_area", "x": 0.0, "y": 0.0},
                    {"hazards": [], "terrain": []},
                    "call-5b",
                ),
                *_tool_exchange(
                    "drive_rover",
                    {"linear_speed": 0.0, "angular_speed": 0.2, "duration": 0.5},
                    {"status": "ok"},
                    "call-6",
                ),
                *_tool_exchange(
                    "drive_rover",
                    {"linear_speed": 0.2, "angular_speed": 0.0, "duration": 0.8},
                    {"status": "ok"},
                    "call-7",
                ),
            ],
        }
        second_preflight = {
            "session_id": f"{session_id}-reuse",
            "context_signature": context_signature,
            "preferred_behaviors": [saved_behavior],
        }
        second_info = mission_agent._apply_behavior_learning(
            "Repeat the same short safe maneuver.",
            "behavior-test-user",
            second_result,
            0,
            second_preflight,
        )

        refreshed = next(
            row for row in memory_manager.get_learned_behaviors()
            if int(row.get("id") or 0) == int(saved_behavior.get("id") or 0)
        )
        print(json.dumps({
            "ok": True,
            "session_id": session_id,
            "saved_behavior_id": refreshed["id"],
            "first_info": first_info,
            "second_info": second_info,
            "behavior": {
                "trigger": refreshed["trigger"],
                "action": refreshed["action"],
                "success_count": refreshed["success_count"],
                "failure_count": refreshed["failure_count"],
                "source_session": refreshed["source_session"],
            },
        }, indent=2))
        return 0
    finally:
        mission_agent._run_behavior_followup_sync = original_followup


if __name__ == "__main__":
    raise SystemExit(main())
