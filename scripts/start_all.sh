#!/usr/bin/env bash
# Master launch script: Gazebo headless, bridge, API, Hermes (foreground), Gateway.
# Run from repo root, or the script will cd to repo root.
# Press Ctrl+C to stop all services.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

source /opt/ros/humble/setup.bash 2>/dev/null || source /opt/ros/jazzy/setup.bash 2>/dev/null || true
export GZ_SIM_RESOURCE_PATH="$REPO_ROOT/simulation/models"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

SIM_WORLD="${HERMES_SIM_WORLD:-simulation/worlds/mars_terrain.sdf}"

# Free ports so we don't get "address already in use"
pkill -f "uvicorn bridge.sensor_bridge" 2>/dev/null || true
pkill -f "uvicorn api.main" 2>/dev/null || true
sleep 1

# Only one Telegram poller instance (avoid "Conflict: terminated by other getUpdates")
pkill -f "telegram_bot.bot" 2>/dev/null || true
pkill -f "hermes_cli.main gateway run" 2>/dev/null || true
pkill -f "hermes_rover/gateway_agent.py" 2>/dev/null || true
sleep 1

echo "Starting Gazebo headless..."
echo "(If Gazebo crashes with Ogre/material errors, run it alone in another terminal to debug.)"
gz sim -s "$SIM_WORLD" &
GZ_PID=$!
sleep 5
# Unpause simulation so the rover responds to drive commands immediately
gz service -s /world/mars_surface/control --reqtype gz.msgs.WorldControl --reptype gz.msgs.Boolean --timeout 3000 --req 'pause: false' 2>/dev/null || true

echo "Starting sensor bridge on :8765..."
python3 -m uvicorn bridge.sensor_bridge:app --host 0.0.0.0 --port 8765 &
BRIDGE_PID=$!
sleep 2

echo "Starting API server on :8000..."
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 3

echo "Starting Hermes Gateway (Telegram adapter)..."
bash scripts/start_gateway_pdf.sh &
GATEWAY_PID=$!
sleep 1

echo "Starting Hermes agent (foreground; Ctrl+C here stops all)..."
cleanup() {
  kill $GZ_PID $BRIDGE_PID $API_PID $GATEWAY_PID 2>/dev/null || true
}
trap cleanup EXIT SIGINT SIGTERM
exec bash scripts/start_hermes.sh
