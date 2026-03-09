#!/usr/bin/env bash
# Start Mars API + Hermes Gateway for Telegram PDF report delivery.
# - Uses project .venv
# - Starts API only if not already running
# - Runs gateway in foreground with --replace

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f "$REPO_ROOT/.venv/bin/activate" ]; then
  echo "Missing virtualenv at $REPO_ROOT/.venv"
  echo "Create it first: python3.11 -m venv .venv"
  exit 1
fi

# shellcheck disable=SC1091
source "$REPO_ROOT/.venv/bin/activate"

# Load project env vars (token/user/home channel) for gateway config.
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

API_URL="${API_URL:-http://127.0.0.1:8000}"
export API_URL

# Gateway reliability: disable native reasoning to avoid "think-only" empty responses.
export HERMES_REASONING_EFFORT="${HERMES_REASONING_EFFORT:-none}"

# Avoid Telegram polling conflicts: ensure only one bot/gateway process runs.
pkill -f "telegram_bot.bot" 2>/dev/null || true
pkill -f "hermes_cli.main gateway run" 2>/dev/null || true
pkill -f "hermes_rover/gateway_agent.py" 2>/dev/null || true

# Wait briefly until previous pollers exit, so getUpdates conflict doesn't flap.
for _ in $(seq 1 20); do
  if ! pgrep -f "telegram_bot.bot|hermes_cli.main gateway run|hermes_rover/gateway_agent.py" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

API_PID=""
cleanup() {
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

api_ready() {
  curl -fsS "${API_URL}/report" >/dev/null 2>&1
}

if api_ready; then
  echo "API already running at ${API_URL}"
else
  echo "Starting API at ${API_URL} ..."
  export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
  python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 >"${REPO_ROOT}/.api.log" 2>&1 &
  API_PID="$!"

  for _ in $(seq 1 30); do
    if api_ready; then
      break
    fi
    sleep 1
  done

  if ! api_ready; then
    echo "API failed to start. Check ${REPO_ROOT}/.api.log"
    exit 1
  fi
fi

echo "Starting Hermes Gateway..."
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
python hermes_rover/gateway_agent.py --replace
