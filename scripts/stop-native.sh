#!/usr/bin/env bash
# Stop the native (non-Docker) Sentinel stack
# Usage: ./scripts/stop-native.sh

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT/runtime/native/pids.txt"

echo ""
echo "Stopping native Sentinel stack..."

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file found — nothing to stop."
  exit 0
fi

while read -r pid; do
  if [[ "$pid" =~ ^[0-9]+$ ]]; then
    if kill "$pid" 2>/dev/null; then
      echo "  Stopped PID $pid"
    else
      echo "  PID $pid already exited"
    fi
  fi
done < "$PID_FILE"

rm -f "$PID_FILE"
echo "Done."
echo ""
