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
