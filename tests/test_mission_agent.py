"""pytest: Mission-agent learned behavior routing and scoring."""
import json
import sys
from types import SimpleNamespace

import pytest

from hermes_rover.memory import memory_manager
from hermes_rover import mission_agent


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


def test_build_mission_preflight_includes_session_and_telemetry(monkeypatch):
    telemetry = {
        "position": {"x": 3.0, "y": -2.5, "z": 0.0},
        "orientation": {"roll": 0.02, "pitch": 0.04, "yaw": 0.0},
        "velocity": {"linear": 0.0, "angular": 0.0},
        "hazard_detected": False,
        "source": "bridge",
    }

    def fake_memory_tool(**kwargs):
        if kwargs["action"] == "check_area":
            return {
                "hazards": [{"hazard_type": "rock"}],
                "terrain": [{"terrain_type": "sand"}],
            }
        return {
            "behaviors": [
                {
                    "id": 1,
                    "trigger": "intent:explore | hazard:hazard_off | obstacle:obstacle_clear_ge_1m | nearby_terrain:sand",
                    "action": "read_sensors(imu+odometry) -> navigate_to",
                    "success_count": 2,
                    "failure_count": 0,
                    "last_used": "2026-03-12T10:00:00",
                }
            ]
        }

    monkeypatch.setattr(mission_agent, "get_telemetry_snapshot", lambda prefer_bridge=True: telemetry)
    monkeypatch.setattr(mission_agent, "read_topic", lambda *args, **kwargs: "")
    monkeypatch.setattr(mission_agent, "_call_rover_memory_tool_sync", fake_memory_tool)

    preflight = mission_agent._build_mission_preflight(
        "Explore the nearby dune field autonomously.",
        {"session_id": "live-session-42", "context_signature": "intent:explore"},
    )
    prompt = mission_agent._build_runtime_prompt(preflight)

    assert preflight["session_id"] == "live-session-42"
    assert preflight["telemetry"]["position"]["x"] == pytest.approx(3.0)
    assert preflight["preferred_behaviors"][0]["id"] == 1
    assert "live-session-42" in prompt
    assert "x=3.00" in prompt
    assert "Preferred learned behaviors" in prompt


def test_rank_behaviors_prefers_higher_net_success():
    signature = "intent:explore | hazard:hazard_off | obstacle:obstacle_clear_ge_1m | nearby_terrain:sand"
    behaviors = [
        {
            "id": 1,
            "trigger": signature,
            "action": "read_sensors(imu+odometry) -> navigate_to",
            "success_count": 1,
            "failure_count": 0,
            "last_used": "2026-03-10T10:00:00",
        },
        {
            "id": 2,
            "trigger": signature,
            "action": "read_sensors(imu+odometry) -> navigate_to",
            "success_count": 5,
            "failure_count": 4,
            "last_used": "2026-03-12T10:00:00",
        },
        {
            "id": 3,
            "trigger": signature,
            "action": "read_sensors(imu+odometry) -> navigate_to",
            "success_count": 3,
            "failure_count": 0,
            "last_used": "2026-03-09T10:00:00",
        },
    ]

    ranked = mission_agent._rank_behaviors(behaviors, signature)

    assert [behavior["id"] for behavior in ranked[:3]] == [3, 2, 1]


def test_resolve_model_settings_has_no_default_max_tokens(monkeypatch):
    monkeypatch.delenv("HERMES_MAX_TOKENS", raising=False)
    monkeypatch.delenv("HERMES_ROVER_MAX_TOKENS", raising=False)
    monkeypatch.delenv("HERMES_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(mission_agent, "_load_rover_config", lambda: {"model": "anthropic/claude-sonnet-4.5"})

    settings = mission_agent._resolve_model_settings()

    assert settings["max_tokens"] is None


def test_resolve_model_settings_uses_env_max_tokens(monkeypatch):
    monkeypatch.setenv("HERMES_MAX_TOKENS", "4096")
    monkeypatch.setattr(mission_agent, "_load_rover_config", lambda: {"model": "anthropic/claude-sonnet-4.5"})

    settings = mission_agent._resolve_model_settings()

    assert settings["max_tokens"] == 4096


def test_run_conversation_uses_capped_max_tokens_and_reasoning(monkeypatch):
    captured: dict[str, object] = {}

    class FakeAIAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run_conversation(self, *args, **kwargs):
            return {
                "messages": [],
                "completed": True,
                "partial": False,
                "final_response": "ok",
            }

    monkeypatch.setattr(mission_agent, "_register_rover_tools", lambda: None)
    monkeypatch.setattr(
        mission_agent,
        "_resolve_model_settings",
        lambda: {
            "model": "anthropic/claude-sonnet-4.5",
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "max_iterations": 18,
            "max_tokens": 4096,
            "reasoning_config": {"enabled": False},
        },
    )
    monkeypatch.setattr(
        mission_agent,
        "_build_mission_preflight",
        lambda *args, **kwargs: {
            "session_id": "live-session-42",
            "context_signature": "intent:explore | hazard:hazard_off",
            "preferred_behaviors": [],
        },
    )
    monkeypatch.setattr(mission_agent, "_get_history", lambda session_key: [])
    monkeypatch.setattr(mission_agent, "_set_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mission_agent,
        "_apply_behavior_learning",
        lambda *args, **kwargs: {"saved_behavior": False},
    )
    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=FakeAIAgent))

    result = mission_agent._run_conversation_sync(
        "Autonomous mission: navigate once, avoid hazards, then stop.",
        "user-42",
        {"session_id": "live-session-42"},
    )

    assert result["completed"] is True
    assert captured["max_tokens"] == 4096
    assert captured["reasoning_config"] == {"enabled": False}


def test_apply_behavior_learning_saves_behavior_after_success(monkeypatch):
    telemetry = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "hazard_detected": False,
    }
    monkeypatch.setattr(mission_agent, "get_telemetry_snapshot", lambda prefer_bridge=True: telemetry)

    followup_messages = _tool_exchange(
        "rover_memory",
        {
            "action": "save_behavior",
            "trigger": "intent:explore | hazard:hazard_off",
            "behavior_action": "read_sensors(imu+odometry) -> navigate_to",
            "session_id": "session-123",
        },
        {"status": "ok", "saved": "behavior"},
        "followup-1",
    )
    monkeypatch.setattr(
        mission_agent,
        "_run_behavior_followup_sync",
        lambda *args, **kwargs: {"messages": followup_messages},
    )

    result = {
        "completed": True,
        "partial": False,
        "messages": [
            *_tool_exchange("read_sensors", {"sensors": ["imu", "odometry"]}, {"status": "ok"}, "call-1"),
            *_tool_exchange("rover_memory", {"action": "check_area", "x": 0.0, "y": 0.0}, {"hazards": [], "terrain": []}, "call-2"),
            *_tool_exchange("navigate_to", {"target_x": 5.0, "target_y": 2.0}, {"status": "ok"}, "call-3"),
        ],
    }
    preflight = {
        "session_id": "session-123",
        "context_signature": "intent:explore | hazard:hazard_off | obstacle:obstacle_clear_ge_1m",
        "preferred_behaviors": [],
    }

    info = mission_agent._apply_behavior_learning("Explore ahead safely.", "user-1", result, 0, preflight)

    assert info["non_trivial"] is True
    assert info["good_outcome"] is True
    assert info["used_followup"] is True
    assert info["saved_behavior"] is True
    assert "navigate_to" in info["behavior_action"]


@pytest.mark.parametrize(
    ("messages", "completed"),
    [
        (
            _tool_exchange(
                "capture_camera_image",
                {"camera": "mastcam"},
                {"success": True, "path": "C:/tmp/mastcam.png"},
                "photo-1",
            ),
            True,
        ),
        (
            [
                *_tool_exchange("read_sensors", {"sensors": ["imu"]}, {"status": "ok"}, "haz-1"),
                *_tool_exchange(
                    "navigate_to",
                    {"target_x": 2.0, "target_y": 1.0},
                    {"status": "hazard_stop", "message": "tilt hazard"},
                    "haz-2",
                ),
            ],
            True,
        ),
    ],
)
def test_apply_behavior_learning_skips_simple_or_hazard_stop(monkeypatch, messages, completed):
    telemetry = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "hazard_detected": False,
    }
    monkeypatch.setattr(mission_agent, "get_telemetry_snapshot", lambda prefer_bridge=True: telemetry)
    called: list[bool] = []

    def fake_followup(*args, **kwargs):
        called.append(True)
        return {"messages": []}

    monkeypatch.setattr(mission_agent, "_run_behavior_followup_sync", fake_followup)

    info = mission_agent._apply_behavior_learning(
        "Handle the mission.",
        "user-2",
        {"completed": completed, "partial": False, "messages": messages},
        0,
        {
            "session_id": "session-456",
            "context_signature": "intent:general | hazard:hazard_off",
            "preferred_behaviors": [],
        },
    )

    assert info["saved_behavior"] is False
    assert called == []


def test_reused_behavior_updates_success_and_failure_counts(tmp_path, monkeypatch):
    db_path = tmp_path / "rover_memory.db"
    monkeypatch.setattr(memory_manager, "DB_PATH", str(db_path))
    memory_manager.init_db()
    memory_manager.log_learned_behavior(
        trigger="intent:explore | hazard:hazard_off | obstacle:obstacle_clear_ge_1m",
        action="read_sensors(imu+odometry) -> navigate_to",
        session_id="seed-session",
    )
    behavior = memory_manager.get_learned_behaviors()[0]

    safe_telemetry = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "hazard_detected": False,
    }
    monkeypatch.setattr(mission_agent, "get_telemetry_snapshot", lambda prefer_bridge=True: safe_telemetry)
    monkeypatch.setattr(
        mission_agent,
        "_run_behavior_followup_sync",
        lambda *args, **kwargs: {"messages": []},
    )

    preflight = {
        "session_id": "session-789",
        "context_signature": "intent:explore | hazard:hazard_off | obstacle:obstacle_clear_ge_1m",
        "preferred_behaviors": [behavior],
    }
    success_result = {
        "completed": True,
        "partial": False,
        "messages": [
            *_tool_exchange("read_sensors", {"sensors": ["imu", "odometry"]}, {"status": "ok"}, "succ-1"),
            *_tool_exchange("navigate_to", {"target_x": 4.0, "target_y": 1.0}, {"status": "ok"}, "succ-2"),
            *_tool_exchange(
                "rover_memory",
                {
                    "action": "save_behavior",
                    "trigger": "intent:explore | hazard:hazard_off",
                    "behavior_action": "read_sensors(imu+odometry) -> navigate_to",
                    "session_id": "session-789",
                },
                {"status": "ok", "saved": "behavior"},
                "succ-3",
            ),
        ],
    }
    mission_agent._apply_behavior_learning("Explore the ridge.", "user-3", success_result, 0, preflight)

    failure_result = {
        "completed": True,
        "partial": False,
        "messages": [
            *_tool_exchange("read_sensors", {"sensors": ["imu", "odometry"]}, {"status": "ok"}, "fail-1"),
            *_tool_exchange(
                "navigate_to",
                {"target_x": 6.0, "target_y": 2.0},
                {"status": "hazard_stop", "message": "obstacle in lidar"},
                "fail-2",
            ),
        ],
    }
    mission_agent._apply_behavior_learning("Explore the ridge.", "user-4", failure_result, 0, preflight)

    updated = memory_manager.get_learned_behaviors()[0]
    assert updated["success_count"] == 1
    assert updated["failure_count"] == 1
