"""
Hazard detection for Mars rover: tilt, storm.
Fetches sensor data from bridge GET / and runs checks.
"""
import aiohttp

TILT_WARNING_RAD = 0.35  # ~20 deg
TILT_CRITICAL_RAD = 0.52  # ~30 deg


class HazardDetector:
    """Detect tilt and storm hazards from bridge sensor data."""

    def __init__(self, bridge_url: str = "http://localhost:8765"):
        self.bridge_url = bridge_url.rstrip("/")
        self._storm_active = False

    @property
    def storm_active(self) -> bool:
        return self._storm_active

    @storm_active.setter
    def storm_active(self, value: bool) -> None:
        self._storm_active = bool(value)

    async def check_tilt(self, sensor_data: dict) -> dict | None:
        """If roll or pitch > 0.35 rad (20 deg) return warning; > 0.52 rad (30 deg) return critical."""
        orient = sensor_data.get("orientation", {})
        roll = float(orient.get("roll", 0))
        pitch = float(orient.get("pitch", 0))
        max_tilt = max(abs(roll), abs(pitch))
        if max_tilt >= TILT_CRITICAL_RAD:
            return {
                "type": "tilt",
                "severity": "critical",
                "action": "STOP immediately. Tilt exceeds 30 deg. Reverse to safer terrain.",
                "details": {"roll_rad": roll, "pitch_rad": pitch, "roll_deg": round(roll * 57.3, 1), "pitch_deg": round(pitch * 57.3, 1)},
            }
        if max_tilt >= TILT_WARNING_RAD:
            return {
                "type": "tilt",
                "severity": "warning",
                "action": "Reduce speed. Tilt exceeds 20 deg. Consider reversing.",
                "details": {"roll_rad": roll, "pitch_rad": pitch, "roll_deg": round(roll * 57.3, 1), "pitch_deg": round(pitch * 57.3, 1)},
            }
        return None

    async def check_storm(self) -> dict | None:
        """Return hazard if storm_active; else None."""
        if self.storm_active:
            return {
                "type": "storm",
                "severity": "critical",
                "action": "DUST STORM ACTIVE. Park rover, lower mast, enter low-power mode. Alert operator.",
                "details": {"storm_active": True},
            }
        return None

    async def get_all_hazards(self) -> list[dict]:
        """Fetch bridge GET /, run tilt and storm checks, return list of hazards."""
        hazards: list[dict] = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.bridge_url}/",
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return hazards
                    sensor_data = await resp.json()
        except Exception:
            return hazards
        tilt = await self.check_tilt(sensor_data)
        if tilt:
            hazards.append(tilt)
        storm = await self.check_storm()
        if storm:
            hazards.append(storm)
        return hazards
