"""pytest: Hermes rover tools schema and memory."""
import asyncio
import json
import os
import sqlite3
import uuid
from pathlib import Path

import pytest

# Ensure repo root on PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in os.environ.get("PYTHONPATH", ""):
    import sys
    sys.path.insert(0, str(ROOT))

from hermes_rover.tools import drive_tool, sensor_tool, navigate_tool, camera_tool, memory_tool
from hermes_rover.memory import memory_manager
from hermes_rover.memory.session_logger import SessionLogger


@pytest.fixture
def isolated_memory_db(tmp_path, monkeypatch):
    db_path = tmp_path / "rover_memory.db"
    monkeypatch.setattr(memory_manager, "DB_PATH", str(db_path))
    memory_manager.init_db()
    return db_path


def test_drive_tool_schema():
    schema = drive_tool.TOOL_SCHEMA
    assert schema["name"] == "drive_rover"
    props = schema["parameters"]["properties"]
    assert "linear_speed" in props
    assert "angular_speed" in props
    assert "duration" in props
    assert "linear_speed" in schema["parameters"]["required"]


def test_sensor_tool_schema():
    schema = sensor_tool.TOOL_SCHEMA
    assert schema["name"] == "read_sensors"
    assert "sensors" in schema["parameters"]["properties"]
    assert schema["parameters"]["properties"]["sensors"]["type"] == "array"
    assert "sensors" in schema["parameters"]["required"]


def test_navigate_tool_schema():
    schema = navigate_tool.TOOL_SCHEMA
    assert schema["name"] == "navigate_to"
    props = schema["parameters"]["properties"]
    assert "target_x" in props
    assert "target_y" in props
    assert "target_x" in schema["parameters"]["required"]
    assert "target_y" in schema["parameters"]["required"]


def test_navigate_tool_stops_when_progress_stalls(monkeypatch):
    snapshot = {
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        "velocity": {"linear": 0.0, "angular": 0.0},
        "hazard_detected": False,
        "sim_connected": True,
        "source": "bridge",
    }

    async def _noop_publish(*args, **kwargs):
        return None

    async def _noop_sleep(*args, **kwargs):
        return None

    monkeypatch.setattr(navigate_tool, "get_telemetry_snapshot", lambda prefer_bridge=True: snapshot)
    monkeypatch.setattr(navigate_tool, "_publish_for_duration", _noop_publish)
    monkeypatch.setattr(navigate_tool, "_publish_stop_burst", _noop_publish)
    monkeypatch.setattr(navigate_tool, "read_topic", lambda *args, **kwargs: "")
    monkeypatch.setattr(navigate_tool, "STALL_STEP_LIMIT", 3)
    monkeypatch.setattr(navigate_tool, "POST_MOVE_SETTLE_SEC", 0.0)
    monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

    payload = asyncio.run(navigate_tool.execute(target_x=5.0, target_y=0.0))
    data = json.loads(payload)

    assert data["status"] == "error"
    assert data["message"] == "navigation stalled"


def test_camera_tool_schema():
    schema = camera_tool.TOOL_SCHEMA
    assert schema["name"] == "capture_camera_image"
    props = schema["parameters"]["properties"]
    assert "camera" in props
    assert "camera" in schema["parameters"]["required"]


def test_camera_tool_extracts_rgb_payload():
    raw = '\n'.join([
        'width: 2',
        'height: 1',
        'step: 6',
        'data: "\\377\\000\\000\\000\\377\\000"',
    ])
    width, height, step, payload = camera_tool._extract_image_payload(raw)
    rgb = camera_tool._rgb_rows_to_bytes(width, height, step, payload)

    assert (width, height, step) == (2, 1, 6)
    assert rgb == bytes([255, 0, 0, 0, 255, 0])


def test_memory_manager_init(isolated_memory_db):
    memory_manager.init_db()
    assert Path(memory_manager.DB_PATH).exists()
    conn = sqlite3.connect(memory_manager.DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('hazard_map','session_log','terrain_log','learned_behaviors')"
    )
    tables = {row[0] for row in c.fetchall()}
    conn.close()
    assert tables == {"hazard_map", "session_log", "terrain_log", "learned_behaviors"}


def test_memory_tool_check_area_returns_hazards_and_terrain(tmp_path, monkeypatch):
    db_path = tmp_path / "rover_memory.db"
    monkeypatch.setattr(memory_manager, "DB_PATH", str(db_path))
    memory_manager.init_db()
    memory_manager.log_hazard(2.0, -1.0, "rock", "medium", "test rock", "session-1")
    memory_manager.log_terrain(2.2, -1.1, "sand", 0.6, "soft terrain")

    payload = asyncio.run(memory_tool.execute(action="check_area", x=2.0, y=-1.0, radius=1.0))
    data = json.loads(payload)

    assert data["hazards"][0]["hazard_type"] == "rock"
    assert data["terrain"][0]["terrain_type"] == "sand"


def test_session_logger(isolated_memory_db):
    logger = SessionLogger(reuse_active=False)
    logger.end_session("test")
    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM session_log WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (logger.session_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    session = dict(row)
    assert session["summary"] == "test"
    assert session["session_id"] == logger.session_id


def test_log_session_upserts_duplicate_session_id(isolated_memory_db):
    session_id = "dup-session"
    memory_manager.log_session(
        session_id=session_id,
        start_time="2026-03-13T10:00:00",
        end_time="2026-03-13T10:05:00",
        distance_traveled=1.0,
        summary="first",
    )
    memory_manager.log_session(
        session_id=session_id,
        start_time="2026-03-13T10:00:00",
        end_time="2026-03-13T10:10:00",
        distance_traveled=2.5,
        summary="second",
    )

    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM session_log WHERE session_id = ? ORDER BY id DESC",
        (session_id,),
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    row = dict(rows[0])
    assert row["summary"] == "second"
    assert row["distance_traveled"] == pytest.approx(2.5)


def test_dedupe_session_log_removes_existing_duplicates(isolated_memory_db):
    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.execute(
        "INSERT INTO session_log (session_id, start_time, end_time, distance_traveled, photos_taken, hazards_encountered, skills_used, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("dup-session", "2026-03-13T09:00:00", "2026-03-13T09:05:00", 1.0, 0, 0, "", "older"),
    )
    conn.execute(
        "INSERT INTO session_log (session_id, start_time, end_time, distance_traveled, photos_taken, hazards_encountered, skills_used, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("dup-session", "2026-03-13T10:00:00", "2026-03-13T10:05:00", 2.0, 0, 0, "", "newer"),
    )
    conn.commit()
    conn.close()

    removed = memory_manager.dedupe_session_log()
    assert removed == 1

    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM session_log WHERE session_id = ? ORDER BY id DESC",
        ("dup-session",),
    ).fetchall()
    conn.close()

    assert len(rows) == 1
    assert dict(rows[0])["summary"] == "newer"


def test_live_session_state_roundtrip(isolated_memory_db):
    session_id = f"live-{uuid.uuid4()}"
    memory_manager.begin_live_session(session_id, "9999-12-31T23:58:00", source="test")
    memory_manager.update_live_session(
        session_id,
        last_update="9999-12-31T23:59:59",
        commands_sent=3,
        distance_traveled=4.25,
        hazards_detected=2,
        last_position=(1.0, 2.0, 0.0),
        active=True,
        source="test",
    )

    live = memory_manager.get_live_session(session_id)
    assert live is not None
    assert live["commands_sent"] == 3
    assert live["distance_traveled"] == pytest.approx(4.25)
    assert live["hazards_detected"] == 2
    assert live["last_position"] == (1.0, 2.0, 0.0)
    assert live["active"] is True

    active = memory_manager.get_active_live_session()
    assert active is not None
    assert active["session_id"] == session_id

    memory_manager.finish_live_session(session_id, end_time="2026-03-12T00:02:00")
    ended = memory_manager.get_live_session(session_id)
    assert ended is not None
    assert ended["active"] is False


def test_session_logger_prefers_live_stats(isolated_memory_db):
    logger = SessionLogger(reuse_active=False)
    memory_manager.update_live_session(
        logger.session_id,
        last_update="2026-03-12T00:03:00",
        distance_traveled=7.5,
        hazards_detected=3,
        last_position=(0.5, -0.25, 0.0),
        active=True,
    )

    summary = logger.get_summary()
    assert summary["distance_accumulated"] == pytest.approx(7.5)
    assert summary["hazards_count"] == 3

    result = logger.end_session("live stats test")
    assert result["distance_traveled"] == pytest.approx(7.5)
    assert result["hazards_encountered"] == 3

    live = memory_manager.get_live_session(logger.session_id)
    assert live is not None
    assert live["active"] is False


def test_session_logger_reuses_active_live_session(isolated_memory_db):
    session_id = f"shared-{uuid.uuid4()}"
    memory_manager.begin_live_session(session_id, "9999-12-31T23:58:00", source="api")
    memory_manager.update_live_session(
        session_id,
        last_update="9999-12-31T23:59:59",
        distance_traveled=2.25,
        hazards_detected=1,
        last_position=(0.1, 0.2, 0.0),
        active=True,
        source="api",
    )

    logger = SessionLogger(source="cli", reuse_active=True, finalize_on_end=True)
    assert logger.session_id == session_id
    assert logger.start_time == "9999-12-31T23:58:00"

    result = logger.end_session("shared live session")
    assert result["session_id"] == session_id
    assert result["distance_traveled"] == pytest.approx(2.25)
    assert result["hazards_encountered"] == 1
    assert result["finalized"] is True


def test_session_logger_non_finalizing_mode_leaves_live_session_active(isolated_memory_db):
    logger = SessionLogger(source="gateway", reuse_active=False, finalize_on_end=False)
    session_id = logger.session_id

    result = logger.end_session("gateway attachment")
    assert result["session_id"] == session_id
    assert result["finalized"] is False

    live = memory_manager.get_live_session(session_id)
    assert live is not None
    assert live["active"] is True

    conn = sqlite3.connect(memory_manager.DB_PATH)
    row = conn.execute(
        "SELECT COUNT(*) FROM session_log WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 0

    memory_manager.finish_live_session(session_id, end_time="2026-03-12T00:04:00")
