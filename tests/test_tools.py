"""pytest: Hermes rover tools schema and memory."""
import os
import sqlite3
from pathlib import Path

import pytest

# Ensure repo root on PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in os.environ.get("PYTHONPATH", ""):
    import sys
    sys.path.insert(0, str(ROOT))

from hermes_rover.tools import drive_tool, sensor_tool, navigate_tool
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
    logger = SessionLogger()
    logger.end_session("test")
    sessions = memory_manager.get_sessions(limit=1)
    assert len(sessions) >= 1
    assert sessions[0]["summary"] == "test"
    assert sessions[0]["session_id"] == logger.session_id
