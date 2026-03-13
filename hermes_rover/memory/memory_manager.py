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


def _dedupe_session_log_conn(conn: sqlite3.Connection) -> int:
    before = conn.total_changes
    conn.execute(
        """
        DELETE FROM session_log
        WHERE COALESCE(session_id, '') <> ''
          AND id NOT IN (
              SELECT MAX(id)
              FROM session_log
              WHERE COALESCE(session_id, '') <> ''
              GROUP BY session_id
          )
        """
    )
    return conn.total_changes - before


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
    c.execute("""CREATE TABLE IF NOT EXISTS live_session_state (
        session_id TEXT PRIMARY KEY,
        start_time TEXT,
        last_update TEXT,
        commands_sent INTEGER DEFAULT 0,
        distance_traveled REAL DEFAULT 0.0,
        hazards_detected INTEGER DEFAULT 0,
        last_position_x REAL,
        last_position_y REAL,
        last_position_z REAL,
        active INTEGER DEFAULT 1,
        source TEXT
    )""")
    _dedupe_session_log_conn(conn)
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


def get_nearby_terrain(x: float, y: float, radius: float = 10.0) -> list[dict]:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM terrain_log WHERE ABS(x - ?) <= ? AND ABS(y - ?) <= ? ORDER BY timestamp DESC",
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
    existing = None
    if str(session_id or "").strip():
        existing = conn.execute(
            "SELECT id FROM session_log WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()

    if existing:
        keep_id = int(existing[0])
        conn.execute(
            """UPDATE session_log
               SET start_time = ?, end_time = ?, distance_traveled = ?, photos_taken = ?,
                   hazards_encountered = ?, skills_used = ?, summary = ?
               WHERE id = ?""",
            (start_time, end_time, distance_traveled, photos_taken, hazards_encountered, skills_used, summary, keep_id),
        )
        conn.execute(
            "DELETE FROM session_log WHERE session_id = ? AND id <> ?",
            (session_id, keep_id),
        )
    else:
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
        """
        SELECT *
        FROM session_log
        WHERE id IN (
            SELECT MAX(id)
            FROM session_log
            WHERE COALESCE(session_id, '') <> ''
            GROUP BY session_id
            UNION ALL
            SELECT id
            FROM session_log
            WHERE COALESCE(session_id, '') = ''
        )
        ORDER BY start_time DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def dedupe_session_log() -> int:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        removed = _dedupe_session_log_conn(conn)
        conn.commit()
    except sqlite3.OperationalError:
        removed = 0
    conn.close()
    return int(removed)


def begin_live_session(session_id: str, start_time: str, source: str = ""):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT session_id FROM live_session_state WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE live_session_state SET start_time = COALESCE(start_time, ?), last_update = ?, active = 1, source = COALESCE(NULLIF(source, ''), ?) WHERE session_id = ?",
            (start_time, start_time, source, session_id),
        )
    else:
        conn.execute(
            """INSERT INTO live_session_state (
                session_id, start_time, last_update, commands_sent, distance_traveled,
                hazards_detected, last_position_x, last_position_y, last_position_z,
                active, source
            ) VALUES (?, ?, ?, 0, 0.0, 0, NULL, NULL, NULL, 1, ?)""",
            (session_id, start_time, start_time, source),
        )
    conn.commit()
    conn.close()


def update_live_session(
    session_id: str,
    *,
    start_time: str | None = None,
    last_update: str | None = None,
    commands_sent: int | None = None,
    distance_traveled: float | None = None,
    hazards_detected: int | None = None,
    last_position: tuple[float, float, float] | None = None,
    active: bool | None = None,
    source: str | None = None,
):
    init_db()
    row = get_live_session(session_id)
    if row is None:
        begin_live_session(session_id, start_time or datetime.now().isoformat(), source=source or "")
        row = get_live_session(session_id) or {}

    values = {
        "start_time": start_time if start_time is not None else row.get("start_time"),
        "last_update": last_update if last_update is not None else row.get("last_update"),
        "commands_sent": int(commands_sent) if commands_sent is not None else int(row.get("commands_sent") or 0),
        "distance_traveled": float(distance_traveled) if distance_traveled is not None else float(row.get("distance_traveled") or 0.0),
        "hazards_detected": int(hazards_detected) if hazards_detected is not None else int(row.get("hazards_detected") or 0),
        "last_position_x": float(last_position[0]) if last_position is not None else row.get("last_position_x"),
        "last_position_y": float(last_position[1]) if last_position is not None else row.get("last_position_y"),
        "last_position_z": float(last_position[2]) if last_position is not None else row.get("last_position_z"),
        "active": 1 if active is True else 0 if active is False else int(row.get("active") or 0),
        "source": source if source is not None else row.get("source") or "",
    }

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """UPDATE live_session_state
           SET start_time = ?, last_update = ?, commands_sent = ?, distance_traveled = ?,
               hazards_detected = ?, last_position_x = ?, last_position_y = ?, last_position_z = ?,
               active = ?, source = ?
           WHERE session_id = ?""",
        (
            values["start_time"],
            values["last_update"],
            values["commands_sent"],
            values["distance_traveled"],
            values["hazards_detected"],
            values["last_position_x"],
            values["last_position_y"],
            values["last_position_z"],
            values["active"],
            values["source"],
            session_id,
        ),
    )
    conn.commit()
    conn.close()


def get_live_session(session_id: str) -> dict | None:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM live_session_state WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    out = dict(row)
    if any(out.get(key) is not None for key in ("last_position_x", "last_position_y", "last_position_z")):
        out["last_position"] = (
            float(out.get("last_position_x") or 0.0),
            float(out.get("last_position_y") or 0.0),
            float(out.get("last_position_z") or 0.0),
        )
    else:
        out["last_position"] = None
    out["active"] = bool(out.get("active"))
    return out


def get_active_live_session() -> dict | None:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """SELECT * FROM live_session_state
           WHERE active = 1
           ORDER BY COALESCE(last_update, start_time) DESC, start_time DESC
           LIMIT 1"""
    ).fetchone()
    conn.close()
    if not row:
        return None
    return get_live_session(str(dict(row).get("session_id")))


def finish_live_session(session_id: str, end_time: str | None = None):
    init_db()
    when = end_time or datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE live_session_state SET active = 0, last_update = ? WHERE session_id = ?",
        (when, session_id),
    )
    conn.commit()
    conn.close()


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
