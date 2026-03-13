"""pytest: Sensor bridge endpoints. Run with: PYTHONPATH=. pytest tests/test_bridge.py -v

Uses httpx + ASGITransport (no real server). Mocks subprocess so tests run without Gazebo.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio

# Ensure repo root on PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in os.environ.get("PYTHONPATH", ""):
    sys.path.insert(0, str(ROOT))

from bridge.sensor_bridge import app
import bridge.sensor_bridge as sensor_bridge


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run so bridge does not call real gz."""
    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("bridge.sensor_bridge.subprocess.run", mock_run):
        yield


@pytest_asyncio.fixture
async def client(mock_subprocess):
    """httpx async client against bridge app (no real server)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    """GET /health returns 200 and {\"status\": \"ok\"}."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_get_state_has_required_keys(client):
    """GET / returns JSON with position, orientation, velocity, hazard_detected, uptime_seconds."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    for key in ("position", "orientation", "velocity", "hazard_detected", "uptime_seconds"):
        assert key in data, f"missing key: {key}"


@pytest.mark.asyncio
async def test_drive_valid_returns_success(client):
    """POST /drive with linear=0.5, angular=0, duration=1.0 returns success (status completed)."""
    with patch("bridge.sensor_bridge.time.sleep"):
        resp = await client.post(
            "/drive",
            json={"linear": 0.5, "angular": 0.0, "duration": 1.0},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "completed"


@pytest.mark.asyncio
async def test_drive_out_of_range_clamped(client):
    """POST /drive with linear=5.0 is clamped; returns 200 and success."""
    with patch("bridge.sensor_bridge.time.sleep"):
        resp = await client.post(
            "/drive",
            json={"linear": 5.0, "angular": 0.0, "duration": 0},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "completed"


def test_poll_once_marks_sim_connected_when_topics_return(monkeypatch):
    topic_values = {
        sensor_bridge.ODOM_TOPIC: "position { x: 1.0 y: 2.0 z: 0.0 } linear { x: 0.2 } angular { z: 0.1 }",
        sensor_bridge.IMU_TOPIC: "orientation { x: 0.0 y: 0.0 z: 0.0 w: 1.0 }",
    }

    monkeypatch.setattr(sensor_bridge, "_read_topic", lambda topic, timeout_sec=sensor_bridge.TOPIC_TIMEOUT_SEC: topic_values.get(topic, ""))
    monkeypatch.setattr(sensor_bridge.time, "monotonic", lambda: 123.0)
    with sensor_bridge._state_lock:
        sensor_bridge._state["_start_time"] = 100.0
        sensor_bridge._state["_last_ok_time"] = 0.0

    sensor_bridge._poll_once()

    with sensor_bridge._state_lock:
        assert sensor_bridge._state["sim_connected"] is True
        assert sensor_bridge._state["position"]["x"] == pytest.approx(1.0)
        assert sensor_bridge._state["velocity"]["linear"] == pytest.approx(0.2)


def test_poll_once_uses_world_stats_heartbeat_when_telemetry_quiet(monkeypatch):
    topic_values = {
        sensor_bridge.ODOM_TOPIC: "",
        sensor_bridge.IMU_TOPIC: "",
        sensor_bridge.STATS_TOPIC: "sim_time { sec: 12 nsec: 0 }",
    }

    monkeypatch.setattr(sensor_bridge, "_read_topic", lambda topic, timeout_sec=sensor_bridge.TOPIC_TIMEOUT_SEC: topic_values.get(topic, ""))
    monkeypatch.setattr(sensor_bridge.time, "monotonic", lambda: 200.0)
    with sensor_bridge._state_lock:
        sensor_bridge._state["_start_time"] = 150.0
        sensor_bridge._state["_last_ok_time"] = 0.0
        sensor_bridge._state["orientation"] = {"roll": 1.0, "pitch": 2.0, "yaw": 3.0}
        sensor_bridge._state["hazard_detected"] = True

    sensor_bridge._poll_once()

    with sensor_bridge._state_lock:
        assert sensor_bridge._state["sim_connected"] is True
        assert sensor_bridge._state["orientation"] == {"roll": 1.0, "pitch": 2.0, "yaw": 3.0}
        assert sensor_bridge._state["hazard_detected"] is True
