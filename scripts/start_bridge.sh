#!/usr/bin/env bash
# Start headless sensor bridge (FastAPI on port 8765).
# Run from repo root, or the script will cd to repo root.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

export GZ_SIM_RESOURCE_PATH="${GZ_SIM_RESOURCE_PATH:-$REPO_ROOT/simulation/models}"
export PYTHONPATH="${REPO_ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Source ROS 2 so gz is on PATH
if [ -f /opt/ros/humble/setup.bash ]; then
  source /opt/ros/humble/setup.bash
elif [ -f /opt/ros/jazzy/setup.bash ]; then
  source /opt/ros/jazzy/setup.bash
fi

exec python3 -m uvicorn bridge.sensor_bridge:app --host 0.0.0.0 --port 8765
