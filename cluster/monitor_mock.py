"""
Pure-Python hardware monitor — same role as monitor.cpp for native (non-Docker) runs.
Works on Windows, Linux, and macOS without compiling C++.
"""
import json
import os
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from paths import (
    CHAOS_CPU_FLAG,
    CHAOS_THERMAL_FLAG,
    JOB_FLAG,
    MONITOR_PORT,
    NODE_ID,
    TELEMETRY_FILE,
    WORKER_DIR,
)


def _read_telemetry_file():
    latency_p99 = 0.0
    error_rate = 0.0
    inference_count = 0
    if os.path.exists(TELEMETRY_FILE):
        try:
            with open(TELEMETRY_FILE, encoding="utf-8") as f:
                data = json.load(f)
            latency_p99 = data.get("inference_latency_p99_ms", 0)
            error_rate = data.get("error_rate", 0)
            inference_count = data.get("inference_count", 0)
        except Exception:
            pass
    return latency_p99, error_rate, inference_count


def get_metrics():
    seed = hash(NODE_ID) % 100
    base_cpu = 15 + random.randint(0, 20) + seed
    cpu = min(95, base_cpu)
    ram = 35 + random.randint(0, 20) + (seed // 2)
    temp_c = 32 + (cpu * 48 // 100) + (seed % 8) + random.randint(0, 3)

    if os.path.exists(JOB_FLAG):
        cpu = min(98, 85 + random.randint(0, 12))
        temp_c = min(96, 72 + random.randint(0, 18))

    if os.path.exists(CHAOS_CPU_FLAG):
        cpu = min(98, 90 + random.randint(0, 8))
        temp_c = min(98, 82 + random.randint(0, 12))

    if os.path.exists(CHAOS_THERMAL_FLAG):
        temp_c = min(99, 86 + random.randint(0, 10))

    p99, err, count = _read_telemetry_file()
    return {
        "cpu": cpu,
        "ram": ram,
        "temperature_c": temp_c,
        "inference_latency_p99_ms": p99,
        "error_rate": err,
        "inference_count": count,
        "timestamp": str(int(time.time())),
    }


class MonitorHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/health", "/"):
            body = json.dumps(get_metrics()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    os.makedirs(WORKER_DIR, exist_ok=True)
    server = HTTPServer(("0.0.0.0", MONITOR_PORT), MonitorHandler)
    print(f"[MONITOR-MOCK] {NODE_ID} on port {MONITOR_PORT} | data: {WORKER_DIR}")
    server.serve_forever()
