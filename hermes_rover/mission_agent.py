"""
Programmatic Hermes mission runner for rover API commands.

This bridges the vendored hermes-agent runtime with the rover-specific tools,
skills, and prompts in this repository so FastAPI can execute natural-language
missions without shelling out to the interactive CLI.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_HERMES_AGENT_ROOT = _PROJECT_ROOT / "hermes-agent"
_ROVER_TOOLSET_NAME = "hermes-rover-api"
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
    return {
        "model": model,
        "provider": provider,
        "base_url": base_url,
        "max_iterations": max_iterations,
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
        _REGISTERED = True


def _run_conversation_sync(user_message: str, session_key: str) -> dict[str, Any]:
    _register_rover_tools()
    settings = _resolve_model_settings()

    from run_agent import AIAgent

    agent = AIAgent(
        model=settings["model"],
        provider=settings["provider"],
        base_url=settings["base_url"],
        max_iterations=settings["max_iterations"],
        enabled_toolsets=[_ROVER_TOOLSET_NAME],
        quiet_mode=True,
        verbose_logging=False,
        save_trajectories=False,
        ephemeral_system_prompt=_load_rover_prompt(),
    )
    history = _get_history(session_key)
    result = agent.run_conversation(
        user_message,
        conversation_history=history,
        task_id=f"rover-api-{session_key}",
    )
    _set_history(session_key, result.get("messages"))
    return result


async def run_hermes_command(text: str, user_id: str | None = None) -> dict[str, Any]:
    session_key = (str(user_id).strip() if user_id else "api-default") or "api-default"
    try:
        result = await asyncio.to_thread(_run_conversation_sync, text, session_key)
    except Exception as e:
        return {
            "status": "error",
            "response": "",
            "error": f"Hermes mission runner failed: {e}",
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
    }

