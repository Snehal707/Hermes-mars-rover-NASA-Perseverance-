"""
Programmatic Hermes mission runner for rover API commands.

This bridges the vendored hermes-agent runtime with the rover-specific tools,
skills, and prompts in this repository so FastAPI can execute natural-language
missions without shelling out to the interactive CLI.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from hermes_rover.memory import memory_manager
from hermes_rover.telemetry import LIDAR_TOPIC, get_telemetry_snapshot, read_topic
from hermes_rover.tools import memory_tool

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_HERMES_AGENT_ROOT = _PROJECT_ROOT / "hermes-agent"
_ROVER_TOOLSET_NAME = "hermes-rover-api"
_ROVER_MEMORY_TOOLSET_NAME = "hermes-rover-memory-followup"
_ROVER_TOOL_NAMES = [
    "drive_rover",
    "read_sensors",
    "navigate_to",
    "check_hazards",
    "rover_memory",
    "generate_report",
    "capture_camera_image",
]
_SUPPORT_TOOL_NAMES = [
    "skills_list",
    "skill_view",
    "skill_manage",
    "send_message",
    "clarify",
]
_HISTORY_LIMIT = 60
_CHECK_AREA_RADIUS_M = 10.0
_HAZARD_LIDAR_MIN_M = 1.0
_MOVEMENT_TOOL_NAMES = {"drive_rover", "navigate_to"}
_ALLOWED_BEHAVIOR_TOOL_NAMES = set(_ROVER_TOOL_NAMES) | {"check_hazards"}
_DISALLOWED_BEHAVIOR_TOKENS = {
    "shell",
    "bash",
    "powershell",
    "python",
    "curl",
    "wget",
    "terminal",
    "subprocess",
    "patch",
    "write_file",
    "read_file",
    "browser_",
    "ignore safety",
    "bypass",
    "disable hazard",
    "disable imu",
    "disable lidar",
}
_TRIGGER_TOKEN_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "into",
    "from",
    "this",
    "that",
    "then",
    "when",
    "than",
    "over",
    "near",
    "just",
    "area",
    "mission",
    "rover",
    "safe",
    "safely",
    "current",
    "later",
}
_TOOL_NAME_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(name) for name in sorted(_ALLOWED_BEHAVIOR_TOOL_NAMES, key=len, reverse=True))
    + r")\b"
)

_REGISTRATION_LOCK = threading.Lock()
_REGISTERED = False
_HISTORY_LOCK = threading.Lock()
_HISTORY_BY_SESSION: dict[str, list[dict[str, Any]]] = {}


def _prepend_sys_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _ensure_runtime_paths() -> None:
    _prepend_sys_path(_PROJECT_ROOT)
    _prepend_sys_path(_HERMES_AGENT_ROOT)
    os.environ.setdefault("HERMES_PROJECT_ROOT", str(_PROJECT_ROOT))


def _load_rover_config() -> dict[str, Any]:
    config_path = _PROJECT_ROOT / "hermes_rover" / "config" / "hermes_config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _coerce_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _resolve_reasoning_config(config: dict[str, Any]) -> dict[str, Any] | None:
    raw = (
        os.environ.get("HERMES_REASONING_EFFORT")
        or config.get("reasoning_effort")
        or ""
    )
    effort = str(raw or "").strip().lower()
    if effort in {"", "none", "off", "disabled", "false", "0"}:
        return {"enabled": False}
    if effort in {"minimal", "low", "medium", "high", "xhigh"}:
        return {"enabled": True, "effort": effort}
    return {"enabled": False}


def _resolve_model_settings() -> dict[str, Any]:
    config = _load_rover_config()
    model = (
        os.environ.get("HERMES_ROVER_MODEL")
        or os.environ.get("HERMES_MODEL")
        or os.environ.get("LLM_MODEL")
        or config.get("model")
        or "anthropic/claude-sonnet-4"
    )
    provider = (
        os.environ.get("HERMES_ROVER_PROVIDER")
        or os.environ.get("HERMES_INFERENCE_PROVIDER")
        or config.get("provider")
        or "openrouter"
    )
    base_url = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("OPENROUTER_BASE_URL")
        or "https://openrouter.ai/api/v1"
    )
    max_iterations = int(
        os.environ.get(
            "HERMES_ROVER_MAX_ITERATIONS",
            config.get("max_iterations", 18),
        )
    )
    max_tokens = _coerce_positive_int(
        os.environ.get("HERMES_MAX_TOKENS")
        or os.environ.get("HERMES_ROVER_MAX_TOKENS")
        or config.get("max_tokens"),
    )
    return {
        "model": model,
        "provider": provider,
        "base_url": base_url,
        "max_iterations": max_iterations,
        "max_tokens": max_tokens,
        "reasoning_config": _resolve_reasoning_config(config),
    }


def _load_rover_prompt() -> str:
    prompt_parts: list[str] = []
    for name in ("system_prompt.md", "context.md"):
        path = _PROJECT_ROOT / "hermes_rover" / "config" / name
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore").strip()
        if content:
            prompt_parts.append(content)
    prompt_parts.append(
        "## API Mission Mode\n"
        "You are executing through the rover API, not an interactive shell.\n"
        "Prefer rover tools and rover skills over generic actions.\n"
        "If the command is mission-like, break it into safe rover actions, use the available tools, and report the concrete outcome.\n"
        "For short maneuvers or brief demonstrations, prefer bounded drive_rover steps over navigate_to.\n"
        "Before path planning or avoidance in a similar context, consult learned behaviors and prefer the best safe match.\n"
        "After a non-trivial safe success, save exactly one learned behavior tied to the active session.\n"
        "Do not claim a photo, report, or delivery succeeded unless a tool confirms it."
    )
    return "\n\n".join(prompt_parts).strip()


def _sync_rover_skills() -> None:
    src = _PROJECT_ROOT / "hermes_rover" / "skills"
    if not src.exists():
        return
    hermes_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))
    dst = hermes_home / "skills" / "rover"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _trim_history(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not messages:
        return []
    return list(messages[-_HISTORY_LIMIT:])


def _get_history(session_key: str) -> list[dict[str, Any]]:
    with _HISTORY_LOCK:
        return list(_HISTORY_BY_SESSION.get(session_key, []))


def _set_history(session_key: str, messages: list[dict[str, Any]] | None) -> None:
    with _HISTORY_LOCK:
        _HISTORY_BY_SESSION[session_key] = _trim_history(messages)


def _register_rover_tools() -> None:
    global _REGISTERED
    if _REGISTERED:
        return

    with _REGISTRATION_LOCK:
        if _REGISTERED:
            return

        _ensure_runtime_paths()
        _sync_rover_skills()

        from tools.registry import registry
        from toolsets import create_custom_toolset
        from hermes_rover.tools import tool_registry

        for schema in tool_registry.get_all_tools():
            tool_name = schema["name"]
            executor = tool_registry.get_tool_executor(tool_name)
            if executor is None:
                continue

            async def _handler(args: dict[str, Any] | None = None, _executor=executor, **_kwargs) -> str:
                return await _executor(**(args or {}))

            registry.register(
                name=tool_name,
                toolset="rover",
                schema=schema,
                handler=_handler,
                is_async=True,
                description=schema.get("description", ""),
            )

        create_custom_toolset(
            name=_ROVER_TOOLSET_NAME,
            description="Hermes rover mission toolset for Mars simulation control",
            tools=[*_ROVER_TOOL_NAMES, *_SUPPORT_TOOL_NAMES],
            includes=[],
        )
        create_custom_toolset(
            name=_ROVER_MEMORY_TOOLSET_NAME,
            description="Memory-only rover follow-up toolset for learned behavior logging",
            tools=["rover_memory", "read_sensors"],
            includes=[],
        )
        _REGISTERED = True


def _safe_json_loads(raw: Any) -> Any:
    if not isinstance(raw, str):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return raw


def _normalized_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", (text or "").lower())
        if len(token) > 1 and token not in _TRIGGER_TOKEN_STOPWORDS
    }


def _extract_mission_intents(user_message: str) -> list[str]:
    lowered = (user_message or "").lower()
    labels: list[str] = []
    patterns = [
        ("explore", ("explore", "autonomous", "autonomously")),
        ("navigate", ("navigate", "waypoint", "go to", "reach", "move to")),
        ("avoid", ("avoid", "hazard", "obstacle", "cliff")),
        ("survey", ("survey", "scan", "assess", "analyze", "analyse")),
        ("imaging", ("photo", "camera", "image", "mastcam", "navcam", "hazcam")),
        ("report", ("report", "summary")),
    ]
    for label, candidates in patterns:
        if any(candidate in lowered for candidate in candidates):
            labels.append(label)
    if labels:
        return labels
    tokens = sorted(_normalized_tokens(user_message))
    return tokens[:3] or ["general"]


def _tilt_band(snapshot: dict[str, Any]) -> str:
    orientation = snapshot.get("orientation", {}) if isinstance(snapshot, dict) else {}
    try:
        roll = abs(float(orientation.get("roll", 0.0)))
        pitch = abs(float(orientation.get("pitch", 0.0)))
    except Exception:
        return "tilt_unknown"
    max_tilt = max(roll, pitch)
    if max_tilt < 0.2:
        return "tilt_low_lt_0_2"
    if max_tilt < 0.35:
        return "tilt_moderate_0_2_to_0_35"
    if max_tilt < 0.52:
        return "tilt_warning_0_35_to_0_52"
    return "tilt_critical_ge_0_52"


def _lidar_obstacle_snapshot() -> dict[str, Any]:
    raw = read_topic(LIDAR_TOPIC, timeout_sec=2)
    values: list[float] = []
    for first, second in re.findall(r"range\s*:\s*([\d.e+-]+)|ranges\s*\[([\d.e+-]+)\]", raw or ""):
        token = (first or second or "").strip()
        if not token:
            continue
        try:
            value = float(token)
        except Exception:
            continue
        if 0.01 < value < 1000:
            values.append(value)
    if not values:
        return {"state": "obstacle_unknown", "min_range_m": None}
    min_range = min(values)
    if min_range < _HAZARD_LIDAR_MIN_M:
        return {"state": "obstacle_lt_1m", "min_range_m": round(min_range, 3)}
    return {"state": "obstacle_clear_ge_1m", "min_range_m": round(min_range, 3)}


def _memory_label_summary(rows: list[dict[str, Any]], key: str) -> str:
    labels: list[str] = []
    for row in rows:
        value = str(row.get(key) or "").strip().lower()
        if value and value not in labels:
            labels.append(value)
    return ",".join(labels[:3]) if labels else "none"


def _call_rover_memory_tool_sync(**kwargs) -> dict[str, Any]:
    payload = asyncio.run(memory_tool.execute(**kwargs))
    parsed = _safe_json_loads(payload)
    return parsed if isinstance(parsed, dict) else {}


def _resolve_session_id(mission_context: dict[str, Any] | None) -> str:
    if isinstance(mission_context, dict):
        session_id = str(mission_context.get("session_id") or "").strip()
        if session_id:
            return session_id
    active = memory_manager.get_active_live_session()
    if isinstance(active, dict):
        return str(active.get("session_id") or "").strip()
    return ""


def _build_context_signature(
    user_message: str,
    telemetry: dict[str, Any],
    memory_snapshot: dict[str, Any],
    obstacle_snapshot: dict[str, Any],
    provided_signature: str = "",
) -> str:
    parts: list[str] = []
    if provided_signature.strip():
        parts.append(provided_signature.strip())
    parts.append(f"intent:{'+'.join(_extract_mission_intents(user_message))}")
    parts.append(f"tilt:{_tilt_band(telemetry)}")
    parts.append(f"hazard:{'hazard_on' if bool(telemetry.get('hazard_detected', False)) else 'hazard_off'}")
    parts.append(f"obstacle:{str(obstacle_snapshot.get('state') or 'obstacle_unknown')}")
    parts.append(f"nearby_hazards:{_memory_label_summary(memory_snapshot.get('hazards', []), 'hazard_type')}")
    parts.append(f"nearby_terrain:{_memory_label_summary(memory_snapshot.get('terrain', []), 'terrain_type')}")
    deduped: list[str] = []
    for part in parts:
        if part and part not in deduped:
            deduped.append(part)
    return " | ".join(deduped)


def _extract_tool_names_from_text(text: str) -> list[str]:
    return [match.group(0) for match in _TOOL_NAME_PATTERN.finditer(text or "")]


def _behavior_is_safe(action: str) -> bool:
    lowered = (action or "").lower()
    if any(token in lowered for token in _DISALLOWED_BEHAVIOR_TOKENS):
        return False
    return bool(_extract_tool_names_from_text(action))


def _parse_timestamp(value: str) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _rank_behaviors(
    behaviors: list[dict[str, Any]],
    context_signature: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    current_tokens = _normalized_tokens(context_signature)
    ranked: list[dict[str, Any]] = []
    for behavior in behaviors:
        trigger = str(behavior.get("trigger") or "").strip()
        action = str(behavior.get("action") or behavior.get("behavior_action") or "").strip()
        if not trigger or not action or not _behavior_is_safe(action):
            continue
        trigger_tokens = _normalized_tokens(trigger)
        overlap = len(trigger_tokens & current_tokens)
        union = len(trigger_tokens | current_tokens) or 1
        similarity = overlap / union
        if similarity < 0.12:
            continue
        success_count = int(behavior.get("success_count") or 0)
        failure_count = int(behavior.get("failure_count") or 0)
        rank_score = round(similarity * 100.0 + (success_count - failure_count) * 5.0 + success_count, 3)
        enriched = dict(behavior)
        enriched["action"] = action
        enriched["_similarity"] = similarity
        enriched["_rank_score"] = rank_score
        ranked.append(enriched)
    ranked.sort(
        key=lambda item: (
            float(item.get("_rank_score") or 0.0),
            int(item.get("success_count") or 0),
            _parse_timestamp(str(item.get("last_used") or "")),
        ),
        reverse=True,
    )
    return ranked[:limit]


def _build_mission_preflight(user_message: str, mission_context: dict[str, Any] | None = None) -> dict[str, Any]:
    mission_context = mission_context if isinstance(mission_context, dict) else {}
    provided_telemetry = mission_context.get("telemetry_snapshot")
    if not isinstance(provided_telemetry, dict):
        provided_telemetry = mission_context.get("telemetry")
    telemetry = get_telemetry_snapshot(prefer_bridge=True)
    if not isinstance(telemetry, dict) or not telemetry:
        telemetry = provided_telemetry if isinstance(provided_telemetry, dict) else {}

    position = telemetry.get("position", {}) if isinstance(telemetry.get("position"), dict) else {}
    try:
        x = float(position.get("x", 0.0))
        y = float(position.get("y", 0.0))
    except Exception:
        x = 0.0
        y = 0.0

    memory_snapshot = _call_rover_memory_tool_sync(action="check_area", x=x, y=y, radius=_CHECK_AREA_RADIUS_M)
    if not isinstance(memory_snapshot.get("hazards"), list):
        memory_snapshot["hazards"] = []
    if not isinstance(memory_snapshot.get("terrain"), list):
        memory_snapshot["terrain"] = []

    behaviors_payload = _call_rover_memory_tool_sync(action="get_behaviors")
    all_behaviors = behaviors_payload.get("behaviors", [])
    if not isinstance(all_behaviors, list):
        all_behaviors = []

    obstacle_snapshot = _lidar_obstacle_snapshot()
    context_signature = _build_context_signature(
        user_message,
        telemetry,
        memory_snapshot,
        obstacle_snapshot,
        str(mission_context.get("context_signature") or ""),
    )
    return {
        "session_id": _resolve_session_id(mission_context),
        "telemetry": telemetry,
        "memory_snapshot": memory_snapshot,
        "obstacle_snapshot": obstacle_snapshot,
        "context_signature": context_signature,
        "preferred_behaviors": _rank_behaviors(all_behaviors, context_signature),
    }


def _format_runtime_context(preflight: dict[str, Any]) -> str:
    telemetry = preflight.get("telemetry", {}) if isinstance(preflight, dict) else {}
    position = telemetry.get("position", {}) if isinstance(telemetry.get("position"), dict) else {}
    orientation = telemetry.get("orientation", {}) if isinstance(telemetry.get("orientation"), dict) else {}
    memory_snapshot = preflight.get("memory_snapshot", {}) if isinstance(preflight, dict) else {}
    obstacle_snapshot = preflight.get("obstacle_snapshot", {}) if isinstance(preflight, dict) else {}
    behavior_lines = [
        (
            f'- trigger="{behavior.get("trigger", "")}" '
            f'action="{behavior.get("action", "")}" '
            f'success={int(behavior.get("success_count") or 0)} '
            f'failure={int(behavior.get("failure_count") or 0)}'
        )
        for behavior in preflight.get("preferred_behaviors", [])[:3]
    ] or ["- none preloaded"]
    return "\n".join(
        [
            "## Mission Runtime Context",
            f'- Active session_id: {preflight.get("session_id") or "unknown"}',
            f'- Context signature: {preflight.get("context_signature") or "unknown"}',
            (
                "- Live telemetry: "
                f'x={float(position.get("x", 0.0)):.2f}, '
                f'y={float(position.get("y", 0.0)):.2f}, '
                f'roll={float(orientation.get("roll", 0.0)):.2f}, '
                f'pitch={float(orientation.get("pitch", 0.0)):.2f}, '
                f'hazard={bool(telemetry.get("hazard_detected", False))}'
            ),
            (
                "- Immediate obstacle state: "
                f'{obstacle_snapshot.get("state", "obstacle_unknown")} '
                f'(min_range_m={obstacle_snapshot.get("min_range_m")})'
            ),
            (
                "- Nearby memory: "
                f'hazards={_memory_label_summary(memory_snapshot.get("hazards", []), "hazard_type")}; '
                f'terrain={_memory_label_summary(memory_snapshot.get("terrain", []), "terrain_type")}'
            ),
            "- Preferred learned behaviors:",
            *behavior_lines,
            (
                "- Use preferred learned behaviors only when current telemetry still matches and all IMU, "
                "LIDAR, hazard, and terrain safety checks remain satisfied."
            ),
        ]
    )


def _build_runtime_prompt(preflight: dict[str, Any] | None = None, *, followup: bool = False) -> str:
    prompt = _load_rover_prompt()
    if preflight:
        prompt = f"{prompt}\n\n{_format_runtime_context(preflight)}"
    if followup:
        prompt = (
            f"{prompt}\n\n"
            "## Learned Behavior Follow-up\n"
            "You are in a post-mission learning pass.\n"
            "You may only use rover_memory and read_sensors.\n"
            "If the mission summary describes a non-trivial safe success, save exactly one learned behavior.\n"
            "Do not invent new tools, exact coordinates, or any behavior that bypasses safety."
        )
    return prompt


def _extract_tool_events(messages: list[dict[str, Any]], history_length: int) -> list[dict[str, Any]]:
    pending_calls: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for message in messages[history_length:]:
        role = str(message.get("role") or "")
        if role == "assistant":
            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function", {}) if isinstance(tool_call, dict) else {}
                call_id = str(tool_call.get("id") or tool_call.get("call_id") or "").strip()
                pending_calls[call_id] = {
                    "name": str(function.get("name") or "").strip(),
                    "args": _safe_json_loads(function.get("arguments", "{}")),
                }
            continue
        if role != "tool":
            continue
        tool_call_id = str(message.get("tool_call_id") or "").strip()
        metadata = pending_calls.get(tool_call_id, {})
        events.append(
            {
                "tool_call_id": tool_call_id,
                "name": str(metadata.get("name") or "").strip(),
                "args": metadata.get("args") if isinstance(metadata.get("args"), dict) else {},
                "result": _safe_json_loads(str(message.get("content") or "")),
                "result_raw": str(message.get("content") or ""),
            }
        )
    return events


def _tool_event_failed(event: dict[str, Any]) -> bool:
    result = event.get("result")
    if isinstance(result, dict):
        status = str(result.get("status") or "").strip().lower()
        if status in {"error", "hazard_stop"}:
            return True
        if result.get("success") is False:
            return True
        if str(result.get("error") or "").strip():
            return True
    return str(event.get("result_raw") or "").strip().lower().startswith("error executing tool")


def _is_non_trivial_mission(tool_events: list[dict[str, Any]]) -> bool:
    movement_events = [event for event in tool_events if event.get("name") in _MOVEMENT_TOOL_NAMES]
    return any(event.get("name") == "navigate_to" for event in movement_events) or len(movement_events) >= 2


def _summarize_behavior_action(tool_events: list[dict[str, Any]]) -> str:
    descriptors: list[str] = []
    for event in tool_events:
        name = str(event.get("name") or "").strip()
        if not name or name not in _ALLOWED_BEHAVIOR_TOOL_NAMES:
            continue
        args = event.get("args") if isinstance(event.get("args"), dict) else {}
        if name == "rover_memory":
            memory_action = str(args.get("action") or "").strip()
            if memory_action in {"", "save_behavior", "recall_sessions"}:
                continue
            label = f"rover_memory({memory_action})"
        elif name == "read_sensors":
            sensors = args.get("sensors")
            if isinstance(sensors, list) and sensors:
                selected = [str(sensor).strip() for sensor in sensors[:3] if str(sensor).strip()]
                label = f"read_sensors({'+'.join(selected)})" if selected else "read_sensors"
            else:
                label = "read_sensors"
        elif name == "capture_camera_image":
            camera = str(args.get("camera") or "").strip()
            label = f"capture_camera_image({camera})" if camera else "capture_camera_image"
        elif name == "drive_rover":
            try:
                linear = float(args.get("linear_speed", 0.0))
                angular = float(args.get("angular_speed", 0.0))
            except Exception:
                linear = 0.0
                angular = 0.0
            if abs(linear) > 0 and abs(angular) > 0:
                label = "drive_rover(move_turn)"
            elif abs(linear) > 0:
                label = "drive_rover(move)"
            elif abs(angular) > 0:
                label = "drive_rover(turn)"
            else:
                label = "drive_rover(stop)"
        else:
            label = name
        if not descriptors or descriptors[-1] != label:
            descriptors.append(label)
    return " -> ".join(descriptors[:6])


def _ordered_subsequence_score(expected: list[str], actual: list[str]) -> float:
    if not expected or not actual:
        return 0.0
    expected_index = 0
    matched = 0
    for actual_name in actual:
        if expected_index >= len(expected):
            break
        if actual_name == expected[expected_index]:
            matched += 1
            expected_index += 1
    return matched / len(expected)


def _find_reused_behavior(
    preferred_behaviors: list[dict[str, Any]],
    tool_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    actual_names = [str(event.get("name") or "").strip() for event in tool_events if str(event.get("name") or "").strip()]
    best_behavior: dict[str, Any] | None = None
    best_key = (0.0, 0, 0, 0.0)
    for behavior in preferred_behaviors:
        expected = [
            name
            for name in _extract_tool_names_from_text(str(behavior.get("action") or ""))
            if name in _MOVEMENT_TOOL_NAMES or name in {"read_sensors", "rover_memory", "check_hazards"}
        ]
        if not expected or not any(name in _MOVEMENT_TOOL_NAMES for name in expected):
            continue
        score = _ordered_subsequence_score(expected, actual_names)
        if score < 0.6:
            continue
        success_count = int(behavior.get("success_count") or 0)
        failure_count = int(behavior.get("failure_count") or 0)
        candidate_key = (
            score,
            success_count - failure_count,
            success_count,
            float(behavior.get("_rank_score") or 0.0),
        )
        if candidate_key > best_key:
            best_behavior = behavior
            best_key = candidate_key
    return best_behavior


def _mission_good_outcome(result: dict[str, Any], tool_events: list[dict[str, Any]]) -> bool:
    if not bool(result.get("completed")) or bool(result.get("partial")):
        return False
    if any(_tool_event_failed(event) for event in tool_events):
        return False
    return not bool(get_telemetry_snapshot(prefer_bridge=True).get("hazard_detected", False))


def _save_behavior_with_tool_sync(trigger: str, behavior_action: str, session_id: str) -> dict[str, Any]:
    return _call_rover_memory_tool_sync(
        action="save_behavior",
        trigger=trigger,
        behavior_action=behavior_action,
        session_id=session_id,
    )


def _run_behavior_followup_sync(
    user_message: str,
    session_key: str,
    preflight: dict[str, Any],
    behavior_action: str,
) -> dict[str, Any]:
    _register_rover_tools()
    settings = _resolve_model_settings()

    from run_agent import AIAgent

    agent = AIAgent(
        model=settings["model"],
        provider=settings["provider"],
        base_url=settings["base_url"],
        max_iterations=min(6, settings["max_iterations"]),
        max_tokens=settings["max_tokens"],
        reasoning_config=settings["reasoning_config"],
        enabled_toolsets=[_ROVER_MEMORY_TOOLSET_NAME],
        quiet_mode=True,
        verbose_logging=False,
        save_trajectories=False,
        ephemeral_system_prompt=_build_runtime_prompt(preflight, followup=True),
    )
    followup_request = (
        "Mission follow-up summary:\n"
        f"- Original request: {user_message}\n"
        f"- Session ID: {preflight.get('session_id') or 'unknown'}\n"
        f"- Context signature: {preflight.get('context_signature') or 'unknown'}\n"
        f"- Suggested behavior action: {behavior_action}\n"
        "If and only if this was a safe non-trivial success, call rover_memory exactly once with "
        'action="save_behavior", the provided session_id, a coarse trigger based on the context signature, '
        "and the suggested behavior action. Return a short confirmation."
    )
    return agent.run_conversation(followup_request, task_id=f"rover-behavior-{session_key}")


def _apply_behavior_learning(
    user_message: str,
    session_key: str,
    result: dict[str, Any],
    history_length: int,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    messages = result.get("messages")
    messages = messages if isinstance(messages, list) else []
    tool_events = _extract_tool_events(messages, history_length)
    behavior_action = _summarize_behavior_action(tool_events)
    non_trivial = _is_non_trivial_mission(tool_events)
    save_behavior_called = any(
        event.get("name") == "rover_memory"
        and str((event.get("args") or {}).get("action") or "").strip() == "save_behavior"
        for event in tool_events
    )
    good_outcome = _mission_good_outcome(result, tool_events)
    reused_behavior = _find_reused_behavior(preflight.get("preferred_behaviors", []), tool_events)
    info: dict[str, Any] = {
        "non_trivial": non_trivial,
        "good_outcome": good_outcome,
        "saved_behavior": save_behavior_called,
        "save_behavior_called": save_behavior_called,
        "used_followup": False,
        "save_fallback": False,
        "behavior_action": behavior_action,
        "reused_behavior_id": None,
        "reused_behavior_outcome": "",
        "trigger": str(preflight.get("context_signature") or ""),
    }

    if reused_behavior is not None:
        behavior_id = int(reused_behavior.get("id") or 0)
        if behavior_id > 0:
            if good_outcome:
                memory_manager.increment_behavior_success(behavior_id)
                info["reused_behavior_outcome"] = "success"
            else:
                memory_manager.increment_behavior_failure(behavior_id)
                info["reused_behavior_outcome"] = "failure"
            info["reused_behavior_id"] = behavior_id

    if not non_trivial or not good_outcome:
        return info

    session_id = str(preflight.get("session_id") or "").strip()
    if save_behavior_called or not session_id or not behavior_action:
        return info

    info["used_followup"] = True
    followup_saved = False
    try:
        followup = _run_behavior_followup_sync(user_message, session_key, preflight, behavior_action)
        followup_messages = followup.get("messages")
        followup_messages = followup_messages if isinstance(followup_messages, list) else []
        followup_events = _extract_tool_events(followup_messages, 0)
        followup_saved = any(
            event.get("name") == "rover_memory"
            and str((event.get("args") or {}).get("action") or "").strip() == "save_behavior"
            and isinstance(event.get("result"), dict)
            and str((event.get("result") or {}).get("status") or "").strip().lower() == "ok"
            for event in followup_events
        )
    except Exception as exc:
        info["followup_error"] = str(exc)

    if not followup_saved:
        info["save_fallback"] = True
        followup_saved = str(
            _save_behavior_with_tool_sync(str(preflight.get("context_signature") or ""), behavior_action, session_id).get("status")
            or ""
        ).strip().lower() == "ok"

    info["saved_behavior"] = followup_saved
    return info


def _run_conversation_sync(
    user_message: str,
    session_key: str,
    mission_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _register_rover_tools()
    settings = _resolve_model_settings()
    preflight = _build_mission_preflight(user_message, mission_context)

    from run_agent import AIAgent

    agent = AIAgent(
        model=settings["model"],
        provider=settings["provider"],
        base_url=settings["base_url"],
        max_iterations=settings["max_iterations"],
        max_tokens=settings["max_tokens"],
        reasoning_config=settings["reasoning_config"],
        enabled_toolsets=[_ROVER_TOOLSET_NAME],
        quiet_mode=True,
        verbose_logging=False,
        save_trajectories=False,
        ephemeral_system_prompt=_build_runtime_prompt(preflight),
    )
    history = _get_history(session_key)
    result = agent.run_conversation(
        user_message,
        conversation_history=history,
        task_id=f"rover-api-{session_key}",
    )
    _set_history(session_key, result.get("messages"))
    result["mission_preflight"] = preflight
    result["behavior_learning"] = _apply_behavior_learning(
        user_message,
        session_key,
        result,
        len(history),
        preflight,
    )
    return result


async def run_hermes_command(
    text: str,
    user_id: str | None = None,
    mission_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session_key = (str(user_id).strip() if user_id else "api-default") or "api-default"
    try:
        result = await asyncio.to_thread(_run_conversation_sync, text, session_key, mission_context)
    except Exception as exc:
        return {
            "status": "error",
            "response": "",
            "error": f"Hermes mission runner failed: {exc}",
            "completed": False,
            "partial": False,
        }

    final_response = str(result.get("final_response") or "").strip()
    error = str(result.get("error") or "").strip()
    partial = bool(result.get("partial"))
    completed = bool(result.get("completed"))

    if completed and final_response:
        status = "completed"
    elif partial and (final_response or error):
        status = "partial"
    elif final_response:
        status = "completed"
    else:
        status = "error"

    return {
        "status": status,
        "response": final_response or error,
        "error": error,
        "completed": completed,
        "partial": partial,
        "api_calls": int(result.get("api_calls", 0)),
        "behavior_learning": result.get("behavior_learning"),
    }
