"""pytest: FastAPI endpoints. Run with: PYTHONPATH=. pytest tests/test_api.py -v"""
import os
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient
import api.main as api_main

# Ensure repo root on PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in os.environ.get("PYTHONPATH", ""):
    sys.path.insert(0, str(ROOT))

from api.main import app, _PDF_AVAILABLE, _report_text_to_pdf_bytes


@pytest.fixture
def client():
    return TestClient(app)


def test_status_endpoint(client):
    # 200 if bridge reachable, 502 if not
    resp = client.get("/status")
    assert resp.status_code in (200, 502)


def test_command_endpoint(client):
    resp = client.post("/command", json={"text": "forward 5"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert data.get("status") in ("completed", "processing", "error", "unsupported")


def test_command_endpoint_routes_complex_mission_to_hermes(client, monkeypatch):
    async def fake_bridge_status():
        return {
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
            "velocity": {"linear": 0.0, "angular": 0.0},
            "hazard_detected": False,
            "uptime_seconds": 1.0,
            "sim_connected": True,
        }

    async def fake_hermes(text: str, user_id: str | None = None, mission_context: dict | None = None):
        assert "explore" in text.lower()
        assert user_id == "42"
        assert mission_context is not None
        assert mission_context["session_id"]
        assert mission_context["telemetry"]["hazard_detected"] is False
        assert "intent:explore" in mission_context["context_signature"]
        return {
            "response": "Hermes completed the autonomous exploration sweep.",
            "status": "completed",
            "completed": True,
            "partial": False,
        }

    monkeypatch.setattr(api_main, "_bridge_status", fake_bridge_status)
    monkeypatch.setattr(api_main, "_run_hermes_command", fake_hermes)

    resp = client.post("/command", json={"text": "Explore the area autonomously.", "user_id": "42"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "Hermes completed" in data["response"]


def test_sessions_endpoint(client):
    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_sessions_endpoint_includes_active_live_session(client, monkeypatch):
    monkeypatch.setattr(api_main.memory_manager, "get_sessions", lambda limit=50: [])
    monkeypatch.setattr(
        api_main.memory_manager,
        "get_active_live_session",
        lambda: {
            "session_id": "live-session-1",
            "start_time": "2026-03-12T12:00:00",
            "distance_traveled": 1.75,
            "hazards_detected": 2,
        },
    )

    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sessions"][0]["session_id"] == "live-session-1"
    assert data["sessions"][0]["distance_traveled"] == pytest.approx(1.75)
    assert data["sessions"][0]["hazards_encountered"] == 2


def test_sessions_endpoint_dedupes_duplicate_session_ids(client, monkeypatch):
    monkeypatch.setattr(
        api_main.memory_manager,
        "get_sessions",
        lambda limit=50: [
            {
                "session_id": "dup-session",
                "start_time": "2026-03-13T12:00:00",
                "end_time": "2026-03-13T12:10:00",
                "distance_traveled": 2.0,
                "photos_taken": 0,
                "hazards_encountered": 0,
                "skills_used": "drive",
                "summary": "latest",
            },
            {
                "session_id": "dup-session",
                "start_time": "2026-03-13T11:00:00",
                "end_time": "2026-03-13T11:10:00",
                "distance_traveled": 1.0,
                "photos_taken": 0,
                "hazards_encountered": 1,
                "skills_used": "navigate",
                "summary": "older",
            },
        ],
    )
    monkeypatch.setattr(api_main.memory_manager, "get_active_live_session", lambda: None)
    monkeypatch.setattr(api_main, "_active_live_session_record", lambda: None)

    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["summary"] == "latest"


def test_hazards_endpoint(client):
    resp = client.get("/hazards")
    assert resp.status_code == 200
    data = resp.json()
    assert "hazards" in data
    assert isinstance(data["hazards"], list)


def test_storm_endpoints(client):
    resp_activate = client.post("/storm/activate")
    assert resp_activate.status_code == 200
    assert resp_activate.json().get("status") == "storm activated"

    resp_deactivate = client.post("/storm/deactivate")
    assert resp_deactivate.status_code == 200
    assert resp_deactivate.json().get("status") == "storm deactivated"


@pytest.mark.skipif(not _PDF_AVAILABLE, reason="fpdf2 not installed")
def test_pdf_report_converter_handles_unicode():
    pdf_bytes = _report_text_to_pdf_bytes("HERMES Mars Rover - Session Report\nEmoji: 😀\nDash: —")
    assert isinstance(pdf_bytes, (bytes, bytearray))
    assert bytes(pdf_bytes).startswith(b"%PDF")

@pytest.mark.skipif(not _PDF_AVAILABLE, reason="fpdf2 not installed")
def test_report_pdf_save_returns_persistent_absolute_path(client, monkeypatch, tmp_path):
    doc_cache = (tmp_path / ".hermes" / "document_cache").resolve()
    monkeypatch.setattr(api_main, "DOCUMENT_CACHE_DIR", doc_cache)

    resp = client.get("/report/pdf/save")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True

    saved_path = Path(data["path"])
    assert saved_path.is_absolute()
    assert saved_path.exists()
    assert saved_path.parent == doc_cache
    assert saved_path.suffix.lower() == ".pdf"
    assert saved_path.read_bytes().startswith(b"%PDF")
