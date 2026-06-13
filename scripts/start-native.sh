#!/usr/bin/env bash
# Sentinel AIOps — Native deployment mode (no Docker, full demo on one machine)
# Uses Python monitor_mock.py instead of C++ — works on Windows, Linux, macOS.
# Usage: ./scripts/start-native.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RUNTIME_DIR="$ROOT/runtime/native"
PID_FILE="$RUNTIME_DIR/pids.txt"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required but not found on PATH."
    exit 1
  fi
}

record_pid() {
  local label="$1"
  local pid="$2"
  echo "  [$label] PID $pid"
  echo "$pid" >> "$PID_FILE"
}

start_node() {
  local node_id="$1"
  local monitor_port="$2"
  local receiver_port="$3"
  local data_dir="$RUNTIME_DIR/$node_id"
  mkdir -p "$data_dir"

  echo "Starting $node_id (monitor :$monitor_port, API :$receiver_port)..."
  (
    export NODE_ID="$node_id"
    export NODE_HOST="127.0.0.1"
    export NODE_PORT="$receiver_port"
    export MONITOR_PORT="$monitor_port"
    export MONITOR_URL="http://127.0.0.1:$monitor_port"
    export WORKER_DATA_DIR="$data_dir"
    export ORCHESTRATOR_URL="http://127.0.0.1:8000/api/nodes/register"
    cd "$ROOT/cluster"
    python3 monitor_mock.py &
    echo $! >> "$PID_FILE"
    echo "  [$node_id-monitor] PID $!"
    sleep 0.3
    python3 receiver.py &
    echo $! >> "$PID_FILE"
    echo "  [$node_id-receiver] PID $!"
  )
}

echo ""
echo "=== Sentinel AIOps — Native mode (no Docker) ==="
echo ""

require_cmd python3
require_cmd npm

if [[ -f "$PID_FILE" ]]; then
  echo "Native stack may already be running. Run ./scripts/stop-native.sh first."
  exit 1
fi

mkdir -p "$RUNTIME_DIR"
: > "$PID_FILE"

echo "Installing orchestrator dependencies..."
python3 -m pip install -q -r "$ROOT/orchestrator/requirements.txt"

if [[ ! -d "$ROOT/dashboard/node_modules" ]]; then
  echo "Installing dashboard dependencies..."
  (cd "$ROOT/dashboard" && npm install --silent)
fi

echo "Starting orchestrator on :8000..."
cd "$ROOT/orchestrator"
python3 -m uvicorn master:app --host 0.0.0.0 --port 8000 &
record_pid orchestrator $!

start_node node1 8080 8081
start_node node2 8082 8083
start_node node3 8084 8085
start_node node4 8086 8087

echo "Starting dashboard on :5173..."
cd "$ROOT/dashboard"
npm run dev -- --host 0.0.0.0 &
record_pid dashboard $!

echo ""
echo "Native stack is running."
echo ""
echo "  Dashboard : http://localhost:5173"
echo "  API       : http://localhost:8000"
echo "  Swagger   : http://localhost:8000/docs"
echo ""
echo "  4 worker nodes with thermal/latency/chaos/recovery — same features as Docker."
echo ""
echo "Stop: ./scripts/stop-native.sh"
echo ""
