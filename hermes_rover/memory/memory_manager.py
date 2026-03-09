"""
Extended memory manager for Mars Rover.
Stores: terrain maps, hazard locations, session logs, learned behaviors.
Hermes Agent's built-in memory handles conversation memory.
This module adds rover-specific structured memory.
"""
import os
import sqlite3
from datetime import datetime

_root = os.environ.get("HERMES_PROJECT_ROOT")
if not _root:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(_root, "hermes_rover", "memory", "rover_memory.db")


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS hazard_map (
        id INTEGER PRIMARY KEY,
        x REAL, y REAL,
        hazard_type TEXT,
        severity TEXT,
        description TEXT,
        discovered_at TEXT,
        session_id TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS terrain_log (
        id INTEGER PRIMARY KEY,
        x REAL, y REAL,
        terrain_type TEXT,
        traversability REAL,
        notes TEXT,
        timestamp TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS session_log (
        id INTEGER PRIMARY KEY,
        session_id TEXT,
        start_time TEXT,
        end_time TEXT,
        distance_traveled REAL,
        photos_taken INTEGER,
        hazards_encountered INTEGER,
        skills_used TEXT,
        summary TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS learned_behaviors (
        id INTEGER PRIMARY KEY,
        trigger TEXT,
        action TEXT,
        success_count INTEGER DEFAULT 0,
        failure_count INTEGER DEFAULT 0,
        last_used TEXT,
        source_session TEXT
    )""")
    conn.commit()
    conn.close()


def log_hazard(x: float, y: float, hazard_type: str, severity: str, description: str, session_id: str):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO hazard_map (x, y, hazard_type, severity, description, discovered_at, session_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (x, y, hazard_type, severity, description, datetime.now().isoformat(), session_id or ""),
    )
    conn.commit()
    conn.close()


def get_nearby_hazards(x: float, y: float, radius: float = 10.0) -> list[dict]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM hazard_map WHERE ABS(x - ?) <= ? AND ABS(y - ?) <= ?",
        (x, radius, y, radius),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_terrain(x: float, y: float, terrain_type: str, traversability: float, notes: str = ""):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO terrain_log (x, y, terrain_type, traversability, notes, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (x, y, terrain_type, traversability, notes, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def log_session(
    session_id: str,
    start_time: str,
    end_time: str,
    distance_traveled: float = 0.0,
    photos_taken: int = 0,
    hazards_encountered: int = 0,
    skills_used: str = "",
    summary: str = "",
):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO session_log (session_id, start_time, end_time, distance_traveled, photos_taken, hazards_encountered, skills_used, summary) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (session_id, start_time, end_time, distance_traveled, photos_taken, hazards_encountered, skills_used, summary),
    )
    conn.commit()
    conn.close()


def get_sessions(limit: int = 50) -> list[dict]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM session_log ORDER BY start_time DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_learned_behavior(trigger: str, action: str, session_id: str = ""):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO learned_behaviors (trigger, action, last_used, source_session) VALUES (?, ?, ?, ?)",
        (trigger, action, datetime.now().isoformat(), session_id or ""),
    )
    conn.commit()
    conn.close()


def get_learned_behaviors() -> list[dict]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM learned_behaviors ORDER BY success_count DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def increment_behavior_success(id: int):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE learned_behaviors SET success_count = success_count + 1, last_used = ? WHERE id = ?",
        (datetime.now().isoformat(), id),
    )
    conn.commit()
    conn.close()


def increment_behavior_failure(id: int):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE learned_behaviors SET failure_count = failure_count + 1, last_used = ? WHERE id = ?",
        (datetime.now().isoformat(), id),
    )
    conn.commit()
    conn.close()
