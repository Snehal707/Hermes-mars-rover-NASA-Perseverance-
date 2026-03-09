#!/usr/bin/env python3
"""
End-to-end integration test. Run with: python scripts/integration_test.py
Requires bridge (:8765) and API (:8000) to be running. Uses httpx and stdlib only.
"""
import sys
from pathlib import Path

import httpx

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
TIMEOUT = 5.0
BRIDGE = "http://localhost:8765"
API = "http://localhost:8000"


def main():
    passed = 0

    # Step 1: Bridge health
    try:
        r = httpx.get(f"{BRIDGE}/health", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "ok":
            raise ValueError(f"expected status 'ok', got {data.get('status')}")
        print("[PASS] Step 1: Bridge health")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 1: Bridge health — {e}")

    # Step 2: Bridge state
    try:
        r = httpx.get(BRIDGE + "/", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        for key in ("position", "orientation", "hazard_detected"):
            if key not in data:
                raise ValueError(f"missing key: {key}")
        print("[PASS] Step 2: Bridge state")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 2: Bridge state — {e}")

    # Step 3: Drive command
    try:
        r = httpx.post(
            f"{BRIDGE}/drive",
            json={"linear": 0.3, "angular": 0.0, "duration": 1.0},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "completed":
            raise ValueError(f"expected status 'completed', got {data.get('status')}")
        print("[PASS] Step 3: Drive command")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 3: Drive command — {e}")

    # Step 4: Sensor read
    try:
        r = httpx.get(BRIDGE + "/", timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if "position" not in data:
            raise ValueError("response has no 'position' key")
        print("[PASS] Step 4: Sensor read")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 4: Sensor read — {e}")

    # Step 5: API health
    try:
        r = httpx.get(f"{API}/status", timeout=TIMEOUT)
        if r.status_code != 200:
            raise ValueError(f"status code {r.status_code}")
        print("[PASS] Step 5: API health")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 5: API health — {e}")

    # Step 6: API command
    try:
        r = httpx.post(
            f"{API}/command",
            json={"text": "what is your status"},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            raise ValueError(f"status code {r.status_code}")
        print("[PASS] Step 6: API command")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 6: API command — {e}")

    # Step 7: Memory DB
    try:
        db_path = REPO_ROOT / "hermes_rover" / "memory" / "rover_memory.db"
        if not db_path.exists():
            raise FileNotFoundError(str(db_path))
        print("[PASS] Step 7: Memory DB")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Step 7: Memory DB — {e}")

    print(f"\n{passed}/7 tests passed")
    sys.exit(0 if passed == 7 else 1)


if __name__ == "__main__":
    main()
