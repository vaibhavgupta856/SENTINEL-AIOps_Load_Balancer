#!/usr/bin/env bash
# Full Sentinel reset - stops native processes, clears stale registry, restarts Docker
# Usage: ./scripts/reset-cluster.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo ""
echo "=== Sentinel cluster reset ==="
echo ""

"$ROOT/scripts/stop-native.sh" || true

echo "Stopping Docker stack..."
docker compose down

REGISTRY="$ROOT/orchestrator/node_registry.json"
if [[ -f "$REGISTRY" ]]; then
  rm -f "$REGISTRY"
  echo "Removed stale node_registry.json"
fi

echo "Starting fresh Docker stack..."
docker compose up --build -d

echo ""
echo "Done. Wait ~30 seconds, then open http://localhost:5173"
echo ""
