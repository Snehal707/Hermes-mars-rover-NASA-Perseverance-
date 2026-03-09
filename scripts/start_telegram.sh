#!/usr/bin/env bash
# DEPRECATED: Telegram is now handled by Hermes Gateway only.
# Keep this wrapper so old commands still work, but route to gateway.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "start_telegram.sh is deprecated."
echo "Launching gateway Telegram adapter via scripts/start_gateway_pdf.sh ..."

exec bash "$REPO_ROOT/scripts/start_gateway_pdf.sh"
