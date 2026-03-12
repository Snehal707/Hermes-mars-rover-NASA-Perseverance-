#!/usr/bin/env python3
"""
Rover agent runner: starts Hermes with custom rover tools, system prompt, and context.
Run from project root with PYTHONPATH including project root.
"""
import os
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path


def _project_root():
    """Project root (parent of hermes_rover/)."""
    script = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(script))


def _prepend_env_path(name: str, value: str):
    """Prepend a path-like env var without dropping existing entries."""
    current = os.environ.get(name, "")
    parts = [value]
    if current:
        parts.append(current)
    os.environ[name] = os.path.pathsep.join(parts)


def _sync_rover_skills(root: str) -> None:
    """
    Mirror project rover skills into ~/.hermes/skills/rover so Hermes can load them.
    """
    src = Path(root) / "hermes_rover" / "skills"
    if not src.exists():
        return
    dst = Path.home() / ".hermes" / "skills" / "rover"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def main():
    root = _project_root()
    os.chdir(root)
    _prepend_env_path("PYTHONPATH", root)
    try:
        _sync_rover_skills(root)
    except Exception as e:
        print(f"Warning: could not sync rover skills ({e})")
    if "GZ_SIM_RESOURCE_PATH" not in os.environ:
        os.environ["GZ_SIM_RESOURCE_PATH"] = os.path.join(root, "simulation", "models")

    # Hermes uses ~/.hermes/config.yaml. Copy hermes_rover/config/hermes_config.yaml there if needed.
    session_logger = None
    try:
        from hermes_rover.memory.session_logger import SessionLogger

        session_logger = SessionLogger(source="cli", reuse_active=True, finalize_on_end=True)
        print(f"Session started: {session_logger.session_id}")
    except Exception as e:
        print(f"Warning: session logging unavailable ({e})")

    exit_code = 1
    run_error = None
    try:
        result = subprocess.run(
            ["hermes", "chat"],
            cwd=root,
        )
        exit_code = result.returncode
    except Exception as e:
        run_error = e
    finally:
        if session_logger:
            try:
                started = session_logger.start_time
                ended = datetime.now().isoformat()
                session_logger.end_session(
                    f"Hermes chat session. start={started} end={ended} exit_code={exit_code}."
                )
                print(f"Session logged: {session_logger.session_id}")
            except Exception as e:
                print(f"Warning: failed to persist session ({e})")

    if run_error:
        raise run_error
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
