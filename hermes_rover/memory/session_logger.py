"""
Session logger: tracks actions, hazards, and totals per rover session.
Writes to memory_manager SQLite tables.
"""
import uuid
from datetime import datetime

from hermes_rover.memory import memory_manager


class SessionLogger:
    def __init__(
        self,
        *,
        source: str = "cli",
        reuse_active: bool = True,
        finalize_on_end: bool = True,
    ):
        now = datetime.now().isoformat()
        self.source = source or "cli"
        self.reuse_active = bool(reuse_active)
        self.finalize_on_end = bool(finalize_on_end)
        self.actions: list[dict] = []
        self.hazards: list[dict] = []
        self._distance_delta = 0.0
        self._photos_count = 0
        self._skills_used: set[str] = set()
        active = memory_manager.get_active_live_session() if self.reuse_active else None
        if active is not None:
            self.session_id = str(active.get("session_id") or str(uuid.uuid4()))
            self.start_time = str(active.get("start_time") or now)
        else:
            self.session_id = str(uuid.uuid4())
            self.start_time = now
            memory_manager.begin_live_session(
                session_id=self.session_id,
                start_time=self.start_time,
                source=self.source,
            )

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
        live = memory_manager.get_live_session(self.session_id)
        distance = self._distance_delta if self._distance_delta else 0.0
        if live is not None:
            distance = max(distance, float(live.get("distance_traveled") or 0.0))
        photos = self._photos_count
        hazards_count = len(self.hazards)
        if live is not None:
            hazards_count = max(hazards_count, int(live.get("hazards_detected") or 0))
        skills_str = ",".join(sorted(self._skills_used)) if self._skills_used else ""
        result = {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": end_time,
            "distance_traveled": distance,
            "photos_taken": photos,
            "hazards_encountered": hazards_count,
            "skills_used": list(self._skills_used),
            "summary": summary,
        }
        if not self.finalize_on_end:
            result["finalized"] = False
            return result

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
        memory_manager.finish_live_session(self.session_id, end_time=end_time)
        result["finalized"] = True
        return result

    def get_summary(self) -> dict:
        live = memory_manager.get_live_session(self.session_id)
        distance = self._distance_delta
        hazards_count = len(self.hazards)
        if live is not None:
            distance = max(distance, float(live.get("distance_traveled") or 0.0))
            hazards_count = max(hazards_count, int(live.get("hazards_detected") or 0))
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "actions_count": len(self.actions),
            "hazards_count": hazards_count,
            "distance_accumulated": distance,
            "photos_count": self._photos_count,
            "skills_used": list(self._skills_used),
        }
