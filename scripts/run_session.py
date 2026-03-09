#!/usr/bin/env python3
"""
Orchestrate a complete rover session: Gazebo headless, bridge, API, Hermes.
On SIGINT/SIGTERM: end session, generate report, kill all subprocesses.
Usage: python run_session.py [--duration N]  # N = auto-stop after N minutes
"""
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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


# Global subprocess refs for cleanup
procs: list[subprocess.Popen] = []
session_logger = None
hermes_proc = None


def cleanup(reason: str = "SIGINT/SIGTERM"):
    """End session, optionally generate report, kill all subprocesses."""
    global session_logger, procs, hermes_proc
    print(f"\n[{reason}] Cleaning up...")
    if session_logger:
        try:
            s = session_logger.get_summary()
            summary_parts = [
                f"Session ended: {reason}.",
                f"Distance: {s.get('distance_accumulated', 0):.1f}m.",
                f"Actions: {s.get('actions_count', 0)}, hazards: {s.get('hazards_count', 0)}, photos: {s.get('photos_count', 0)}.",
            ]
            if s.get("skills_used"):
                summary_parts.append(f"Skills used: {', '.join(s['skills_used'])}.")
            session_logger.end_session(" ".join(summary_parts))
            print("Session ended and logged.")
        except Exception as e:
            print(f"Session end error: {e}")
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                p.kill()
            except ProcessLookupError:
                pass
    if hermes_proc:
        try:
            hermes_proc.terminate()
            hermes_proc.wait(timeout=3)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                hermes_proc.kill()
            except ProcessLookupError:
                pass
    sys.exit(0)


def main():
    global session_logger, procs, hermes_proc
    import argparse
    parser = argparse.ArgumentParser(description="Run full rover session: Gazebo, bridge, API, Hermes")
    parser.add_argument("--duration", type=int, metavar="N", help="Auto-stop after N minutes")
    args = parser.parse_args()

    env = make_env()
    os.chdir(REPO_ROOT)

    def handler(signum, frame):
        cleanup("SIGTERM" if signum == signal.SIGTERM else "SIGINT")

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

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
    print("Started API. Hermes will start in 3s...")
    time.sleep(3)

    # 4. Create SessionLogger
    sys.path.insert(0, str(REPO_ROOT))
    from hermes_rover.memory.session_logger import SessionLogger
    session_logger = SessionLogger()
    print(f"Session started: {session_logger.session_id}")

    # 5. Optional duration timer
    if args.duration:
        def timer():
            time.sleep(args.duration * 60)
            print(f"\nDuration {args.duration} min reached. Stopping...")
            os.kill(os.getpid(), signal.SIGTERM)

        t = threading.Thread(target=timer, daemon=True)
        t.start()

    # 6. Run Hermes chat (blocking)
    hermes_proc = subprocess.Popen(
        ["hermes", "chat"],
        env=env,
        cwd=REPO_ROOT,
    )
    globals()["hermes_proc"] = hermes_proc
    hermes_proc.wait()
    cleanup("Hermes exited")


if __name__ == "__main__":
    main()
