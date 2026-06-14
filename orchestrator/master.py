import os, asyncio, httpx, sqlite3, json, time, random
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SENTINEL_ORCHESTRATOR")

app = FastAPI(title="SENTINEL AIOps Orchestrator", version="2.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CIRCUIT_BREAKER_THRESHOLD = 85
CIRCUIT_BREAKER_COOLDOWN = 10
TELEMETRY_POLL_INTERVAL = 3

THERMAL_THRESHOLD_C = 75
P99_LATENCY_BASELINE_MS = 120
P99_VARIANCE_FACTOR = 1.8
ERROR_RATE_THRESHOLD = 0.12
COOLING_OFF_DURATION = 30
MIN_TRAFFIC_WEIGHT = 0.05

CHAOS_ACTIONS = {"latency_spike", "packet_drop", "cpu_spike", "thermal_spike", "node_kill"}

IN_DOCKER = os.path.exists("/.dockerenv")

def is_localhost_url(url: str) -> bool:
    return "127.0.0.1" in url or "localhost" in url.lower()

def docker_worker_url(node_id: str) -> str:
    return f"http://{node_id}:8081"

def resolve_worker_url(node_id: str, registry=None) -> str:
    """Ensure worker URL points at the receiver API, especially inside Docker."""
    reg = registry if registry is not None else node_registry
    node = reg.nodes.get(node_id)
    if not node:
        return docker_worker_url(node_id)

    url = node.get("url", "")
    fixed = url

    if IN_DOCKER:
        if is_localhost_url(url) or not url.endswith(":8081"):
            fixed = docker_worker_url(node_id)
    elif is_localhost_url(url):
        native_ports = {"node1": 8081, "node2": 8083, "node3": 8085, "node4": 8087}
        expected = native_ports.get(node_id)
        if expected and f":{expected}" not in url:
            fixed = f"http://127.0.0.1:{expected}"

    if fixed != url:
        logger.warning(f"Worker URL repair: {node_id} {url} -> {fixed}")
        node["url"] = fixed
        reg.save()

    return fixed

def repair_registry_urls(registry) -> None:
    """Fix stale worker URLs (native localhost / wrong ports)."""
    if not registry.nodes:
        return
    changed = False
    for node_id in list(registry.nodes.keys()):
        before = registry.nodes[node_id].get("url", "")
        after = resolve_worker_url(node_id, registry)
        if before != after:
            changed = True
    if changed:
        logger.info("Registry worker URLs repaired")

RECOVERY_GRACE_SECONDS = 60
recovery_grace_until: Dict[str, float] = {}

def in_recovery_grace(node_id: str) -> bool:
    return recovery_grace_until.get(node_id, 0) > time.time()

class CircuitBreaker:
    def __init__(self):
        self.state = {}

    def is_open(self, node_id: str) -> bool:
        if node_id not in self.state:
            return False
        if self.state[node_id]['status'] == 'OPEN':
            elapsed = time.time() - self.state[node_id]['timestamp']
            if elapsed > CIRCUIT_BREAKER_COOLDOWN:
                logger.info(f"Circuit breaker closing for {node_id} after cooldown")
                self.state[node_id]['status'] = 'CLOSED'
                return False
            return True
        return False

    def open(self, node_id: str):
        self.state[node_id] = {'status': 'OPEN', 'timestamp': time.time()}
        logger.warning(f"Circuit breaker opened for {node_id}")

    def close(self, node_id: str):
        if node_id in self.state:
            self.state[node_id]['status'] = 'CLOSED'

circuit_breaker = CircuitBreaker()
node_previous_state: Dict[str, dict] = {}

class CoolingOffManager:
    """Gradually throttles traffic to nodes showing thermal or latency stress."""

    def __init__(self):
        self.weights: Dict[str, float] = {}
        self.cooling_until: Dict[str, float] = {}
        self.baseline_p99: Dict[str, float] = {}
        self.last_reason: Dict[str, str] = {}

    def _adaptive_baseline(self, node_id: str, p99_ms: float) -> float:
        if p99_ms <= 0:
            return self.baseline_p99.get(node_id, P99_LATENCY_BASELINE_MS)

        current = self.baseline_p99.get(node_id, P99_LATENCY_BASELINE_MS)
        if p99_ms < current:
            updated = (current * 0.85) + (p99_ms * 0.15)
        else:
            updated = (current * 0.95) + (p99_ms * 0.05)
        self.baseline_p99[node_id] = max(40.0, updated)
        return self.baseline_p99[node_id]

    def update(self, node_id: str, metrics: dict) -> float:
        weight = self.weights.get(node_id, 1.0)
        reasons = []

        temp_c = metrics.get('temperature_c', 0)
        p99_ms = metrics.get('inference_latency_p99_ms', 0)
        error_rate = metrics.get('error_rate', 0)
        baseline = self._adaptive_baseline(node_id, p99_ms)

        if temp_c >= THERMAL_THRESHOLD_C:
            weight = min(weight, 0.25)
            reasons.append(f"thermal {temp_c}C")
            self.cooling_until[node_id] = time.time() + COOLING_OFF_DURATION

        if p99_ms > baseline * P99_VARIANCE_FACTOR and p99_ms > 0:
            severity = min(1.0, p99_ms / (baseline * P99_VARIANCE_FACTOR * 2))
            weight = min(weight, max(MIN_TRAFFIC_WEIGHT, 0.6 - (severity * 0.45)))
            reasons.append(f"p99 {p99_ms:.0f}ms vs {baseline:.0f}ms baseline")
            self.cooling_until[node_id] = time.time() + COOLING_OFF_DURATION

        if error_rate >= ERROR_RATE_THRESHOLD:
            weight = min(weight, max(MIN_TRAFFIC_WEIGHT, 0.35))
            reasons.append(f"error rate {error_rate * 100:.1f}%")
            self.cooling_until[node_id] = time.time() + COOLING_OFF_DURATION

        cooling_active = self.cooling_until.get(node_id, 0) > time.time()
        if cooling_active and not reasons:
            weight = min(weight, 0.35)
            reasons.append("cooling-off period")

        if not cooling_active and not reasons:
            weight = min(1.0, weight + 0.15)

        weight = max(MIN_TRAFFIC_WEIGHT, min(1.0, weight))
        previous_weight = self.weights.get(node_id, 1.0)
        self.weights[node_id] = weight

        reason_text = ", ".join(reasons) if reasons else "healthy"
        self.last_reason[node_id] = reason_text

        if reasons and weight < 0.8 and (previous_weight >= 0.8 or cooling_active):
            log_healing_event(
                node_id,
                "traffic_throttled",
                f"{node_id} traffic weight reduced to {weight:.0%} ({reason_text}). "
                f"Sentinel is giving this node a cooling-off period instead of waiting for a crash."
            )
        elif not reasons and previous_weight < 0.8 and weight >= 0.95:
            log_healing_event(
                node_id,
                "traffic_restored",
                f"{node_id} telemetry normalized. Routing weight restored to {weight:.0%}."
            )

        return weight

    def get_weight(self, node_id: str) -> float:
        return self.weights.get(node_id, 1.0)

    def get_reason(self, node_id: str) -> str:
        return self.last_reason.get(node_id, "healthy")

    def reset(self, node_id: str):
        self.weights[node_id] = 1.0
        self.cooling_until.pop(node_id, None)
        self.last_reason[node_id] = "healthy"

class NodeRegistry:
    def __init__(self):
        self.nodes: Dict[str, dict] = {}
        self.load()

    def register(self, node_id: str, url: str) -> dict:
        existing = self.nodes.get(node_id)
        if existing and is_localhost_url(url):
            prev_url = existing.get("url", "")
            if prev_url and not is_localhost_url(prev_url):
                logger.warning(
                    f"Ignoring localhost registration for {node_id}; keeping Docker URL {prev_url}"
                )
                existing["registered_at"] = datetime.now().isoformat()
                self.save()
                return existing

        self.nodes[node_id] = {
            'url': url,
            'registered_at': datetime.now().isoformat(),
            'status': 'Unknown',
            'last_heartbeat': None,
            'metrics': {
                'cpu': 0,
                'ram': 0,
                'temperature_c': 0,
                'inference_latency_p99_ms': 0,
                'error_rate': 0,
                'routing_weight': 1.0,
            },
            'chaos': None,
        }
        self.save()
        logger.info(f"Node registered: {node_id} at {url}")
        return self.nodes[node_id]

    def unregister(self, node_id: str):
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.save()
            logger.info(f"Node unregistered: {node_id}")

    def get_healthy_nodes(self) -> List[str]:
        return [nid for nid, n in self.nodes.items()
                if n['status'] == 'Online' and not circuit_breaker.is_open(nid)]

    def get_available_nodes(self) -> List[str]:
        return [nid for nid in self.get_healthy_nodes()
                if self.nodes[nid]['metrics']['cpu'] < CIRCUIT_BREAKER_THRESHOLD]

    def save(self):
        with open('node_registry.json', 'w') as f:
            json.dump(self.nodes, f, indent=2, default=str)

    def load(self):
        if os.path.exists('node_registry.json'):
            with open('node_registry.json', 'r') as f:
                self.nodes = json.load(f)
            for node in self.nodes.values():
                node.setdefault('chaos', None)
                metrics = node.setdefault('metrics', {})
                metrics.setdefault('temperature_c', 0)
                metrics.setdefault('inference_latency_p99_ms', 0)
                metrics.setdefault('error_rate', 0)
                metrics.setdefault('routing_weight', 1.0)
            repair_registry_urls(self)

node_registry = NodeRegistry()
repair_registry_urls(node_registry)

def init_db():
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        node_id TEXT,
        cpu INTEGER,
        ram INTEGER,
        temperature_c REAL,
        inference_latency_p99_ms REAL,
        error_rate REAL,
        routing_weight REAL,
        timestamp DATETIME,
        job_routed_to TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS routing_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        job_id TEXT,
        source_node TEXT,
        target_node TEXT,
        decision_reason TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS healing_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        node_id TEXT,
        event_type TEXT,
        message TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS chaos_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        node_id TEXT,
        action TEXT,
        duration INTEGER,
        triggered_by TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS inference_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME,
        job_id TEXT,
        target_node TEXT,
        status TEXT,
        detail TEXT
    )""")
    conn.commit()
    conn.close()

def migrate_metrics_schema():
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute("PRAGMA table_info(metrics)")
    existing = {row[1] for row in c.fetchall()}
    migrations = {
        'temperature_c': 'REAL DEFAULT 0',
        'inference_latency_p99_ms': 'REAL DEFAULT 0',
        'error_rate': 'REAL DEFAULT 0',
        'routing_weight': 'REAL DEFAULT 1.0',
    }
    for column, definition in migrations.items():
        if column not in existing:
            c.execute(f"ALTER TABLE metrics ADD COLUMN {column} {definition}")
    conn.commit()
    conn.close()

init_db()
migrate_metrics_schema()

def log_healing_event(node_id: str, event_type: str, message: str):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO healing_log (timestamp, node_id, event_type, message) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), node_id, event_type, message)
    )
    conn.commit()
    conn.close()
    logger.info(f"[HEALING] {message}")

cooling_off = CoolingOffManager()

def log_chaos_event(node_id: str, action: str, duration: int, triggered_by: str = "dashboard"):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO chaos_log (timestamp, node_id, action, duration, triggered_by) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), node_id, action, duration, triggered_by)
    )
    conn.commit()
    conn.close()

def log_inference(job_id: str, target_node: str, status: str, detail: str):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO inference_log (timestamp, job_id, target_node, status, detail) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), job_id, target_node, status, detail)
    )
    conn.commit()
    conn.close()

def track_state_transition(node_id: str, status: str, circuit: str):
    prev = node_previous_state.get(node_id, {})
    prev_status = prev.get('status')
    prev_circuit = prev.get('circuit')

    if prev_status == 'Online' and status == 'Offline':
        log_healing_event(
            node_id,
            "node_offline",
            f"{node_id} stopped responding. Traffic will skip this node on the next poll."
        )
    elif prev_status == 'Offline' and status == 'Online':
        log_healing_event(
            node_id,
            "node_recovered",
            f"{node_id} is back online and eligible for routing again."
        )

    if prev_circuit == 'CLOSED' and circuit == 'OPEN':
        log_healing_event(
            node_id,
            "circuit_open",
            f"{node_id} isolated by circuit breaker. New jobs will route elsewhere."
        )
    elif prev_circuit == 'OPEN' and circuit == 'CLOSED':
        log_healing_event(
            node_id,
            "circuit_closed",
            f"{node_id} circuit closed. Node re-entered the routing pool."
        )

    node_previous_state[node_id] = {'status': status, 'circuit': circuit}

async def probe_worker_health(client: httpx.AsyncClient, url: str) -> dict:
    """Lightweight health probe used to diagnose why recovery failed."""
    try:
        resp = await client.get(f"{url}/health", timeout=2.0)
        if resp.status_code == 200:
            return {"ok": True}
        return {
            "ok": False,
            "reason": "health_rejected",
            "detail": f"returned HTTP {resp.status_code}",
            "status_code": resp.status_code,
        }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "reason": "health_timeout",
            "detail": "health check timed out after 2 seconds",
        }
    except httpx.ConnectError:
        return {
            "ok": False,
            "reason": "container_unreachable",
            "detail": "connection refused — nothing is listening on the worker port",
        }
    except Exception as e:
        return {
            "ok": False,
            "reason": "health_error",
            "detail": str(e),
        }

def _classify_chaos_reset_error(exc: Exception) -> dict:
    if isinstance(exc, httpx.TimeoutException):
        return {
            "reason": "chaos_reset_timeout",
            "detail": "chaos reset timed out after 3 seconds — worker may be hung",
        }
    if isinstance(exc, httpx.ConnectError):
        return {
            "reason": "container_unreachable",
            "detail": "connection refused — worker container is likely stopped or crashed",
        }
    return {
        "reason": "chaos_reset_failed",
        "detail": str(exc),
    }

def build_recovery_failure_message(
    node_id: str,
    url: str,
    chaos_cleared: bool,
    chaos_error: Optional[dict],
    health_probe: dict,
) -> tuple[str, str]:
    """Return (failure_reason, human-readable message) for an unsuccessful recovery."""
    if chaos_error and not chaos_cleared:
        reason = chaos_error["reason"]
        if reason == "container_unreachable":
            return reason, (
                f"{node_id} could not be recovered. The worker at {url} is unreachable — "
                f"the container is probably stopped or crashed. "
                f"Restart it with: docker compose restart {node_id}"
            )
        if reason == "chaos_reset_timeout":
            return reason, (
                f"{node_id} could not be recovered. The worker did not respond to the chaos reset "
                f"within 3 seconds — the process may be hung. Try restarting the container."
            )
        return reason, (
            f"{node_id} could not be recovered. Failed to clear chaos on the worker: "
            f"{chaos_error['detail']}."
        )

    health_reason = health_probe.get("reason", "health_error")
    health_detail = health_probe.get("detail", "unknown error")

    if health_reason == "container_unreachable":
        return health_reason, (
            f"{node_id} could not be recovered. Chaos was cleared on the worker, but it is still "
            f"unreachable at {url} — the container likely crashed after reset. "
            f"Restart it with: docker compose restart {node_id}"
        )
    if health_reason == "health_timeout":
        return health_reason, (
            f"{node_id} could not be recovered. Chaos was cleared, but the health check still "
            f"timed out after 2 seconds — the worker is overloaded or stuck and needs a container restart."
        )
    if health_reason == "health_rejected":
        status_code = health_probe.get("status_code", "?")
        return health_reason, (
            f"{node_id} could not be recovered. The worker is still rejecting health probes "
            f"(HTTP {status_code}) — simulated kill or packet-drop chaos may still be active, "
            f"or the node is in a failed state. Try Recover again, or restart the container."
        )
    return health_reason, (
        f"{node_id} could not be recovered. Chaos was cleared but the health check failed: {health_detail}."
    )

async def recover_node(client: httpx.AsyncClient, node_id: str) -> dict:
    """Clear chaos on the worker, reset orchestrator-side state, and re-poll health."""
    node = node_registry.nodes.get(node_id)
    if not node:
        message = (
            f"{node_id} could not be recovered. It is not registered with the orchestrator — "
            f"it may have been removed from the cluster."
        )
        return {
            "node_id": node_id,
            "ok": False,
            "reason": "node_not_found",
            "message": message,
            "recoverable": False,
        }

    url = resolve_worker_url(node_id)
    chaos_cleared = False
    chaos_error = None

    async def reset_worker_chaos(target_url: str) -> tuple[bool, Optional[dict]]:
        cleared = False
        error = None
        try:
            resp = await client.post(f"{target_url}/chaos", json={"action": "reset"}, timeout=3.0)
            if resp.status_code == 200:
                node["chaos"] = None
                cleared = True
            else:
                error = {
                    "reason": "chaos_reset_rejected",
                    "detail": f"worker returned HTTP {resp.status_code}",
                }
        except Exception as e:
            error = _classify_chaos_reset_error(e)
            logger.warning(f"Chaos reset failed for {node_id} at {target_url}: {e}")
        return cleared, error

    chaos_cleared, chaos_error = await reset_worker_chaos(url)

    circuit_breaker.close(node_id)
    cooling_off.reset(node_id)
    recovery_grace_until[node_id] = time.time() + RECOVERY_GRACE_SECONDS
    if node.get("metrics"):
        node["metrics"]["routing_weight"] = 1.0

    poll = None
    online = False
    for _ in range(4):
        poll = await fetch_and_save(client, node_id)
        online = poll is not None and poll.get("status") == "Online"
        if online:
            break
        if not chaos_cleared:
            chaos_cleared, chaos_error = await reset_worker_chaos(url)
        await asyncio.sleep(0.4)

    if online:
        return {
            "node_id": node_id,
            "ok": True,
            "status": "Online",
            "chaos_cleared": chaos_cleared,
            "circuit": "CLOSED",
            "routing_weight": 1.0,
            "message": f"{node_id} is back online and accepting traffic.",
            "recoverable": True,
        }

    health_probe = await probe_worker_health(client, url)

    if IN_DOCKER and (is_localhost_url(url) or health_probe.get("reason") in {
        "container_unreachable", "health_rejected"
    }):
        url = resolve_worker_url(node_id)
        chaos_cleared, chaos_error = await reset_worker_chaos(url)
        for _ in range(4):
            poll = await fetch_and_save(client, node_id)
            online = poll is not None and poll.get("status") == "Online"
            if online:
                return {
                    "node_id": node_id,
                    "ok": True,
                    "status": "Online",
                    "chaos_cleared": chaos_cleared,
                    "circuit": "CLOSED",
                    "routing_weight": 1.0,
                    "message": (
                        f"{node_id} is back online. Fixed worker URL and cleared kill/chaos state."
                    ),
                    "recoverable": True,
                }
            await asyncio.sleep(0.4)
        health_probe = await probe_worker_health(client, url)

    failure_reason, message = build_recovery_failure_message(
        node_id, url, chaos_cleared, chaos_error, health_probe
    )

    log_healing_event(node_id, "recovery_failed", message)

    return {
        "node_id": node_id,
        "ok": False,
        "status": "Offline",
        "chaos_cleared": chaos_cleared,
        "circuit": "CLOSED",
        "routing_weight": 1.0,
        "reason": failure_reason,
        "message": message,
        "recoverable": failure_reason in {"health_rejected", "health_timeout", "chaos_reset_timeout"},
        "diagnosis": {
            "chaos_cleared": chaos_cleared,
            "chaos_error": chaos_error,
            "health_probe": health_probe,
        },
    }

async def fetch_and_save(client, node_id: str):
    node = node_registry.nodes.get(node_id)
    if not node:
        return None

    url = resolve_worker_url(node_id)

    try:
        resp = await client.get(f"{url}/health", timeout=2.0)
        if resp.status_code == 503:
            try:
                await client.post(f"{url}/chaos", json={"action": "reset"}, timeout=2.0)
                resp = await client.get(f"{url}/health", timeout=2.0)
            except Exception:
                pass
        if resp.status_code != 200:
            raise httpx.HTTPStatusError("unhealthy", request=resp.request, response=resp)

        data = resp.json()
        metrics = {
            'cpu': data.get('cpu', 0),
            'ram': data.get('ram', 0),
            'temperature_c': data.get('temperature_c', 0),
            'inference_latency_p99_ms': data.get('inference_latency_p99_ms', 0),
            'error_rate': data.get('error_rate', 0),
        }
        routing_weight = cooling_off.update(node_id, metrics)
        if in_recovery_grace(node_id):
            routing_weight = 1.0
            cooling_off.weights[node_id] = 1.0
            cooling_off.last_reason[node_id] = "healthy (recovery grace)"
        metrics['routing_weight'] = routing_weight
        node['metrics'] = metrics
        node['status'] = 'Online'
        node['last_heartbeat'] = datetime.now().isoformat()

        if data['cpu'] >= CIRCUIT_BREAKER_THRESHOLD and not in_recovery_grace(node_id):
            circuit_breaker.open(node_id)
        else:
            circuit_breaker.close(node_id)

        conn = sqlite3.connect('sentinel_metrics.db')
        c = conn.cursor()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            """INSERT INTO metrics
               (node_id, cpu, ram, temperature_c, inference_latency_p99_ms, error_rate, routing_weight, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node_id,
                data['cpu'],
                data['ram'],
                metrics['temperature_c'],
                metrics['inference_latency_p99_ms'],
                metrics['error_rate'],
                routing_weight,
                current_time,
            )
        )
        conn.commit()
        conn.close()

        circuit = 'OPEN' if circuit_breaker.is_open(node_id) else 'CLOSED'
        track_state_transition(node_id, 'Online', circuit)

        try:
            chaos_resp = await client.get(f"{url}/chaos/status", timeout=1.0)
            if chaos_resp.status_code == 200:
                node['chaos'] = chaos_resp.json()
        except Exception:
            node['chaos'] = None

        return {
            'node_id': node_id,
            'url': url,
            'cpu': data['cpu'],
            'ram': data['ram'],
            'temperature_c': metrics['temperature_c'],
            'inference_latency_p99_ms': metrics['inference_latency_p99_ms'],
            'error_rate': metrics['error_rate'],
            'routing_weight': routing_weight,
            'routing_reason': cooling_off.get_reason(node_id),
            'status': 'Online',
            'circuit_breaker': circuit,
            'chaos': node.get('chaos'),
        }
    except asyncio.TimeoutError:
        node['status'] = 'Offline'
        track_state_transition(node_id, 'Offline', 'OPEN' if circuit_breaker.is_open(node_id) else 'CLOSED')
        return {'node_id': node_id, 'cpu': 0, 'ram': 0, 'status': 'Offline', 'chaos': node.get('chaos')}
    except Exception as e:
        node['status'] = 'Offline'
        logger.error(f"Error fetching telemetry from {node_id}: {str(e)}")
        track_state_transition(node_id, 'Offline', 'OPEN' if circuit_breaker.is_open(node_id) else 'CLOSED')
        return {'node_id': node_id, 'cpu': 0, 'ram': 0, 'status': 'Offline', 'chaos': node.get('chaos')}

async def forward_job_to_node(client: httpx.AsyncClient, node_id: str, job_id: str) -> dict:
    node = node_registry.nodes.get(node_id)
    if not node:
        return {"ok": False, "reason": "node_not_found"}

    try:
        resp = await client.post(
            f"{node['url']}/submit-task",
            json={"job_id": job_id},
            timeout=3.0
        )
        if resp.status_code == 200:
            return {"ok": True, "response": resp.json()}
        return {"ok": False, "reason": f"http_{resp.status_code}"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

def pick_best_node(exclude: Optional[List[str]] = None) -> Optional[str]:
    exclude = exclude or []
    available = [nid for nid in node_registry.get_available_nodes() if nid not in exclude]
    if not available:
        return None

    weighted_candidates = []
    for node_id in available:
        metrics = node_registry.nodes[node_id]['metrics']
        traffic_weight = metrics.get('routing_weight', cooling_off.get_weight(node_id))
        cpu_factor = max(0.1, 1.0 - (metrics.get('cpu', 0) / 100.0))
        selection_weight = max(MIN_TRAFFIC_WEIGHT, traffic_weight * cpu_factor)
        weighted_candidates.append((node_id, selection_weight))

    total_weight = sum(weight for _, weight in weighted_candidates)
    if total_weight <= 0:
        return min(available, key=lambda nid: node_registry.nodes[nid]['metrics']['cpu'])

    pick = random.uniform(0, total_weight)
    cumulative = 0.0
    for node_id, weight in weighted_candidates:
        cumulative += weight
        if pick <= cumulative:
            return node_id

    return weighted_candidates[-1][0]

@app.post("/api/nodes/register")
async def register_node(req: Request):
    body = await req.json()
    node_id = body.get('node_id')
    url = body.get('url')

    if not node_id or not url:
        raise HTTPException(status_code=400, detail="Missing node_id or url")

    node = node_registry.register(node_id, url)
    return {'status': 'registered', 'node': node}

@app.post("/api/nodes/{node_id}/recover")
async def recover_node_endpoint(node_id: str):
    async with httpx.AsyncClient() as client:
        result = await recover_node(client, node_id)

    if result.get("ok"):
        return {"status": "recovered", **result}

    return {
        "status": "failed",
        "recoverable": result.get("recoverable", False),
        **result,
    }

@app.post("/api/nodes/recover-all")
async def recover_all_nodes():
    results = []
    async with httpx.AsyncClient() as client:
        for node_id in list(node_registry.nodes.keys()):
            results.append(await recover_node(client, node_id))

    recovered = [r["node_id"] for r in results if r.get("ok")]
    pending = [r["node_id"] for r in results if not r.get("ok") and r.get("chaos_cleared")]
    failed = [r["node_id"] for r in results if not r.get("ok") and not r.get("chaos_cleared")]

    return {
        "status": "done",
        "recovered": recovered,
        "pending": pending,
        "failed": failed,
        "message": (
            f"Recovered {len(recovered)} node(s)."
            + (f" {len(pending)} still coming back online." if pending else "")
            + (f" {len(failed)} unreachable." if failed else "")
        ),
        "results": results,
    }

@app.delete("/api/nodes/{node_id}")
async def unregister_node(node_id: str):
    node_registry.unregister(node_id)
    return {'status': 'unregistered', 'node_id': node_id}

@app.get("/api/cluster-health")
async def get_health():
    async with httpx.AsyncClient() as client:
        tasks = [fetch_and_save(client, nid) for nid in node_registry.nodes.keys()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        results = [r for r in results if r is not None and not isinstance(r, Exception)]

    online_nodes = [n for n in results if n['status'] == 'Online']
    critical_nodes = [n['node_id'] for n in results if n['cpu'] >= CIRCUIT_BREAKER_THRESHOLD]
    open_circuits = [n['node_id'] for n in results if n.get('circuit_breaker') == 'OPEN']
    chaos_nodes = [n['node_id'] for n in results if n.get('chaos', {}) and n['chaos'].get('active')]
    throttled_nodes = [
        n['node_id'] for n in results
        if n.get('routing_weight', 1.0) < 0.8 or n.get('temperature_c', 0) >= THERMAL_THRESHOLD_C
    ]

    cluster_utilization = (sum(n['cpu'] for n in online_nodes) / len(online_nodes)) if online_nodes else 0

    if critical_nodes:
        log_msg = f"ALERT: High CPU on {', '.join(critical_nodes)}. Open circuits: {', '.join(open_circuits) or 'none'}"
    elif throttled_nodes:
        log_msg = (
            f"Thermal/latency throttling active on {', '.join(throttled_nodes)}. "
            f"Sentinel is reducing traffic while those nodes cool off."
        )
    elif open_circuits:
        log_msg = f"WARNING: {len(open_circuits)} circuit breaker(s) open. Recovery in progress."
    elif chaos_nodes:
        log_msg = f"Chaos active on {', '.join(chaos_nodes)}. Sentinel is rerouting around affected nodes."
    else:
        log_msg = f"Cluster stable. {len(online_nodes)}/{len(node_registry.nodes)} nodes online. Avg CPU {cluster_utilization:.1f}%."

    return {
        'nodes': results,
        'cluster_stats': {
            'total_nodes': len(node_registry.nodes),
            'online_nodes': len(online_nodes),
            'avg_cpu': cluster_utilization,
            'critical_nodes': critical_nodes,
            'open_circuits': open_circuits,
            'chaos_nodes': chaos_nodes,
            'throttled_nodes': throttled_nodes,
        },
        'log': log_msg,
        'timestamp': datetime.now().isoformat()
    }

@app.get("/api/history/{node_id}")
async def get_history(node_id: str, days: int = 0, seconds: int = 0):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()

    if seconds > 0:
        limit_date = (datetime.now() - timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S")
    else:
        limit_date = (datetime.now() - timedelta(days=min(days, 5))).strftime("%Y-%m-%d %H:%M:%S")

    c.execute(
        """SELECT cpu, ram, temperature_c, inference_latency_p99_ms, error_rate, routing_weight, timestamp
           FROM metrics WHERE node_id=? AND timestamp>=? ORDER BY timestamp ASC""",
        (node_id, limit_date)
    )
    data = c.fetchall()
    conn.close()

    return [{
        'time': row[6],
        'cpu': row[0],
        'ram': row[1],
        'temperature_c': row[2],
        'inference_latency_p99_ms': row[3],
        'error_rate': row[4],
        'routing_weight': row[5],
    } for row in data]

@app.post("/api/chaos/trigger")
async def trigger_chaos(req: Request):
    body = await req.json()
    node_id = body.get('node_id')
    action = body.get('action')
    duration = int(body.get('duration', 30))

    if not node_id or action not in CHAOS_ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid node_id or action")

    node = node_registry.nodes.get(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    url = resolve_worker_url(node_id)

    payload = {
        "action": action,
        "duration": duration,
        "latency_ms": int(body.get('latency_ms', 3500)),
        "drop_rate": int(body.get('drop_rate', 85)),
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{url}/chaos", json=payload, timeout=3.0)
            resp.raise_for_status()
            chaos_state = resp.json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to apply chaos on {node_id}: {str(e)}")

    node['chaos'] = chaos_state.get('chaos')
    log_chaos_event(node_id, action, duration)
    log_healing_event(
        node_id,
        "chaos_triggered",
        f"Chaos '{action}' applied to {node_id} for {duration}s. Watch routing shift away from this node."
    )

    action_labels = {
        "latency_spike": "latency spike",
        "packet_drop": "packet loss",
        "cpu_spike": "CPU overload",
        "thermal_spike": "thermal spike",
        "node_kill": "hard kill",
    }

    return {
        "status": "applied",
        "node_id": node_id,
        "action": action,
        "duration": duration,
        "chaos": node['chaos'],
        "message": f"Applied {action_labels.get(action, action)} to {node_id}. Sentinel should reroute within one telemetry cycle."
    }

@app.post("/api/chaos/reset")
async def reset_chaos(req: Request):
    body = await req.json() if req.headers.get('content-length') else {}
    node_id = body.get('node_id')

    if node_id:
        async with httpx.AsyncClient() as client:
            result = await recover_node(client, node_id)
        return {
            "status": "recovered" if result.get("ok") else "failed",
            "nodes": [node_id] if result.get("ok") or result.get("chaos_cleared") else [],
            "message": result.get("message"),
            "result": result,
        }

    async with httpx.AsyncClient() as client:
        for nid in list(node_registry.nodes.keys()):
            resolve_worker_url(nid)
        results = []
        for nid in list(node_registry.nodes.keys()):
            results.append(await recover_node(client, nid))

    recovered = [r["node_id"] for r in results if r.get("ok")]
    failed = [r for r in results if not r.get("ok")]
    return {
        "status": "reset",
        "nodes": recovered,
        "message": f"Recovery attempted on {len(results)} node(s). {len(recovered)} back online.",
        "failed_details": [
            {"node_id": r["node_id"], "message": r.get("message"), "reason": r.get("reason")}
            for r in failed
        ],
        "results": results,
    }

@app.get("/api/healing-log")
async def get_healing_log(limit: int = 40):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, node_id, event_type, message FROM healing_log ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [{
        'timestamp': row[0],
        'node_id': row[1],
        'event_type': row[2],
        'message': row[3],
    } for row in rows]

@app.get("/api/inference-log")
async def get_inference_log(limit: int = 30):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, job_id, target_node, status, detail FROM inference_log ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return [{
        'timestamp': row[0],
        'job_id': row[1],
        'target_node': row[2],
        'status': row[3],
        'detail': row[4],
    } for row in rows]

@app.post("/api/submit-job")
async def submit_job(req: Request):
    body = await req.json()
    job_id = body.get('job_id', f"job_{int(time.time())}")

    tried_nodes = []
    final_node = None
    rerouted = False

    async with httpx.AsyncClient() as client:
        await get_health()

        for attempt in range(3):
            candidate = pick_best_node(exclude=tried_nodes)
            if not candidate:
                break

            tried_nodes.append(candidate)
            node_metrics = node_registry.nodes[candidate]['metrics']
            cpu = node_metrics['cpu']
            result = await forward_job_to_node(client, candidate, job_id)

            if result["ok"]:
                final_node = candidate
                log_inference(
                    job_id,
                    candidate,
                    "delivered",
                    f"Job accepted by {candidate} at {cpu}% CPU, weight {node_metrics.get('routing_weight', 1.0):.0%}"
                )
                break

            rerouted = True
            circuit_breaker.open(candidate)
            log_inference(
                job_id,
                candidate,
                "rerouted",
                f"Delivery to {candidate} failed ({result['reason']}). Trying next node."
            )
            log_healing_event(
                candidate,
                "job_reroute",
                f"Job {job_id} could not reach {candidate}. Sentinel picked another node."
            )

    if not final_node:
        online = [nid for nid, n in node_registry.nodes.items() if n['status'] == 'Online']
        if not online:
            return {
                'status': 'Failed',
                'job_id': job_id,
                'message': 'Cluster offline. No nodes available to accept work.',
                'timestamp': datetime.now().isoformat()
            }
        return {
            'status': 'Queued',
            'job_id': job_id,
            'message': 'All healthy nodes rejected the job. It stays queued until capacity frees up.',
            'timestamp': datetime.now().isoformat()
        }

    final_metrics = node_registry.nodes[final_node]['metrics']
    best_cpu = final_metrics['cpu']
    routing_weight = final_metrics.get('routing_weight', 1.0)
    routing_reason = cooling_off.get_reason(final_node)
    reason = f"Weighted pick at {best_cpu}% CPU, weight {routing_weight:.0%} ({routing_reason})"
    if rerouted:
        reason = f"Self-healed reroute to {final_node} ({reason})"

    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute(
        "INSERT INTO routing_log (timestamp, job_id, source_node, target_node, decision_reason) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), job_id, 'orchestrator', final_node, reason)
    )
    conn.commit()
    conn.close()

    return {
        'status': 'Success',
        'job_id': job_id,
        'assigned_node': final_node,
        'node_url': node_registry.nodes[final_node]['url'],
        'node_load': f"{best_cpu}%",
        'routing_weight': routing_weight,
        'routing_reason': routing_reason,
        'rerouted': rerouted,
        'tried_nodes': tried_nodes,
        'message': (
            f"Job {job_id} delivered to {final_node} ({best_cpu}% CPU, weight {routing_weight:.0%})"
            + (" after reroute" if rerouted else "")
        ),
        'timestamp': datetime.now().isoformat()
    }

@app.get("/api/routing-log")
async def get_routing_log(limit: int = 50):
    conn = sqlite3.connect('sentinel_metrics.db')
    c = conn.cursor()
    c.execute("SELECT timestamp, job_id, target_node, decision_reason FROM routing_log ORDER BY id DESC LIMIT ?", (limit,))
    data = c.fetchall()
    conn.close()

    return [{
        'timestamp': row[0],
        'job_id': row[1],
        'target_node': row[2],
        'decision_reason': row[3]
    } for row in data]
