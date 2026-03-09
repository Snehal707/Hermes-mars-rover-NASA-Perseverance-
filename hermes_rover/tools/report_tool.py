"""
Generate session report: distance, hazards, skills used, terrain explored, recommendations.
"""
import json
import sqlite3

from hermes_rover.memory import memory_manager

memory_manager.init_db()

TOOL_SCHEMA = {
    "name": "generate_report",
    "description": "Generate a session report: total distance, hazards found, skills used, terrain explored, recommendations.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session ID to report on. Use 'current' for most recent session.",
                "default": "current",
            },
        },
    },
}


def _build_report(session_id: str) -> dict:
    conn = sqlite3.connect(memory_manager.DB_PATH)
    conn.row_factory = sqlite3.Row
    report = {
        "session_id": session_id,
        "total_distance": 0.0,
        "hazards_found": [],
        "skills_used": [],
        "terrain_explored": [],
        "recommendations": [],
        "summary": "",
    }
    session = conn.execute(
        "SELECT * FROM session_log WHERE session_id = ? ORDER BY start_time DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if session:
        s = dict(session)
        report["total_distance"] = s.get("distance_traveled") or 0.0
        report["summary"] = s.get("summary") or ""
        skills_str = s.get("skills_used") or ""
        report["skills_used"] = [x.strip() for x in skills_str.split(",") if x.strip()]
    hazards = conn.execute(
        "SELECT hazard_type, severity, description, x, y FROM hazard_map WHERE session_id = ?",
        (session_id,),
    ).fetchall()
    report["hazards_found"] = [
        {"type": h[0], "severity": h[1], "description": h[2], "x": h[3], "y": h[4]}
        for h in hazards
    ]
    terrain = conn.execute(
        "SELECT x, y, terrain_type, traversability, notes FROM terrain_log ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()
    report["terrain_explored"] = [
        {"x": t[0], "y": t[1], "terrain_type": t[2], "traversability": t[3], "notes": t[4]}
        for t in terrain
    ]
    conn.close()

    if report["hazards_found"]:
        report["recommendations"].append(
            f"Review {len(report['hazards_found'])} hazard(s) before next traverse."
        )
    if report["terrain_explored"]:
        low = sum(1 for t in report["terrain_explored"] if (t.get("traversability") or 1) < 0.5)
        if low:
            report["recommendations"].append(
                f"{low} low-traversability terrain logged; use caution in similar areas."
            )
    report["recommendations"].append("Check rover battery and dust accumulation.")
    return report


async def execute(session_id: str = "current", **kwargs) -> str:
    sid = str(session_id or "current")
    if sid == "current":
        sessions = memory_manager.get_sessions(limit=1)
        sid = sessions[0]["session_id"] if sessions else "current"
    report = _build_report(sid)
    return json.dumps(report)
