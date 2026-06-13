import os
import tempfile

NODE_ID = os.environ.get("NODE_ID", "default")
WORKER_DIR = os.environ.get("WORKER_DATA_DIR", "/tmp")
os.makedirs(WORKER_DIR, exist_ok=True)

TELEMETRY_FILE = os.path.join(WORKER_DIR, "worker_telemetry.json")
JOB_FLAG = os.path.join(WORKER_DIR, "job_active.flag")
CHAOS_CPU_FLAG = os.path.join(WORKER_DIR, "chaos_cpu.flag")
CHAOS_THERMAL_FLAG = os.path.join(WORKER_DIR, "chaos_thermal.flag")

MONITOR_PORT = int(os.environ.get("MONITOR_PORT", "8080"))
MONITOR_URL = os.environ.get("MONITOR_URL", f"http://127.0.0.1:{MONITOR_PORT}")
ORCHESTRATOR_REGISTER_URL = os.environ.get(
    "ORCHESTRATOR_URL", "http://127.0.0.1:8000/api/nodes/register"
)
NODE_HOST = os.environ.get("NODE_HOST", "127.0.0.1")
NODE_PORT = int(os.environ.get("NODE_PORT", "8081"))
