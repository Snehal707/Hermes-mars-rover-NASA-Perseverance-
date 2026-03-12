"""pytest: Hermes rover tools schema and memory."""
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

from hermes_rover.tools import drive_tool, sensor_tool, navigate_tool, camera_tool
from hermes_rover.memory import memory_manager
from hermes_rover.memory.session_logger import SessionLogger


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


def test_memory_manager_init():
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


def test_session_logger():
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


def test_live_session_state_roundtrip():
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


def test_session_logger_prefers_live_stats():
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


def test_session_logger_reuses_active_live_session():
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


def test_session_logger_non_finalizing_mode_leaves_live_session_active():
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
