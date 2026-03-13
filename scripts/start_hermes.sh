#!/usr/bin/env bash
# Start Hermes rover agent with custom tools and config.
# Run from repo root, or the script will cd to repo root.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Load project env vars (API keys + Telegram settings) for Hermes CLI tools.
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
fi

# If home channel is not set, default to first allowed Telegram user (DM).
if [ -z "${TELEGRAM_HOME_CHANNEL:-}" ] && [ -n "${TELEGRAM_ALLOWED_USERS:-}" ]; then
  export TELEGRAM_HOME_CHANNEL="${TELEGRAM_ALLOWED_USERS%%,*}"
fi

export GZ_SIM_RESOURCE_PATH="${GZ_SIM_RESOURCE_PATH:-$REPO_ROOT/simulation/models}"
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  export PATH="$REPO_ROOT/.venv/bin:$PATH"
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

# Source ROS 2 (optional, for gz topic if sim is running).
# Match start_sim.sh order to avoid mixing Jazzy/Humble binaries across processes.
if [ -f /opt/ros/jazzy/setup.bash ]; then
  source /opt/ros/jazzy/setup.bash
elif [ -f /opt/ros/humble/setup.bash ]; then
  source /opt/ros/humble/setup.bash
fi

# Run Hermes with rover config (loads system_prompt.md, context.md, tools from hermes_rover/tools)
exec "$PYTHON_BIN" hermes_rover/rover_agent.py
