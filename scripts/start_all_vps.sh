#!/usr/bin/env bash
# Launch the full rover stack for a GPU VPS:
# - server-only Gazebo
# - EGL headless rendering
# - websocket visualization world

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export HERMES_SIM_WORLD="${HERMES_SIM_WORLD:-simulation/worlds/mars_terrain_websocket.sdf}"
export HERMES_SIM_SERVER_ONLY="${HERMES_SIM_SERVER_ONLY:-1}"
export HERMES_SIM_HEADLESS_RENDERING="${HERMES_SIM_HEADLESS_RENDERING:-1}"
export HERMES_SIM_REALTIME="${HERMES_SIM_REALTIME:-1}"

exec bash "$SCRIPT_DIR/start_all.sh"

