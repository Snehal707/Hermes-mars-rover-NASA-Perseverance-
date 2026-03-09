#!/usr/bin/env python3
"""
Pre-scripted demo of Hermes rover capabilities. Good for hackathon recordings.
Starts Gazebo, bridge, API; sends predefined commands to Hermes; logs responses.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
procs: list[subprocess.Popen] = []

DEMO_COMMANDS = [
    "Check all sensors and report status",
    "Move forward 5 meters slowly",
    "Read sensors and check for hazards",
    "Navigate to coordinates 10, 5",
    "Generate a session report",
]


def load_env():
    """Load .env if present."""
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ[k.strip()] = v.strip().strip('"')


def make_env():
    """Build env with GZ_SIM_RESOURCE_PATH and PYTHONPATH."""
    load_env()
    env = os.environ.copy()
    env["GZ_SIM_RESOURCE_PATH"] = str(REPO_ROOT / "simulation" / "models")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.environ.get("PYTHONPATH", "") and f":{os.environ['PYTHONPATH']}" or "")
    return env


def unpause_world(env: dict) -> None:
    """Unpause world so drive commands can move the rover in headless mode."""
    try:
        subprocess.run(
            [
                "gz",
                "service",
                "-s",
                "/world/mars_surface/control",
                "--reqtype",
                "gz.msgs.WorldControl",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "3000",
                "--req",
                "pause: false",
            ],
            env=env,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=6,
        )
    except Exception:
        pass


def cleanup():
    """Kill all subprocesses."""
    print("\nCleaning up...")
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                p.kill()
            except ProcessLookupError:
                pass
    sys.exit(0)


def main():
    global procs
    env = make_env()
    os.chdir(REPO_ROOT)

    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    signal.signal(signal.SIGTERM, lambda s, f: cleanup())

    # 1. Start Gazebo headless
    gz = subprocess.Popen(
        ["gz", "sim", "-s", "simulation/worlds/mars_terrain.sdf"],
        env=env,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(gz)
    print("Started Gazebo (headless). Waiting 5s...")
    time.sleep(5)
    unpause_world(env)

    # 2. Start bridge
    bridge = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bridge.sensor_bridge:app", "--host", "0.0.0.0", "--port", "8765"],
        env=env,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(bridge)
    print("Started bridge. Waiting 2s...")
    time.sleep(2)

    # 3. Start API
    api = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
        env=env,
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    procs.append(api)
    print("Started API. Waiting 3s for services to be ready...")
    time.sleep(3)

    # 4. Send commands to Hermes
    print("\n--- Demo: Sending commands to Hermes ---\n")
    for i, cmd in enumerate(DEMO_COMMANDS, 1):
        print(f"[{i}/{len(DEMO_COMMANDS)}] Command: {cmd}")
        result = subprocess.run(
            ["hermes", "chat", "-q", cmd],
            capture_output=True,
            text=True,
            env=env,
            cwd=REPO_ROOT,
            timeout=120,
        )
        if result.stdout:
            print(f"  Response:\n{result.stdout[:500]}{'...' if len(result.stdout) > 500 else ''}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:200]}")
        print()
        time.sleep(1)

    print("--- Demo complete ---")
    cleanup()


if __name__ == "__main__":
    main()
