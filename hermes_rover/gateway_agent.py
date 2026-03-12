#!/usr/bin/env python3
"""
Gateway runner with rover session logging.
"""
import os
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path


def _project_root() -> str:
    script = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(script))


def _prepend_env_path(name: str, value: str):
    current = os.environ.get(name, "")
    parts = [value]
    if current:
        parts.append(current)
    os.environ[name] = os.path.pathsep.join(parts)


def _sync_rover_skills(root: str) -> None:
    src = Path(root) / "hermes_rover" / "skills"
    if not src.exists():
        return
    dst = Path.home() / ".hermes" / "skills" / "rover"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def main():
    root = _project_root()
    hermes_root = os.path.join(root, "hermes-agent")
    os.chdir(root)
    _prepend_env_path("PYTHONPATH", root)
    _prepend_env_path("PYTHONPATH", hermes_root)
    try:
        _sync_rover_skills(root)
    except Exception as e:
        print(f"Warning: could not sync rover skills ({e})")

    session_logger = None
    try:
        from hermes_rover.memory.session_logger import SessionLogger

        session_logger = SessionLogger(source="gateway", reuse_active=True, finalize_on_end=False)
        print(f"Gateway session started: {session_logger.session_id}")
    except Exception as e:
        print(f"Warning: gateway session logging unavailable ({e})")

    cmd = [sys.executable, "-m", "hermes_cli.main", "gateway", "run"]
    if "--replace" not in sys.argv[1:]:
        cmd.append("--replace")
    cmd.extend(sys.argv[1:])

    exit_code = 1
    run_error = None
    try:
        result = subprocess.run(cmd, cwd=hermes_root, env=os.environ)
        exit_code = result.returncode
    except Exception as e:
        run_error = e
    finally:
        if session_logger:
            try:
                started = session_logger.start_time
                ended = datetime.now().isoformat()
                session_logger.end_session(
                    f"Hermes gateway session. start={started} end={ended} exit_code={exit_code}."
                )
                print(f"Gateway session logged: {session_logger.session_id}")
            except Exception as e:
                print(f"Warning: failed to persist gateway session ({e})")

    if run_error:
        raise run_error
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
