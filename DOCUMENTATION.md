# Sentinel AIOps — Project Documentation

**Version:** 2.2  
**Last updated:** June 2026

---

## Table of contents

1. [What is Sentinel?](#what-is-sentinel)
2. [What problem does it solve?](#what-problem-does-it-solve)
3. [How it works](#how-it-works)
4. [Architecture](#architecture)
5. [Features](#features)
6. [Tech stack](#tech-stack)
7. [Project structure](#project-structure)
8. [Getting started](#getting-started)
9. [Using the dashboard](#using-the-dashboard)
10. [API reference](#api-reference)
11. [Configuration](#configuration)
12. [Node recovery](#node-recovery)
13. [Chaos engineering lab](#chaos-engineering-lab)
14. [Scaling](#scaling)
15. [Troubleshooting](#troubleshooting)

---

## What is Sentinel?

Sentinel is an **AIOps load-balancing platform** that distributes inference jobs across a cluster of worker nodes. Unlike a basic round-robin or CPU-only load balancer, Sentinel watches **thermal telemetry**, **inference latency (p99)**, and **error rates** from each worker and throttles traffic to stressed nodes *before* they crash.

The system is built for demo and development use with four worker nodes out of the box, but the orchestrator is designed to scale to **1000+ nodes** through dynamic registration and async polling.

---

## What problem does it solve?

Standard load balancers react after a node is already failing — high CPU, timeouts, or a hard crash. Sentinel takes a proactive approach:

- If a node's **die temperature** crosses 75°C, its routing weight drops immediately.
- If **p99 inference latency** degrades relative to an adaptive baseline, traffic is reduced.
- If **error rate** exceeds 12%, the node enters a cooling-off period.
- A **circuit breaker** isolates nodes above 85% CPU.
- Failed job deliveries are **automatically rerouted** to another node.

The goal is graceful degradation: pull traffic away early, self-heal when possible, and keep the cluster serving work.

---

## How it works

### End-to-end flow

```
1. Worker nodes start and auto-register with the orchestrator.
2. Every 3 seconds, the orchestrator polls GET /health on each node.
3. Telemetry (CPU, RAM, temperature, p99 latency, error rate) is stored in SQLite.
4. The CoolingOffManager updates each node's routing weight (0.05 – 1.0).
5. When a job arrives via POST /api/submit-job, the orchestrator picks a node
   using weighted random selection (favoring low CPU and high routing weight).
6. The job is forwarded to the chosen node's POST /submit-task endpoint.
7. If delivery fails, the circuit breaker opens on that node and up to 2 more
   nodes are tried before the job is queued or marked failed.
8. The React dashboard polls /api/cluster-health every 3 seconds and renders
   live charts, logs, and chaos controls.
```

### Worker node internals

Each worker container runs two processes:

| Process | Port | Role |
|---------|------|------|
| **C++ monitor** (`monitor.cpp`) | 8080 | Simulates hardware metrics: CPU, RAM, die temperature. Reads inference stats from a shared telemetry file. |
| **Python receiver** (`receiver.py`) | 8081 | HTTP API facing the orchestrator. Handles `/health`, `/submit-task`, `/chaos`. Tracks inference latency and error rate. |

On startup, the receiver auto-registers with the orchestrator at `http://sentinel_orchestrator:8000/api/nodes/register`.

### Routing algorithm

Sentinel v2.2 uses **weighted random routing**, not pure least-CPU:

```
selection_weight = routing_weight × max(0.1, 1 - cpu/100)
```

- `routing_weight` is set by the CoolingOffManager (thermal, latency, errors).
- Lower CPU increases the chance of selection.
- Nodes in cooling-off still receive a minimum of 5% traffic unless the circuit breaker is open.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     React Dashboard  :5173                       │
│   Live metrics · Multi-metric charts · Chaos lab · Recovery UI   │
└─────────────────────────────┬────────────────────────────────────┘
                              │ HTTP (3s poll)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI Orchestrator  :8000                     │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────────────────────┐  │
│  │ Node        │ │ CoolingOff   │ │ Circuit Breaker           │  │
│  │ Registry    │ │ Manager      │ │ (85% CPU threshold)       │  │
│  └─────────────┘ └──────────────┘ └───────────────────────────┘  │
│  ┌─────────────────────────────┐ ┌────────────────────────────┐  │
│  │ SQLite (metrics, logs)      │ │ Weighted job router        │  │
│  └─────────────────────────────┘ └────────────────────────────┘  │
└─────────────────────────────┬────────────────────────────────────┘
                              │ Poll /health · Forward /submit-task
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌───────────┐       ┌───────────┐       ┌───────────┐
    │  node1    │       │  node2    │  ...  │  nodeN    │
    │ C++ :8080 │       │ C++ :8080 │       │ C++ :8080 │
    │ Py  :8081 │       │ Py  :8081 │       │ Py  :8081 │
    └───────────┘       └───────────┘       └───────────┘
```

### Docker network

All services run on the `cluster_net` bridge (`172.18.0.0/16`):

| Service | Container | IP |
|---------|-----------|-----|
| Orchestrator | `sentinel_orchestrator` | 172.18.0.100 |
| Dashboard | `sentinel_dashboard` | 172.18.0.101 |
| node1 – node4 | auto-named | 172.18.0.2 – 172.18.0.5 |

---

## Features

### Core load balancing

- **Dynamic node registration** — workers register on startup; registry persisted to `node_registry.json`.
- **Weighted routing** — combines CPU headroom with thermal/latency/error-driven routing weight.
- **Job rerouting** — up to 3 delivery attempts across different nodes on failure.
- **Job queuing** — jobs queue when all healthy nodes reject work.

### Thermal-aware cooling-off

- Die temperature reported from C++ workers (simulated, rises with CPU load).
- Threshold: **75°C** triggers weight reduction to ~25%.
- **30-second cooling-off period** even after metrics normalize.
- Gradual weight restoration when telemetry is healthy.

### Latency and error telemetry

- Python receiver tracks the last 100 inference samples per node.
- **p99 latency** compared against an adaptive per-node baseline.
- **Error rate** from failed health checks and rejected jobs.
- Both feed into routing weight decisions.

### Circuit breaking

- Opens when node CPU ≥ **85%**.
- **10-second cooldown** before the node re-enters the pool.
- Open circuits are excluded from job routing.

### Self-healing and recovery

- Automatic state transition logging (offline, recovered, circuit open/closed, traffic throttled).
- **Recover node** button per worker card in the dashboard.
- **Recover all** in the chaos lab.
- Detailed failure messages when recovery is not possible (container down, timeout, health rejected).
- Error messages auto-clear when the node returns to Online.

### Chaos engineering lab

Built-in fault injection for demos and resilience testing:

| Action | Effect |
|--------|--------|
| Spike latency | Health checks slow down; node may appear offline |
| Drop packets | Random health probe failures |
| Overload CPU | Forces CPU past circuit breaker threshold |
| Spike temperature | Pushes die temp past thermal threshold |
| Kill node | Worker stops responding to health and job requests |

Chaos auto-expires after 45 seconds unless reset manually.

### Dashboard

- Futuristic HUD-style UI (glass panels, animated background, Orbitron + JetBrains Mono fonts).
- Cluster stats: online nodes, avg CPU, open circuits, cooling-off count, chaos count.
- Per-node cards with CPU / RAM / temp, routing weight bar, status chips.
- **Multi-metric charts** — view CPU, RAM, temp individually, in pairs, or all three together (default: all three).
- Self-healing log, inference delivery log, router status panel.
- Built-in traffic generator (sends a job every 2 seconds).

### Persistence and history

- **SQLite** database: `orchestrator/sentinel_metrics.db`
- Tables: `metrics`, `routing_log`, `healing_log`, `inference_log`, `chaos_log`
- History API supports live window (10 seconds), 24 hours, 2 days, or 5 days.

---

## Tech stack

### Orchestrator

| Technology | Purpose |
|------------|---------|
| **Python 3.11+** | Runtime |
| **FastAPI** | HTTP API framework |
| **Uvicorn** | ASGI server |
| **httpx** | Async HTTP client for node polling |
| **SQLite** | Time-series metrics and logs |
| **asyncio** | Concurrent polling of all nodes |

### Worker nodes

| Technology | Purpose |
|------------|---------|
| **C++11** | Low-level hardware monitor (`monitor.cpp`) |
| **Python 3** | HTTP receiver and chaos state (`receiver.py`) |
| **Linux sockets** | C++ HTTP health server on port 8080 |

### Dashboard

| Technology | Purpose |
|------------|---------|
| **React 18** | UI framework |
| **TypeScript** | Type-safe components |
| **Vite 4** | Dev server and bundler |
| **Tailwind CSS 3** | Utility-first styling |
| **Recharts** | Area charts for telemetry |
| **Framer Motion** | Node card animations |
| **Lucide React** | Icons |

### Infrastructure

| Technology | Purpose |
|------------|---------|
| **Docker** | Container runtime |
| **Docker Compose** | Multi-service orchestration |
| **Ubuntu 22.04** | Base image for worker containers |

---

## Project structure

```
sentinal-node/
├── orchestrator/
│   ├── master.py              # FastAPI orchestrator (v2.2)
│   ├── requirements.txt       # Python dependencies
│   ├── Dockerfile
│   ├── node_registry.json     # Persisted node registry
│   └── sentinel_metrics.db    # SQLite metrics (created at runtime)
├── cluster/
│   ├── monitor.cpp            # C++ hardware / thermal monitor
│   ├── receiver.py            # Python worker HTTP API
│   ├── chaos_state.py         # In-memory chaos fault state
│   └── Dockerfile
├── dashboard/
│   ├── src/
│   │   ├── App.tsx            # Main dashboard
│   │   ├── index.css          # Global / HUD styles
│   │   └── components/
│   │       ├── ChaosPanel.tsx
│   │       └── NodeMetricsChart.tsx
│   ├── package.json
│   ├── Dockerfile
│   ├── vite.config.ts
│   └── tailwind.config.js
├── docker-compose.yml         # 4 nodes + orchestrator + dashboard
├── load-generator.py          # Standalone traffic script
├── README.md                  # Original project readme
└── DOCUMENTATION.md           # This file
```

---

## Getting started

### Prerequisites

- **Docker** and **Docker Compose** (recommended)
- Optional for local dev: Node.js 18+, Python 3.11+, g++

### Option 1 — Docker Compose (recommended)

```bash
# From the project root
cd sentinal-node

# Build and start all services
docker compose up --build
```

Wait until you see the orchestrator, dashboard, and all four nodes running.

**Access points:**

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| Orchestrator API | http://localhost:8000 |
| Swagger API docs | http://localhost:8000/docs |

### Option 2 — Local development

**Orchestrator:**

```bash
cd orchestrator
pip install -r requirements.txt
python -m uvicorn master:app --host 0.0.0.0 --port 8000 --reload
```

**Dashboard:**

```bash
cd dashboard
npm install
npm run dev
```

**Worker node** (requires Linux for C++ socket code):

```bash
cd cluster
g++ -o monitor monitor.cpp -std=c++11
./monitor 8080 node1 &
NODE_ID=node1 NODE_PORT=8081 python3 receiver.py
```

### Verify the cluster

```bash
curl http://localhost:8000/api/cluster-health
```

You should see four nodes with `"status": "Online"`.

### Submit a test job

```bash
curl -X POST http://localhost:8000/api/submit-job \
  -H "Content-Type: application/json" \
  -d '{"job_id": "test_job_1", "task_type": "inference"}'
```

### Stop the stack

```bash
docker compose down
```

---

## Using the dashboard

1. Open **http://localhost:5173**.
2. The header shows live telemetry status and a **Route one job** button.
3. Cluster stat cards summarize online nodes, CPU, circuits, cooling-off, and chaos.
4. **Chaos lab** — select a target node, start traffic, then inject faults. Use **Recover all** to reset every node.
5. **Worker nodes** section — each card shows metrics, routing weight, and a telemetry chart.
6. Use **Chart metrics** pills to switch between CPU, RAM, temp, pairs, or all three.
7. Click **Recover node** on any degraded or offline card to attempt recovery.
8. Bottom panels show self-healing events, inference delivery, and router status.

---

## API reference

### Cluster health

```
GET /api/cluster-health
```

Returns all nodes, cluster stats, and a human-readable status log.

### Node management

```
POST /api/nodes/register
Body: { "node_id": "node5", "url": "http://node5:8081" }

DELETE /api/nodes/{node_id}

POST /api/nodes/{node_id}/recover
POST /api/nodes/recover-all
```

### Jobs

```
POST /api/submit-job
Body: { "job_id": "job_123", "task_type": "inference" }
```

Response includes `assigned_node`, `routing_weight`, `rerouted`, and `tried_nodes`.

### History

```
GET /api/history/{node_id}?seconds=10
GET /api/history/{node_id}?days=5
```

Returns CPU, RAM, temperature, p99 latency, error rate, and routing weight over time.

### Chaos

```
POST /api/chaos/trigger
Body: {
  "node_id": "node1",
  "action": "thermal_spike",
  "duration": 45
}

POST /api/chaos/reset
Body: {}                  # recover all
Body: { "node_id": "node1" }  # recover one
```

Valid actions: `latency_spike`, `packet_drop`, `cpu_spike`, `thermal_spike`, `node_kill`.

### Logs

```
GET /api/routing-log?limit=50
GET /api/healing-log?limit=40
GET /api/inference-log?limit=30
```

---

## Configuration

Edit constants at the top of `orchestrator/master.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_THRESHOLD` | 85 | CPU % that opens the circuit |
| `CIRCUIT_BREAKER_COOLDOWN` | 10 | Seconds before circuit closes |
| `TELEMETRY_POLL_INTERVAL` | 3 | Dashboard/orchestrator poll interval (seconds) |
| `THERMAL_THRESHOLD_C` | 75 | Die temp (°C) that triggers throttling |
| `P99_LATENCY_BASELINE_MS` | 120 | Initial p99 baseline per node |
| `P99_VARIANCE_FACTOR` | 1.8 | Multiplier over baseline that triggers throttling |
| `ERROR_RATE_THRESHOLD` | 0.12 | Error rate (12%) that triggers throttling |
| `COOLING_OFF_DURATION` | 30 | Seconds of reduced weight after a trigger |
| `MIN_TRAFFIC_WEIGHT` | 0.05 | Minimum routing weight (5%) |

---

## Node recovery

### When recovery works

Recovery clears chaos on the worker, closes the circuit breaker, resets routing weight to 100%, and re-polls health. It works well when the worker process is still running but was affected by simulated chaos.

### When recovery fails

The orchestrator returns a specific message explaining why:

| Reason | Meaning | Fix |
|--------|---------|-----|
| `container_unreachable` | Worker not accepting connections | `docker compose restart nodeX` |
| `chaos_reset_timeout` | Worker hung, no response in 3s | Restart container |
| `health_timeout` | Chaos cleared but health timed out | Wait and retry, or restart |
| `health_rejected` | Worker still returning HTTP errors | Retry Recover, or restart |
| `node_not_found` | Node not in registry | Re-register the node |

Failure messages appear on the node card and in the status panel. They disappear automatically when the node returns to Online.

---

## Chaos engineering lab

The chaos lab is designed to demonstrate Sentinel's self-healing behavior:

1. Click **Start traffic** to send jobs every 2 seconds.
2. Select a target node.
3. Trigger a fault (e.g. **Spike temperature**).
4. Watch routing weight drop and traffic shift to other nodes within one telemetry cycle (3 seconds).
5. Click **Recover node** or **Recover all** to restore the cluster.

Chaos also auto-expires after 45 seconds.

---

## Scaling

The orchestrator polls all registered nodes concurrently with `asyncio.gather`. To add more nodes:

1. Add services to `docker-compose.yml` (copy a `nodeN` block).
2. Set `NODE_ID` and a unique IP on `cluster_net`.
3. Nodes auto-register on startup.

For large deployments (100+ nodes), consider Kubernetes StatefulSets or a compose generator script. The node registry and async architecture are built to support 1000+ nodes in theory; network and poll latency become the practical limits.

---

## Troubleshooting

### Nodes show Offline

- Check containers: `docker compose ps`
- Try **Recover node** in the dashboard.
- Restart a node: `docker compose restart node1`
- Check orchestrator logs: `docker compose logs orchestrator`

### Dashboard cannot reach API

- Confirm orchestrator is on port 8000.
- The dashboard calls `http://127.0.0.1:8000` — use localhost, not the Docker internal hostname, when accessing from your browser.

### Nodes not registering

- Ensure the orchestrator starts before workers (workers retry 15 times).
- Manually register:
  ```bash
  curl -X POST http://localhost:8000/api/nodes/register \
    -H "Content-Type: application/json" \
    -d '{"node_id": "node1", "url": "http://node1:8081"}'
  ```

### Reset metrics database

```bash
rm orchestrator/sentinel_metrics.db
# Restart orchestrator — tables are recreated automatically
```

### CSS build error (`@apply` with `group`)

If Tailwind reports `@apply should not be used with the 'group' utility`, ensure `group` is on the JSX element, not inside `@apply` in CSS. This is already fixed in the current codebase.

---

## License

Proprietary — Sentinel AIOps Project (2024–2026)

---

## Quick reference card

```
Start:     docker compose up --build
Dashboard: http://localhost:5173
API:       http://localhost:8000/docs
Submit:    POST /api/submit-job
Recover:   POST /api/nodes/{id}/recover
Chaos:     POST /api/chaos/trigger
Stop:      docker compose down
```
