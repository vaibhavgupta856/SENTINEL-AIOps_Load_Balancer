from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import multiprocessing
import time
import os
import json
import socket
import urllib.request
import urllib.error
from collections import deque
from chaos_state import (
    apply,
    reset,
    get_status,
    should_drop_health,
    health_delay_seconds,
    cpu_spike_active,
    thermal_spike_active,
)
from paths import (
    TELEMETRY_FILE,
    JOB_FLAG,
    CHAOS_CPU_FLAG,
    CHAOS_THERMAL_FLAG,
    MONITOR_URL,
    ORCHESTRATOR_REGISTER_URL,
    NODE_HOST,
    NODE_PORT,
    WORKER_DIR,
)

LATENCY_WINDOW = 100

_latency_samples = deque(maxlen=LATENCY_WINDOW)
_error_count = 0
_inference_count = 0


def percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * pct) - 1))
    return ordered[index]


def record_inference(latency_ms, success=True):
    global _error_count, _inference_count
    _latency_samples.append(latency_ms)
    _inference_count += 1
    if not success:
        _error_count += 1
    flush_worker_telemetry()


def flush_worker_telemetry():
    payload = {
        "inference_latency_p99_ms": round(percentile(_latency_samples, 0.99), 2),
        "inference_latency_avg_ms": round(sum(_latency_samples) / len(_latency_samples), 2) if _latency_samples else 0.0,
        "error_rate": round(_error_count / _inference_count, 4) if _inference_count else 0.0,
        "inference_count": _inference_count,
    }
    os.makedirs(WORKER_DIR, exist_ok=True)
    with open(TELEMETRY_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def sync_chaos_flags():
    if cpu_spike_active():
        open(CHAOS_CPU_FLAG, "w", encoding="utf-8").close()
    elif os.path.exists(CHAOS_CPU_FLAG):
        os.remove(CHAOS_CPU_FLAG)

    if thermal_spike_active():
        open(CHAOS_THERMAL_FLAG, "w", encoding="utf-8").close()
    elif os.path.exists(CHAOS_THERMAL_FLAG):
        os.remove(CHAOS_THERMAL_FLAG)


def apply_chaos_metric_overrides(metrics: dict) -> dict:
    """Ensure chaos-driven stress is visible even if the hardware monitor fetch fails."""
    if cpu_spike_active():
        metrics["cpu"] = min(98, max(metrics.get("cpu", 0), 92))
        metrics["ram"] = min(98, max(metrics.get("ram", 0), 88))
        metrics["temperature_c"] = min(99, max(metrics.get("temperature_c", 0), 82))
    if thermal_spike_active():
        metrics["temperature_c"] = min(99, max(metrics.get("temperature_c", 0), 88))
    return metrics


def fetch_monitor_metrics():
    """Fetch low-level metrics from the C++ or Python hardware monitor."""
    metrics = {
        "cpu": 0,
        "ram": 0,
        "temperature_c": 0,
        "inference_latency_p99_ms": percentile(_latency_samples, 0.99),
        "error_rate": round(_error_count / _inference_count, 4) if _inference_count else 0.0,
        "inference_count": _inference_count,
    }
    try:
        response = urllib.request.urlopen(f"{MONITOR_URL.rstrip('/')}/health", timeout=1)
        metrics.update(json.loads(response.read().decode()))
    except Exception:
        pass
    return apply_chaos_metric_overrides(metrics)


def run_task():
    """Simulate heavy compute workload and record inference latency."""
    started = time.time()
    success = True
    try:
        os.makedirs(WORKER_DIR, exist_ok=True)
        with open(JOB_FLAG, "w", encoding="utf-8") as f:
            f.write("1")
        time.sleep(10)
        if os.path.exists(JOB_FLAG):
            os.remove(JOB_FLAG)
    except Exception:
        success = False
    finally:
        latency_ms = (time.time() - started) * 1000
        record_inference(latency_ms, success=success)


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode())


def send_json(handler, status, payload):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for orchestrator health checks and job submissions"""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            delay = health_delay_seconds()
            if delay > 0:
                time.sleep(delay)

            if should_drop_health():
                record_inference(delay * 1000 if delay else 2500, success=False)
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"chaos_packet_drop"}')
                return

            sync_chaos_flags()
            metrics = fetch_monitor_metrics()
            send_json(self, 200, metrics)
            return

        if self.path == "/chaos/status":
            send_json(self, 200, get_status())
            return

        if self.path == "/chaos/reset":
            chaos = reset()
            sync_chaos_flags()
            if os.path.exists(JOB_FLAG):
                os.remove(JOB_FLAG)
            send_json(self, 200, {"status": "reset", "chaos": chaos})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/submit-task":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            job = json.loads(body.decode())

            if should_drop_health():
                record_inference(1800, success=False)
                send_json(self, 503, {
                    "status": "rejected",
                    "job_id": job.get("job_id", "unknown"),
                    "message": "Node unavailable",
                })
                return

            multiprocessing.Process(target=run_task).start()
            send_json(self, 200, {
                "status": "accepted",
                "job_id": job.get("job_id", "unknown"),
                "message": "Task queued for execution",
            })
            return

        if self.path == "/chaos":
            body = read_json_body(self)
            action = body.get("action", "reset")
            if action == "reset":
                chaos = reset()
                sync_chaos_flags()
                if os.path.exists(JOB_FLAG):
                    os.remove(JOB_FLAG)
                send_json(self, 200, {"status": "reset", "chaos": chaos})
                return

            chaos = apply(
                action=action,
                duration=int(body.get("duration", 30)),
                latency_ms=int(body.get("latency_ms", 3000)),
                drop_rate=int(body.get("drop_rate", 80)),
            )
            sync_chaos_flags()
            send_json(self, 200, {"status": "applied", "chaos": chaos})
            return

        if self.path == "/chaos/reset":
            chaos = reset()
            sync_chaos_flags()
            if os.path.exists(JOB_FLAG):
                os.remove(JOB_FLAG)
            send_json(self, 200, {"status": "reset", "chaos": chaos})
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def auto_register_node():
    """Auto-register node with orchestrator on startup."""
    node_id = os.environ.get("NODE_ID") or socket.gethostname()
    node_url = f"http://{NODE_HOST}:{NODE_PORT}"

    for attempt in range(15):
        try:
            data = json.dumps({"node_id": node_id, "url": node_url})
            req = urllib.request.Request(
                ORCHESTRATOR_REGISTER_URL,
                data=data.encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=2)
            print(f"[AUTO-REGISTER] Node {node_id} registered at {node_url}")
            return True
        except Exception as e:
            print(f"[AUTO-REGISTER] Attempt {attempt + 1}/15 waiting for orchestrator ({str(e)[:60]})")
            time.sleep(2)

    print(f"[AUTO-REGISTER] Failed to register node {node_id}")
    return False


if __name__ == "__main__":
    flush_worker_telemetry()
    multiprocessing.Process(target=auto_register_node, daemon=True).start()
    server = ThreadedHTTPServer(("0.0.0.0", NODE_PORT), HealthCheckHandler)
    print(f"[NODE] {os.environ.get('NODE_ID', 'worker')} API on port {NODE_PORT} | monitor {MONITOR_URL}")
    server.serve_forever()
