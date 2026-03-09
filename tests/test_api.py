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


def test_sessions_endpoint(client):
    resp = client.get("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


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
