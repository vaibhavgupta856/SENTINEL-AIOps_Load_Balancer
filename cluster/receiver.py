from http.server import BaseHTTPRequestHandler, HTTPServer
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

TELEMETRY_FILE = "/tmp/worker_telemetry.json"
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
    with open(TELEMETRY_FILE, "w") as f:
        json.dump(payload, f)


def sync_chaos_flags():
    cpu_flag = "/tmp/chaos_cpu.flag"
    thermal_flag = "/tmp/chaos_thermal.flag"

    if cpu_spike_active():
        open(cpu_flag, "w").close()
    elif os.path.exists(cpu_flag):
        os.remove(cpu_flag)

    if thermal_spike_active():
        open(thermal_flag, "w").close()
    elif os.path.exists(thermal_flag):
        os.remove(thermal_flag)


def fetch_monitor_metrics():
    """Fetch low-level metrics from the C++ hardware monitor."""
    try:
        response = urllib.request.urlopen('http://localhost:8080/health', timeout=1)
        metrics = json.loads(response.read().decode())
        if cpu_spike_active():
            metrics["cpu"] = min(98, max(metrics.get("cpu", 0), 92))
            metrics["ram"] = min(98, max(metrics.get("ram", 0), 88))
        if thermal_spike_active():
            metrics["temperature_c"] = min(99, max(metrics.get("temperature_c", 0), 88))
        return metrics
    except Exception:
        return {
            "cpu": 0,
            "ram": 0,
            "temperature_c": 0,
            "inference_latency_p99_ms": percentile(_latency_samples, 0.99),
            "error_rate": round(_error_count / _inference_count, 4) if _inference_count else 0.0,
            "inference_count": _inference_count,
        }


def run_task():
    """Simulate heavy compute workload and record inference latency."""
    started = time.time()
    success = True
    try:
        with open("/tmp/job_active.flag", "w") as f:
            f.write("1")
        time.sleep(10)
        if os.path.exists("/tmp/job_active.flag"):
            os.remove("/tmp/job_active.flag")
    except Exception:
        success = False
    finally:
        latency_ms = (time.time() - started) * 1000
        record_inference(latency_ms, success=success)


def read_json_body(handler):
    length = int(handler.headers.get('Content-Length', 0))
    if length == 0:
        return {}
    return json.loads(handler.rfile.read(length).decode())


def send_json(handler, status, payload):
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(body)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for orchestrator health checks and job submissions"""

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/health':
            delay = health_delay_seconds()
            if delay > 0:
                time.sleep(delay)

            if should_drop_health():
                record_inference(delay * 1000 if delay else 2500, success=False)
                self.send_response(503)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error":"chaos_packet_drop"}')
                return

            sync_chaos_flags()
            metrics = fetch_monitor_metrics()
            send_json(self, 200, metrics)
            return

        if self.path == '/chaos/status':
            send_json(self, 200, get_status())
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == '/submit-task':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            job = json.loads(body.decode())

            if should_drop_health():
                record_inference(1800, success=False)
                send_json(self, 503, {
                    "status": "rejected",
                    "job_id": job.get('job_id', 'unknown'),
                    "message": "Node unavailable"
                })
                return

            multiprocessing.Process(target=run_task).start()
            send_json(self, 200, {
                "status": "accepted",
                "job_id": job.get('job_id', 'unknown'),
                "message": "Task queued for execution"
            })
            return

        if self.path == '/chaos':
            body = read_json_body(self)
            action = body.get('action', 'reset')
            if action == 'reset':
                sync_chaos_flags()
                send_json(self, 200, {"status": "reset", "chaos": reset()})
                return

            chaos = apply(
                action=action,
                duration=int(body.get('duration', 30)),
                latency_ms=int(body.get('latency_ms', 3000)),
                drop_rate=int(body.get('drop_rate', 80)),
            )
            sync_chaos_flags()
            send_json(self, 200, {"status": "applied", "chaos": chaos})
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

def auto_register_node():
    """Auto-register node with orchestrator on startup"""
    node_id = os.environ.get('NODE_ID') or socket.gethostname()
    node_url = f"http://{node_id}:8081"
    orchestrator_url = "http://sentinel_orchestrator:8000/api/nodes/register"

    for attempt in range(15):
        try:
            data = json.dumps({"node_id": node_id, "url": node_url})
            req = urllib.request.Request(
                orchestrator_url,
                data=data.encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=2)
            print(f"[AUTO-REGISTER] Node {node_id} registered at {node_url}")
            return True
        except Exception as e:
            print(f"[AUTO-REGISTER] Attempt {attempt + 1}/15 waiting for orchestrator ({str(e)[:60]})")
            time.sleep(2)

    print(f"[AUTO-REGISTER] Failed to register node {node_id}")
    return False

if __name__ == '__main__':
    port = int(os.environ.get('NODE_PORT', 8081))
    flush_worker_telemetry()
    multiprocessing.Process(target=auto_register_node, daemon=True).start()
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"[NODE] API server listening on port {port}")
    server.serve_forever()
