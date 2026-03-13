"""
Hermes Mars Rover API â€” central backend on port 8000.
Proxies bridge, exposes memory/hazards/skills/behaviors, storm toggle, command queue, WebSocket stream.
"""
import asyncio
import math
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

import aiohttp
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel

try:
    from fpdf import FPDF
    _PDF_AVAILABLE = True
except ImportError:
    _PDF_AVAILABLE = False

from hermes_rover.memory import memory_manager

memory_manager.init_db()

# Module state
_command_queue: deque = deque(maxlen=1000)
_storm_active: bool = False
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://localhost:8765")
ROOT = Path(os.environ.get("HERMES_PROJECT_ROOT", Path(__file__).resolve().parent.parent))
SKILLS_DIR = ROOT / "hermes_rover" / "skills"
WS_STREAM_INTERVAL_SEC = float(os.environ.get("HERMES_WS_STREAM_INTERVAL_SEC", "0.2"))
WS_BRIDGE_STALE_GRACE_SEC = float(os.environ.get("HERMES_WS_BRIDGE_STALE_GRACE_SEC", "3.0"))

_live_mission: dict = {
    "session_id": "",
    "start_time": "",
    "last_update": "",
    "commands_sent": 0,
    "distance_traveled": 0.0,
    "hazards_detected": 0,
    "last_hazard_state": False,
    "last_position": None,  # tuple[x, y, z]
}


app = FastAPI(title="Hermes Mars Rover API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    api_key = os.environ.get("ROVER_API_KEY")
    if api_key:
        provided = request.headers.get("X-API-Key")
        if provided != api_key:
            return JSONResponse(
                {"detail": "Invalid or missing X-API-Key"},
                status_code=403,
            )
    return await call_next(request)


class CommandBody(BaseModel):
    text: str
    user_id: str | None = None


class DriveBody(BaseModel):
    linear: float
    angular: float
    duration: float


def _now_iso() -> str:
    return datetime.now().isoformat()


def _extract_position_tuple(status: dict | None) -> tuple[float, float, float] | None:
    if not isinstance(status, dict):
        return None
    pos = status.get("position")
    if not isinstance(pos, dict):
        return None
    try:
        return (
            float(pos.get("x", 0.0)),
            float(pos.get("y", 0.0)),
            float(pos.get("z", 0.0)),
        )
    except Exception:
        return None


def _active_live_session_record() -> dict | None:
    record = memory_manager.get_active_live_session()
    if record is not None:
        return record
    session_id = _live_mission.get("session_id")
    if isinstance(session_id, str) and session_id:
        return memory_manager.get_live_session(session_id)
    return None


def _sync_live_mission_from_record(record: dict | None) -> bool:
    if not isinstance(record, dict):
        return False
    _live_mission["session_id"] = str(record.get("session_id") or "")
    _live_mission["start_time"] = str(record.get("start_time") or "")
    _live_mission["last_update"] = str(record.get("last_update") or _live_mission["start_time"] or "")
    _live_mission["commands_sent"] = int(record.get("commands_sent") or 0)
    _live_mission["distance_traveled"] = float(record.get("distance_traveled") or 0.0)
    _live_mission["hazards_detected"] = int(record.get("hazards_detected") or 0)
    _live_mission["last_hazard_state"] = False
    last_position = record.get("last_position")
    if isinstance(last_position, tuple) and len(last_position) == 3:
        _live_mission["last_position"] = last_position
    else:
        _live_mission["last_position"] = None
    return True


def _persist_live_mission(source: str = "api") -> None:
    if not _live_mission.get("session_id"):
        return
    memory_manager.update_live_session(
        str(_live_mission["session_id"]),
        start_time=str(_live_mission.get("start_time") or _now_iso()),
        last_update=str(_live_mission.get("last_update") or _now_iso()),
        commands_sent=int(_live_mission.get("commands_sent", 0)),
        distance_traveled=float(_live_mission.get("distance_traveled", 0.0)),
        hazards_detected=int(_live_mission.get("hazards_detected", 0)),
        last_position=_live_mission.get("last_position"),
        active=True,
        source=source,
    )


def _reset_live_mission(initial_status: dict | None = None) -> None:
    record = _active_live_session_record()
    if _sync_live_mission_from_record(record):
        if initial_status is not None:
            _live_mission["last_position"] = _extract_position_tuple(initial_status)
            _live_mission["last_update"] = _now_iso()
            _persist_live_mission(source="api")
        return

    _live_mission["session_id"] = str(uuid.uuid4())
    _live_mission["start_time"] = _now_iso()
    _live_mission["last_update"] = _live_mission["start_time"]
    _live_mission["commands_sent"] = 0
    _live_mission["distance_traveled"] = 0.0
    _live_mission["hazards_detected"] = 0
    _live_mission["last_hazard_state"] = False
    _live_mission["last_position"] = _extract_position_tuple(initial_status)
    memory_manager.begin_live_session(
        session_id=str(_live_mission["session_id"]),
        start_time=str(_live_mission["start_time"]),
        source="api",
    )
    _persist_live_mission(source="api")


def _update_live_mission(status: dict | None = None, *, command_sent: bool = False) -> None:
    current_session_id = str(_live_mission.get("session_id") or "")
    if current_session_id:
        current_record = memory_manager.get_live_session(current_session_id)
        if current_record is not None and not bool(current_record.get("active")):
            _live_mission["session_id"] = ""

    if not _live_mission.get("session_id"):
        _reset_live_mission(status)

    if command_sent:
        _live_mission["commands_sent"] = int(_live_mission.get("commands_sent", 0)) + 1

    current_position = _extract_position_tuple(status)
    last_position = _live_mission.get("last_position")
    if current_position is not None:
        if isinstance(last_position, tuple) and len(last_position) == 3:
            dx = float(current_position[0]) - float(last_position[0])
            dy = float(current_position[1]) - float(last_position[1])
            dz = float(current_position[2]) - float(last_position[2])
            delta = math.sqrt(dx * dx + dy * dy + dz * dz)
            if delta > 0:
                _live_mission["distance_traveled"] = float(_live_mission.get("distance_traveled", 0.0)) + delta
        _live_mission["last_position"] = current_position

    hazard_now = bool((status or {}).get("hazard_detected", False))
    if hazard_now and not bool(_live_mission.get("last_hazard_state", False)):
        _live_mission["hazards_detected"] = int(_live_mission.get("hazards_detected", 0)) + 1
    _live_mission["last_hazard_state"] = hazard_now
    _live_mission["last_update"] = _now_iso()
    _persist_live_mission(source="api")


def _get_live_mission_snapshot() -> dict:
    if not _live_mission.get("session_id"):
        if not _sync_live_mission_from_record(_active_live_session_record()):
            _reset_live_mission(None)
    return {
        "session_id": _live_mission.get("session_id", ""),
        "start_time": _live_mission.get("start_time", ""),
        "last_update": _live_mission.get("last_update", ""),
        "commands_sent": int(_live_mission.get("commands_sent", 0)),
        "distance_traveled": float(_live_mission.get("distance_traveled", 0.0)),
        "hazards_detected": int(_live_mission.get("hazards_detected", 0)),
        "last_position": _live_mission.get("last_position"),
    }


def _extract_first_number(text: str, patterns: list[str]) -> float | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                return float(m.group(1))
            except Exception:
                return None
    return None


def _extract_command_text(payload: dict) -> tuple[str, str | None]:
    """
    Accept multiple common payload shapes for command compatibility.
    """
    text = ""
    user_id = None
    if isinstance(payload, dict):
        for key in ("text", "command", "query", "prompt", "message"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                text = val.strip()
                break
        if not text:
            nested = payload.get("input")
            if isinstance(nested, str) and nested.strip():
                text = nested.strip()
            elif isinstance(nested, dict):
                for key in ("text", "command", "query", "prompt", "message"):
                    val = nested.get(key)
                    if isinstance(val, str) and val.strip():
                        text = val.strip()
                        break
        uid = payload.get("user_id")
        if uid is not None:
            user_id = str(uid)
    return text, user_id


def _parse_drive_command(text: str) -> dict | None:
    """
    Parse simple natural-language drive commands.
    Returns {linear, angular, duration, action} or None.
    """
    t = (text or "").strip().lower()
    if not t:
        return None

    if "stop" in t or "halt" in t:
        return {"linear": 0.0, "angular": 0.0, "duration": 0.1, "action": "stop"}

    meters = _extract_first_number(t, [
        r"([\d.]+)\s*(?:m|meter|meters)\b",
    ])
    seconds = _extract_first_number(t, [
        r"for\s+([\d.]+)\s*(?:s|sec|secs|second|seconds)\b",
        r"([\d.]+)\s*(?:s|sec|secs|second|seconds)\b",
    ])
    degrees = _extract_first_number(t, [
        r"([\d.]+)\s*(?:deg|degree|degrees)\b",
    ])

    # Forward / backward translation
    if any(k in t for k in ("forward", "ahead", "backward", "back")):
        linear = -0.35 if any(k in t for k in ("backward", "back")) else 0.35
        if seconds is not None:
            duration = seconds
        elif meters is not None:
            duration = meters / max(0.01, abs(linear))
        else:
            duration = 2.0
        duration = max(0.1, min(30.0, float(duration)))
        return {"linear": linear, "angular": 0.0, "duration": duration, "action": "move"}

    # Left / right rotation
    if any(k in t for k in ("turn left", "left")) or any(k in t for k in ("turn right", "right")):
        angular = 0.35 if "left" in t else -0.35
        if seconds is not None:
            duration = seconds
        elif degrees is not None:
            duration = math.radians(degrees) / max(0.01, abs(angular))
        else:
            duration = 1.5
        duration = max(0.1, min(20.0, float(duration)))
        return {"linear": 0.0, "angular": angular, "duration": duration, "action": "turn"}

    # Generic movement phrases like "move rover" / "drive rover"
    if any(k in t for k in ("move", "drive", "go")):
        linear = 0.35
        if "back" in t or "reverse" in t or "backward" in t:
            linear = -0.35
        if seconds is not None:
            duration = seconds
        elif meters is not None:
            duration = meters / max(0.01, abs(linear))
        else:
            duration = 3.0
        duration = max(0.1, min(30.0, float(duration)))
        return {"linear": linear, "angular": 0.0, "duration": duration, "action": "move"}

    return None


def _should_try_hermes(text: str) -> bool:
    """
    Route anything beyond a simple direct drive phrase through Hermes.
    """
    t = (text or "").strip().lower()
    if not t:
        return False

    complex_markers = (
        "photo",
        "picture",
        "image",
        "camera",
        "mastcam",
        "navcam",
        "hazcam",
        "scan",
        "lidar",
        "explore",
        "autonomous",
        "autonomously",
        "survey",
        "mission",
        "hazard",
        "terrain",
        "report",
        "summary",
        "remember",
        "learn",
        "avoid",
        "analyze",
        "analyse",
        "assess",
        "waypoint",
        "navigate",
    )
    if any(marker in t for marker in complex_markers):
        return True

    return _parse_drive_command(text) is None


async def _run_hermes_command(
    text: str,
    user_id: str | None = None,
    mission_context: dict | None = None,
) -> dict | None:
    try:
        from hermes_rover.mission_agent import run_hermes_command
    except Exception:
        return None
    return await run_hermes_command(text, user_id=user_id, mission_context=mission_context)


def _build_hermes_mission_context(text: str, telemetry: dict | None = None) -> dict:
    live = _get_live_mission_snapshot()
    lowered = (text or "").strip().lower()
    intent = "general"
    if "explore" in lowered or "autonomous" in lowered:
        intent = "explore"
    elif "navigate" in lowered or "waypoint" in lowered or "move to" in lowered:
        intent = "navigate"
    elif "avoid" in lowered or "hazard" in lowered or "obstacle" in lowered:
        intent = "avoid"
    elif "survey" in lowered or "scan" in lowered or "assess" in lowered:
        intent = "survey"
    hazard_flag = "hazard_unknown"
    if isinstance(telemetry, dict):
        hazard_flag = "hazard_on" if bool(telemetry.get("hazard_detected", False)) else "hazard_off"
    return {
        "session_id": str(live.get("session_id") or ""),
        "telemetry": telemetry if isinstance(telemetry, dict) else None,
        "context_signature": f"intent:{intent} | {hazard_flag}",
    }


async def _bridge_drive(linear: float, angular: float, duration: float) -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{BRIDGE_URL.rstrip('/')}/drive",
                json={"linear": linear, "angular": angular, "duration": duration},
                timeout=aiohttp.ClientTimeout(total=max(15, int(duration) + 10)),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception:
        return None


async def _bridge_status() -> dict | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{BRIDGE_URL.rstrip('/')}/",
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.json()
    except Exception:
        return None


def _is_report_to_telegram_command(text: str) -> bool:
    t = (text or "").lower()
    return ("report" in t or "summary" in t) and ("telegram" in t or "tg" in t)


def _resolve_telegram_chat_id(explicit_user_id: str | None = None) -> str | None:
    if explicit_user_id and str(explicit_user_id).strip().lstrip("-").isdigit():
        return str(explicit_user_id).strip()

    allowed = os.environ.get("TELEGRAM_ALLOWED_USERS", "").strip()
    if allowed:
        for part in allowed.split(","):
            p = part.strip()
            if p and p.lstrip("-").isdigit():
                return p
    return None


async def _send_telegram_pdf(chat_id: str, pdf_bytes: bytes) -> tuple[bool, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN is not configured."

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    data.add_field(
        "document",
        pdf_bytes,
        filename="mars_rover_report.pdf",
        content_type="application/pdf",
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return False, f"Telegram sendDocument failed ({resp.status}): {body[:200]}"
                return True, "PDF sent to Telegram."
    except Exception as e:
        return False, f"Telegram sendDocument error: {e}"


async def _send_telegram_text(chat_id: str, text: str) -> tuple[bool, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        return False, "TELEGRAM_BOT_TOKEN is not configured."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": str(chat_id), "text": text[:3500]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return False, f"Telegram sendMessage failed ({resp.status}): {body[:200]}"
                return True, "Text report sent to Telegram."
    except Exception as e:
        return False, f"Telegram sendMessage error: {e}"


async def _send_report_to_telegram(explicit_user_id: str | None = None) -> tuple[bool, str]:
    chat_id = _resolve_telegram_chat_id(explicit_user_id)
    if not chat_id:
        return False, "No Telegram chat_id available (set TELEGRAM_ALLOWED_USERS or pass user_id)."

    report_text = await _build_report_text()
    if _PDF_AVAILABLE:
        try:
            pdf_bytes = _report_text_to_pdf_bytes(report_text)
            ok, msg = await _send_telegram_pdf(chat_id, pdf_bytes)
            if ok:
                return True, msg
            # fall through to text fallback if PDF upload fails
        except Exception:
            pass
    return await _send_telegram_text(chat_id, report_text)


def _parse_skill_frontmatter(content: str) -> dict:
    """Extract name and description from YAML frontmatter."""
    out = {"name": "", "description": ""}
    m = re.search(r"---\s*\n([\s\S]*?)\n---", content)
    if not m:
        return out
    block = m.group(1)
    nm = re.search(r"^name:\s*(.+)$", block, re.M)
    desc = re.search(r"^description:\s*(.+)$", block, re.M)
    if nm:
        out["name"] = nm.group(1).strip().strip('"')
    if desc:
        out["description"] = desc.group(1).strip().strip('"')
    return out


def _default_telemetry_payload() -> dict:
    return {
        "position": {"x": 0, "y": 0, "z": 0},
        "orientation": {"roll": 0, "pitch": 0, "yaw": 0},
        "velocity": {"linear": 0, "angular": 0},
        "hazard_detected": False,
        "uptime_seconds": 0,
        "sim_connected": False,
    }


def _fallback_telemetry_payload(last_payload: dict | None, *, sim_connected: bool | None = None) -> dict:
    payload = dict(last_payload) if isinstance(last_payload, dict) else _default_telemetry_payload()
    payload.setdefault("position", {"x": 0, "y": 0, "z": 0})
    payload.setdefault("orientation", {"roll": 0, "pitch": 0, "yaw": 0})
    payload.setdefault("velocity", {"linear": 0, "angular": 0})
    payload.setdefault("hazard_detected", False)
    payload.setdefault("uptime_seconds", 0)
    if sim_connected is not None:
        payload["sim_connected"] = sim_connected
    else:
        payload.setdefault("sim_connected", False)
    return payload


def _dedupe_sessions_by_id(sessions: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen_ids: set[str] = set()
    for session in sessions:
        sid = str(session.get("session_id") or "").strip()
        if sid:
            if sid in seen_ids:
                continue
            seen_ids.add(sid)
        unique.append(session)
    return unique


@app.get("/status")
async def get_status():
    """Proxy GET bridge/ for rover telemetry."""
    status = await _bridge_status()
    if status is None:
        raise HTTPException(status_code=502, detail="Bridge unavailable")
    _update_live_mission(status)
    return status


@app.get("/telemetry")
async def get_telemetry():
    """Alias for /status (backward compatibility)."""
    return await get_status()


@app.get("/rover/state")
async def get_rover_state():
    """Alias for /status (backward compatibility)."""
    return await get_status()


@app.get("/sensors")
async def get_sensors():
    """Alias for /status (backward compatibility)."""
    return await get_status()


def _transcribe_audio_sync(path: str) -> str:
    """Run whisper CLI on file; return transcribed text or empty string."""
    try:
        result = subprocess.run(
            ["whisper", path, "--output_format", "txt", "--output_dir", os.path.dirname(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return ""
        txt_path = path.rsplit(".", 1)[0] + ".txt"
        if os.path.isfile(txt_path):
            return Path(txt_path).read_text(encoding="utf-8", errors="ignore").strip()
        return ""
    except Exception:
        return ""


@app.post("/command")
async def post_command(payload: dict):
    """Handle simple drive commands directly; queue everything else."""
    text, user_id = _extract_command_text(payload)

    if _is_report_to_telegram_command(text):
        ok, msg = await _send_report_to_telegram(user_id)
        return {"response": msg, "status": "completed" if ok else "error"}

    parsed = _parse_drive_command(text)
    hermes_result = None

    if _should_try_hermes(text):
        before_status = await _bridge_status()
        if before_status is not None:
            _update_live_mission(before_status)
        hermes_result = await _run_hermes_command(
            text,
            user_id,
            mission_context=_build_hermes_mission_context(text, before_status),
        )
        if hermes_result and hermes_result.get("status") in {"completed", "partial"} and hermes_result.get("response"):
            status = await _bridge_status()
            if status is not None:
                _update_live_mission(status, command_sent=True)
            else:
                _update_live_mission(None, command_sent=True)
            return {
                "response": hermes_result["response"],
                "status": hermes_result["status"],
            }

    if parsed:
        before_status = await _bridge_status()
        if before_status is not None:
            _update_live_mission(before_status)
        result = await _bridge_drive(parsed["linear"], parsed["angular"], parsed["duration"])
        if result is not None:
            status = await _bridge_status()
            if status is not None:
                _update_live_mission(status, command_sent=True)
            else:
                _update_live_mission(None, command_sent=True)
            pos = (status or {}).get("position", {})
            pos_note = ""
            if pos:
                pos_note = f" | position x={float(pos.get('x', 0.0)):.2f}, y={float(pos.get('y', 0.0)):.2f}"
            return {
                "response": (
                    f"Executed {parsed['action']}: "
                    f"linear={parsed['linear']:.2f}, angular={parsed['angular']:.2f}, "
                    f"duration={parsed['duration']:.2f}s{pos_note}"
                ),
                "status": "completed",
            }
        return {
            "response": "Drive command parsed, but bridge /drive is unreachable.",
            "status": "error",
        }

    if hermes_result:
        return {
            "response": hermes_result.get("response") or hermes_result.get("error") or "Hermes mission execution failed.",
            "status": hermes_result.get("status", "error"),
        }

    return {
        "response": (
            "Unsupported command for direct API execution. "
            "Use explicit move/turn/stop phrases or run it through Hermes rover tools."
        ),
        "status": "unsupported",
    }


@app.post("/drive")
async def post_drive(body: DriveBody):
    """
    Compatibility endpoint used by some Hermes flows.
    Proxies directly to bridge /drive.
    """
    before_status = await _bridge_status()
    if before_status is not None:
        _update_live_mission(before_status)
    result = await _bridge_drive(body.linear, body.angular, body.duration)
    if result is None:
        raise HTTPException(status_code=502, detail="Bridge /drive unavailable")
    after_status = await _bridge_status()
    if after_status is not None:
        _update_live_mission(after_status, command_sent=True)
    else:
        _update_live_mission(None, command_sent=True)
    return result


@app.post("/transcribe")
async def post_transcribe(audio: UploadFile = File(..., description="Audio file (e.g. OGG from Telegram)")):
    """Transcribe audio via whisper CLI. Returns {"text": "..."}."""
    suffix = Path(audio.filename or "audio.ogg").suffix or ".ogg"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _transcribe_audio_sync, tmp_path)
        return {"text": text}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.get("/sessions")
async def get_sessions():
    """List recent sessions from rover memory DB."""
    sessions = memory_manager.get_sessions(limit=50)
    live = _active_live_session_record()
    if live is not None and not any((s.get("session_id") or "") == live.get("session_id") for s in sessions):
        sessions = [{
            "session_id": str(live.get("session_id") or ""),
            "start_time": str(live.get("start_time") or ""),
            "end_time": None,
            "distance_traveled": float(live.get("distance_traveled") or 0.0),
            "photos_taken": 0,
            "hazards_encountered": int(live.get("hazards_detected") or 0),
            "skills_used": "live",
            "summary": "Live mission telemetry",
        }, *sessions]
    return {"sessions": _dedupe_sessions_by_id(sessions)}


@app.get("/session/live")
async def get_live_session():
    """Return current live mission tracker state (API runtime session)."""
    status = await _bridge_status()
    if status is not None:
        _update_live_mission(status)
    return {"live_session": _get_live_mission_snapshot()}


@app.post("/session/live/reset")
async def reset_live_session():
    """Reset live mission tracker state and start a fresh runtime session."""
    status = await _bridge_status()
    _reset_live_mission(status)
    return {"status": "reset", "live_session": _get_live_mission_snapshot()}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific session by ID."""
    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM session_log WHERE session_id = ? ORDER BY start_time DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    conn.close()
    if not row:
        live = memory_manager.get_live_session(session_id)
        if live is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return {
            "session_id": str(live.get("session_id") or ""),
            "start_time": str(live.get("start_time") or ""),
            "end_time": None,
            "distance_traveled": float(live.get("distance_traveled") or 0.0),
            "photos_taken": 0,
            "hazards_encountered": int(live.get("hazards_detected") or 0),
            "skills_used": str(live.get("source") or "live"),
            "summary": "Live mission telemetry",
        }
    return dict(row)


@app.get("/hazards")
async def get_hazards():
    """Return all hazards from hazard_map."""
    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM hazard_map ORDER BY discovered_at DESC").fetchall()
    conn.close()
    return {"hazards": [dict(r) for r in rows]}


@app.get("/hazards/nearby")
async def get_hazards_nearby(x: float = 0.0, y: float = 0.0, radius: float = 10.0):
    """Return hazards within radius of (x, y)."""
    hazards = memory_manager.get_nearby_hazards(x, y, radius)
    return {"hazards": hazards}


@app.post("/storm/activate")
async def storm_activate():
    """Set global storm flag to True."""
    global _storm_active
    _storm_active = True
    return {"status": "storm activated"}


@app.post("/storm/deactivate")
async def storm_deactivate():
    """Set global storm flag to False."""
    global _storm_active
    _storm_active = False
    return {"status": "storm deactivated"}


@app.get("/skills")
async def get_skills():
    """List SKILL.md files with name and description from frontmatter."""
    skills = []
    if not SKILLS_DIR.exists():
        return {"skills": skills}
    for path in sorted(SKILLS_DIR.rglob("SKILL.md")):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            meta = _parse_skill_frontmatter(content)
            skills.append({
                "name": meta["name"] or path.parent.name,
                "description": meta["description"],
                "path": str(path.relative_to(ROOT)),
            })
        except Exception:
            skills.append({"name": path.parent.name, "description": "", "path": str(path.relative_to(ROOT))})
    return {"skills": skills}


@app.get("/behaviors")
async def get_behaviors():
    """Return learned behaviors sorted by success_count DESC."""
    behaviors = memory_manager.get_learned_behaviors()
    return {"behaviors": behaviors}


async def _build_report_text() -> str:
    """Build a plain-text session report from latest sessions and optional bridge status."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    lines = [
        "HERMES Mars Rover - Session Report",
        "=" * 40,
        f"Generated at: {generated_at}",
    ]
    sessions = memory_manager.get_sessions(limit=10)
    if not sessions:
        lines.append("No sessions recorded yet.")
    else:
        for i, s in enumerate(sessions[:5], 1):
            sid = (s.get("session_id") or "unknown")[:8]
            start = (s.get("start_time") or "")[:19]
            end = (s.get("end_time") or "")[:19]
            dist = s.get("distance_traveled") or 0
            hazards = s.get("hazards_encountered") or 0
            skills = s.get("skills_used") or "-"
            summary = (s.get("summary") or "-").strip() or "-"
            lines.append(f"\nSession {i} ({sid}...)")
            lines.append(f"  Start: {start}  End: {end}")
            lines.append(f"  Distance: {dist:.1f} m  Hazards: {hazards}  Skills: {skills}")
            lines.append(f"  Summary: {summary}")
    status = await _bridge_status()
    if status is not None:
        _update_live_mission(status)
    live = _get_live_mission_snapshot()
    lines.append("\n--- Live Mission (Current API Runtime) ---")
    lines.append(f"Mission ID: {str(live.get('session_id', ''))[:8]}...")
    lines.append(f"Started: {(live.get('start_time') or '')[:19]}  Last update: {(live.get('last_update') or '')[:19]}")
    lines.append(
        "Tracked: "
        f"distance={float(live.get('distance_traveled', 0.0)):.2f} m, "
        f"commands={int(live.get('commands_sent', 0))}, "
        f"hazards={int(live.get('hazards_detected', 0))}"
    )
    if status is not None:
        pos = status.get("position", {})
        vel = status.get("velocity", {})
        lines.append("\n--- Current status ---")
        lines.append(f"Position: x={pos.get('x', 0):.2f} y={pos.get('y', 0):.2f} z={pos.get('z', 0):.2f}")
        lines.append(f"Speed: {vel.get('linear', 0):.2f} m/s  Sim connected: {status.get('sim_connected', False)}")
    else:
        lines.append("\n(Bridge unreachable for live status)")
    return "\n".join(lines)


REPORTS_DIR = ROOT / "reports"
HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
DOCUMENT_CACHE_DIR = HERMES_HOME / "document_cache"


def _save_report_to_reports_dir(content: str) -> None:
    """Write report to reports/session_report_YYYYMMDD_HHMMSS.txt."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"session_report_{stamp}.txt"
    path.write_text(content, encoding="utf-8")


def _save_pdf_to_document_cache(pdf_bytes: bytes) -> Path:
    """Persist a report PDF under ~/.hermes/document_cache and return absolute path."""
    DOCUMENT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = (DOCUMENT_CACHE_DIR / f"mars_rover_report_{stamp}.pdf").resolve()
    path.write_bytes(pdf_bytes)
    return path


@app.get("/report")
@app.post("/report")
async def report():
    """Return a plain-text session report (for Telegram /report and dashboard). Saves a copy to reports/."""
    text = await _build_report_text()
    try:
        _save_report_to_reports_dir(text)
    except Exception:
        pass
    return PlainTextResponse(text)


def _report_text_to_pdf_bytes(text: str) -> bytes:
    """Convert report text to PDF using fpdf2. Raises if fpdf2 not available."""
    if not _PDF_AVAILABLE:
        raise RuntimeError("fpdf2 not installed")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.replace("\r", "").split("\n"):
        # Core Helvetica font in fpdf2 only supports Latin-1.
        # Replace unsupported Unicode characters (e.g. em dash, emoji)
        # so report generation never fails with a 503.
        safe_line = line.encode("latin-1", "replace").decode("latin-1")
        # Reset X for each line so width=0 always means "full printable width".
        # Without this, repeated multi_cell(0, ...) can run out of horizontal space.
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 6, safe_line)

    out = pdf.output()
    if isinstance(out, bytearray):
        return bytes(out)
    if isinstance(out, bytes):
        return out
    if isinstance(out, str):
        return out.encode("latin-1", "replace")
    raise RuntimeError(f"Unexpected PDF output type: {type(out).__name__}")


@app.get("/report/pdf")
async def report_pdf():
    """Return session report as PDF. Returns 503 if fpdf2 is not installed."""
    if not _PDF_AVAILABLE:
        raise HTTPException(status_code=503, detail="PDF generation not available (install fpdf2)")
    text = await _build_report_text()
    try:
        pdf_bytes = _report_text_to_pdf_bytes(text)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=mars_rover_report.pdf"},
    )


@app.get("/report/pdf/save")
async def report_pdf_save():
    """
    Generate session report PDF, persist it in ~/.hermes/document_cache,
    and return the absolute file path for MEDIA:<path> delivery.
    """
    if not _PDF_AVAILABLE:
        raise HTTPException(status_code=503, detail="PDF generation not available (install fpdf2)")
    text = await _build_report_text()
    try:
        pdf_bytes = _report_text_to_pdf_bytes(text)
        saved_path = _save_pdf_to_document_cache(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {
        "success": True,
        "path": str(saved_path),
    }


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """Stream rover telemetry to connected clients every 200ms."""
    await websocket.accept()
    last_payload: dict | None = None
    last_ok_at = 0.0
    try:
        async with aiohttp.ClientSession() as session:
            while True:
                payload: dict | None = None
                try:
                    async with session.get(
                        f"{BRIDGE_URL.rstrip('/')}/",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            payload = await resp.json()
                except Exception:
                    payload = None

                if payload is not None:
                    last_payload = payload
                    last_ok_at = time.monotonic()
                    _update_live_mission(payload)
                    await websocket.send_json(payload)
                else:
                    stale = (time.monotonic() - last_ok_at) >= WS_BRIDGE_STALE_GRACE_SEC
                    await websocket.send_json(
                        _fallback_telemetry_payload(last_payload, sim_connected=False if stale else None)
                    )
                await asyncio.sleep(WS_STREAM_INTERVAL_SEC)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
