"""
Session logger: tracks actions, hazards, and totals per rover session.
Writes to memory_manager SQLite tables.
"""
import uuid
from datetime import datetime

from hermes_rover.memory import memory_manager


class SessionLogger:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.now().isoformat()
        self.actions: list[dict] = []
        self.hazards: list[dict] = []
        self._distance_delta = 0.0
        self._photos_count = 0
        self._skills_used: set[str] = set()

    def log_action(self, action_type: str, details: dict):
        self.actions.append({
            "action_type": action_type,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        })
        if action_type == "move" and isinstance(details.get("distance"), (int, float)):
            self._distance_delta += float(details["distance"])
        if action_type == "photo":
            self._photos_count += 1
        if action_type == "skill":
            self._skills_used.add(details.get("skill", "") or str(details))

    def log_hazard(self, hazard_data: dict):
        self.hazards.append(hazard_data)
        memory_manager.log_hazard(
            x=float(hazard_data.get("x", 0)),
            y=float(hazard_data.get("y", 0)),
            hazard_type=str(hazard_data.get("hazard_type", "unknown")),
            severity=str(hazard_data.get("severity", "medium")),
            description=str(hazard_data.get("description", "")),
            session_id=self.session_id,
        )

    def end_session(self, summary: str) -> dict:
        end_time = datetime.now().isoformat()
        distance = self._distance_delta if self._distance_delta else 0.0
        photos = self._photos_count
        hazards_count = len(self.hazards)
        skills_str = ",".join(sorted(self._skills_used)) if self._skills_used else ""
        memory_manager.log_session(
            session_id=self.session_id,
            start_time=self.start_time,
            end_time=end_time,
            distance_traveled=distance,
            photos_taken=photos,
            hazards_encountered=hazards_count,
            skills_used=skills_str,
            summary=summary,
        )
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": end_time,
            "distance_traveled": distance,
            "photos_taken": photos,
            "hazards_encountered": hazards_count,
            "skills_used": list(self._skills_used),
            "summary": summary,
        }

    def get_summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "actions_count": len(self.actions),
            "hazards_count": len(self.hazards),
            "distance_accumulated": self._distance_delta,
            "photos_count": self._photos_count,
            "skills_used": list(self._skills_used),
        }
