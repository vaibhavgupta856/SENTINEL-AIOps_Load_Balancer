#!/usr/bin/env bash
# Sentinel AIOps — Docker deployment mode (full cluster + dashboard)
# Usage: ./scripts/start-docker.sh [--prod]

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PROD=false
if [[ "${1:-}" == "--prod" ]]; then
  PROD=true
fi

echo ""
echo "=== Sentinel AIOps — Docker mode ==="
echo ""

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH."
  exit 1
fi

if $PROD; then
  echo "Starting production stack (nginx :80, 2 orchestrator workers)..."
  docker compose -f docker-compose.prod.yml up --build -d
  echo ""
  echo "Dashboard : http://localhost"
  echo "API docs  : http://localhost/docs"
  echo ""
  echo "Stop: docker compose -f docker-compose.prod.yml down"
else
  echo "Starting development stack (Vite :5173, API :8000, 4 worker nodes)..."
  docker compose up --build
fi
