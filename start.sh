#!/usr/bin/env bash
# Sentinel AIOps — choose deployment mode
# Usage:
#   ./start.sh docker          # Docker dev (default)
#   ./start.sh docker --prod   # Docker production
#   ./start.sh native          # No Docker — full demo locally
#   ./start.sh stop            # Stop native stack

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
MODE="${1:-docker}"
ARG2="${2:-}"

case "$MODE" in
  docker)
    if [[ "$ARG2" == "--prod" ]]; then
      exec "$ROOT/scripts/start-docker.sh" --prod
    else
      exec "$ROOT/scripts/start-docker.sh"
    fi
    ;;
  native)
    exec "$ROOT/scripts/start-native.sh"
    ;;
  stop)
    exec "$ROOT/scripts/stop-native.sh"
    ;;
  *)
    echo "Usage: ./start.sh [docker|native|stop] [--prod]"
    exit 1
    ;;
esac
