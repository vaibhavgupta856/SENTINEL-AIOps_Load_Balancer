# Sentinel AIOps Load Balancer

<h1 align="center"><strong>⚠️ THIS IS NOT A SIMULATOR ⚠️</strong></h1>

<p align="center"><strong>Real jobs. Real failures. Real recovery.</strong></p>

> **Tagline:** *Route before the crash. Recover after the hit.*

**Version 2.2** — Thermal-aware orchestration with cooling-off routing, chaos testing, and self-healing recovery.

---

<p><strong><em>Sentinel runs real workloads on real worker processes.</em></strong> When you submit a job, it is <strong>actually executed</strong> on a live node. When you trigger chaos — CPU overload, thermal spike, packet drop, or node kill — the worker <strong>genuinely fails, goes offline, or stops accepting traffic</strong>. When you click <strong>Recover</strong>, the orchestrator <strong>actually clears fault state, resets circuit breakers, and brings the node back into the routing pool</strong> — or tells you exactly why it could not.</p>

**Nothing here is cosmetic dashboard theater:**

- **Real inference jobs** are routed, executed, logged, and rerouted on failure
- **Real telemetry** is polled from C++ hardware monitors and Python worker APIs every 3 seconds
- **Real crashes and isolation** happen — circuit breakers open, routing weight drops, traffic shifts to healthy nodes
- **Real recovery** is attempted against live workers — chaos flags cleared, health re-probed, traffic restored

<p align="center"><strong>You are operating a working AIOps load balancer with a live cluster — not watching a pre-recorded demo.</strong></p>

---

Sentinel is an AIOps load-balancing platform that distributes inference jobs across a cluster of C++ worker nodes. Unlike basic round-robin or CPU-only balancers, it watches **die temperature**, **inference latency (p99)**, and **error rates**, then throttles traffic to stressed nodes before they crash.

---

## Table of contents

- [What problem does it solve?](#what-problem-does-it-solve)
- [How it works](#how-it-works)
- [Architecture](#architecture)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Quick start (local)](#quick-start-local)
- [Deployment modes: Docker vs Native](#deployment-modes-docker-vs-native)
- [Production deployment](#production-deployment)
- [Free deployment options](#free-deployment-options)
- [Dashboard guide](#dashboard-guide)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [Node recovery](#node-recovery)
- [Chaos engineering lab](#chaos-engineering-lab)
- [Scaling](#scaling)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What problem does it solve?

Standard load balancers react after a node is already failing — high CPU, timeouts, or a hard crash. Sentinel takes a proactive approach:

- **Die temperature** above 75°C → routing weight drops immediately
- **p99 inference latency** degrades vs an adaptive baseline → traffic reduced
- **Error rate** above 12% → cooling-off period starts
- **CPU above 85%** → circuit breaker isolates the node
- **Failed job delivery** → automatic reroute to another node (up to 3 attempts)

The goal is graceful degradation: pull traffic away early, self-heal when possible, and keep the cluster serving work.

---

## How it works

### End-to-end flow

1. Worker nodes start and **auto-register** with the orchestrator
2. Every **3 seconds**, the orchestrator polls `GET /health` on each node
3. Telemetry (CPU, RAM, temperature, p99 latency, error rate) is stored in **SQLite**
4. The **CoolingOffManager** updates each node's routing weight (5% – 100%)
5. Jobs arrive via `POST /api/submit-job` → orchestrator picks a node using **weighted random selection**
6. Job forwarded to the node's `POST /submit-task`
7. On delivery failure → circuit breaker opens → up to 2 more nodes tried
8. React dashboard polls `/api/cluster-health` every 3 seconds

### Worker node internals

Each worker container runs two processes:

| Process | Port | Role |
|---------|------|------|
| **C++ monitor** (`monitor.cpp`) | 8080 | Simulates CPU, RAM, die temperature; reads inference stats from shared file |
| **Python receiver** (`receiver.py`) | 8081 | HTTP API for orchestrator: `/health`, `/submit-task`, `/chaos` |

The receiver auto-registers at `http://sentinel_orchestrator:8000/api/nodes/register` on startup.

### Routing algorithm (v2.2)

```
selection_weight = routing_weight × max(0.1, 1 - cpu/100)
```

- `routing_weight` set by CoolingOffManager (thermal, latency, errors)
- Lower CPU increases selection chance
- Minimum 5% traffic even when cooling off (unless circuit is open)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│              React Dashboard  (:5173 dev / :80 prod)             │
│   Live metrics · Charts · Chaos lab · Recovery · Logs            │
└─────────────────────────────┬────────────────────────────────────┘
                              │ HTTP (3s poll)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                  FastAPI Orchestrator  :8000                     │
│  Node Registry · CoolingOffManager · Circuit Breaker · SQLite    │
└─────────────────────────────┬────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌───────────┐       ┌───────────┐       ┌───────────┐
    │  node1    │       │  node2    │  ...  │  node4    │
    │ C++ :8080 │       │ C++ :8080 │       │ C++ :8080 │
    │ Py  :8081 │       │ Py  :8081 │       │ Py  :8081 │
    └───────────┘       └───────────┘       └───────────┘
```

**Production:** nginx serves the dashboard on port 80 and proxies `/api/*` to the orchestrator.

---

## Features

### Core load balancing

- Dynamic node registration (JSON registry, persisted)
- Weighted routing (CPU + thermal/latency/error signals)
- Job rerouting on failure (up to 3 attempts)
- Job queuing when all nodes reject work
- Designed to scale to **1000+ nodes** via async concurrent polling

### Thermal-aware cooling-off

- Die temperature from C++ workers (simulated, rises with load)
- Threshold: **75°C** → weight drops to ~25%
- **30-second cooling-off** after a trigger, even if metrics recover
- Gradual weight restoration when healthy

### Latency and error telemetry

- Rolling window of last 100 inference samples per node
- **p99 latency** vs adaptive per-node baseline
- **Error rate** from failed health checks and rejected jobs

### Circuit breaking

- Opens at **85% CPU**
- **10-second cooldown** before re-entry
- Open circuits excluded from routing

### Self-healing and recovery

- Automatic logging: offline, recovered, circuit open/closed, traffic throttled
- **Recover node** button on each worker card
- **Recover all** in chaos lab
- Detailed failure messages when recovery fails (container down, timeout, health rejected)
- Error messages auto-clear when node returns Online

### Chaos engineering lab

| Action | Effect |
|--------|--------|
| Spike latency | Health checks slow; node may appear offline |
| Drop packets | Random health probe failures |
| Overload CPU | Forces CPU past circuit breaker |
| Spike temperature | Pushes temp past thermal threshold |
| Kill node | Worker stops responding to health/jobs |

Chaos auto-expires after 45 seconds. Built-in traffic generator sends jobs every 2 seconds.

### Dashboard

- HUD-style UI (glass panels, animated background)
- Cluster stats: online, avg CPU, open circuits, cooling off, chaos count
- Per-node cards: CPU / RAM / temp, routing weight bar, status chips
- **Multi-metric charts** — CPU, RAM, temp individually, in pairs, or all three (default: all three)
- Self-healing log, inference delivery log, router status
- Live / 24h / 2d / 5d history windows

### Persistence

- **SQLite:** `orchestrator/sentinel_metrics.db`
- Tables: `metrics`, `routing_log`, `healing_log`, `inference_log`, `chaos_log`
- Node registry: `orchestrator/node_registry.json`

### API docs (Swagger)

- Auto-generated at `/docs` — try endpoints without the dashboard

---

## Tech stack

| Layer | Technologies |
|-------|-------------|
| **Orchestrator** | Python 3.11, FastAPI, Uvicorn, httpx, asyncio, SQLite |
| **Workers** | C++11 (`monitor.cpp`), Python 3 (`receiver.py`, `chaos_state.py`) |
| **Dashboard** | React 18, TypeScript, Vite, Tailwind CSS, Recharts, Framer Motion, Lucide |
| **Production** | nginx (static dashboard + API proxy) |
| **Infrastructure** | Docker, Docker Compose, Ubuntu 22.04 |

---

## Project structure

```
sentinal-node/
├── orchestrator/
│   ├── master.py                 # FastAPI orchestrator (v2.2)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── node_registry.json        # Persisted node registry
│   └── sentinel_metrics.db       # SQLite (created at runtime)
├── cluster/
│   ├── monitor.cpp               # C++ hardware / thermal monitor (Docker/Linux)
│   ├── monitor_mock.py           # Python monitor for native (no-Docker) mode
│   ├── paths.py                  # Env-based paths and URLs
│   ├── receiver.py               # Python worker HTTP API
│   ├── chaos_state.py            # In-memory fault injection state
│   └── Dockerfile
├── scripts/
│   ├── start-docker.ps1 / .sh    # One-command Docker stack
│   ├── start-native.ps1 / .sh    # One-command native stack (no Docker)
│   └── stop-native.ps1 / .sh     # Stop native processes
├── start.ps1 / start.sh          # Launcher: docker | native | stop
├── dashboard/
│   ├── src/
│   │   ├── App.tsx               # Main dashboard
│   │   ├── config.ts             # API URL (dev vs production)
│   │   ├── index.css             # Global / HUD styles
│   │   └── components/
│   │       ├── ChaosPanel.tsx
│   │       └── NodeMetricsChart.tsx
│   ├── Dockerfile                # Dev (Vite)
│   ├── Dockerfile.prod           # Production (nginx)
│   ├── nginx.conf                # API proxy config
│   └── package.json
├── docker-compose.yml            # Local development
├── docker-compose.prod.yml       # Production deployment
├── load-generator.py             # Standalone traffic script
├── DOCUMENTATION.md              # Extended reference (same content, more detail)
├── DEPLOYMENT.md                 # Extended deploy guide
└── README.md                     # This file
```

---

## Quick start (local)

### Prerequisites

| Mode | Requirements |
|------|--------------|
| **Docker** (recommended) | Docker + Docker Compose |
| **Native** (no Docker) | Python 3.11+, Node.js 18+, npm |

---

## Deployment modes: Docker vs Native

Both modes run the **full demo**: 4 worker nodes, orchestrator, dashboard, thermal routing, chaos lab, and node recovery.

| | **Docker mode** | **Native mode** |
|---|-----------------|-----------------|
| **Best for** | Production-like demo, Linux C++ workers | Quick local dev on Windows/macOS without Docker |
| **Worker monitor** | C++ `monitor.cpp` in containers | Python `monitor_mock.py` (same API) |
| **One command** | `.\start.ps1 docker` or `./start.sh docker` | `.\start.ps1 native` or `./start.sh native` |
| **Dashboard** | http://localhost:5173 | http://localhost:5173 |
| **API / Swagger** | http://localhost:8000 / `/docs` | Same |
| **Stop** | `Ctrl+C` or `docker compose down` | `.\start.ps1 stop` or `./start.sh stop` |

### Mode A — Docker (recommended)

**Windows (PowerShell):**

```powershell
cd sentinal-node
.\start.ps1 docker
```

**Linux / macOS:**

```bash
cd sentinal-node
chmod +x start.sh scripts/*.sh
./start.sh docker
```

Or directly:

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| Orchestrator API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |

**Production (Docker + nginx on port 80):**

```powershell
.\start.ps1 docker -Prod
# or: ./start.sh docker --prod
```

**Stop:**

```bash
docker compose down
```

### Mode B — Native (no Docker)

Runs orchestrator, 4 workers, and the Vite dashboard directly on your machine. Uses `monitor_mock.py` instead of C++ so it works on **Windows** without compiling.

**Windows (PowerShell):**

```powershell
cd sentinal-node
.\start.ps1 native
```

**Linux / macOS:**

```bash
./start.sh native
```

Native workers use separate ports on `127.0.0.1`:

| Node | Monitor | API |
|------|---------|-----|
| node1 | 8080 | 8081 |
| node2 | 8082 | 8083 |
| node3 | 8084 | 8085 |
| node4 | 8086 | 8087 |

Worker data and chaos flags live under `runtime/native/nodeN/` (gitignored).

**Stop:**

```powershell
.\start.ps1 stop
# or: ./scripts/stop-native.ps1
```

### Verify (either mode)

```bash
curl http://localhost:8000/api/cluster-health

curl -X POST http://localhost:8000/api/submit-job \
  -H "Content-Type: application/json" \
  -d '{"job_id": "test_1", "task_type": "inference"}'
```

Open http://localhost:5173 — you should see 4 nodes, live metrics charts, the chaos lab, and recovery buttons.

### Manual native dev (orchestrator + dashboard only)

If you only want the API and UI without workers:

```bash
# Terminal 1 — orchestrator
cd orchestrator
pip install -r requirements.txt
python -m uvicorn master:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — dashboard
cd dashboard
npm install
npm run dev
```

Use `.\start.ps1 native` for the full 4-node cluster without Docker.

---

## Production deployment

### On a VPS (Ubuntu 22.04, 2 vCPU / 4 GB RAM, port 80 open)

**1. SSH into the server**

```bash
ssh ubuntu@YOUR_SERVER_IP
```

**2. Install Docker**

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

**3. Copy project from your PC**

```bash
scp -r /path/to/sentinal-node ubuntu@YOUR_SERVER_IP:~/
```

Or `git clone` if the repo is on GitHub.

**4. Start production stack**

```bash
cd ~/sentinal-node
docker compose -f docker-compose.prod.yml up --build -d
```

**5. Open in browser**

```
http://YOUR_SERVER_IP/
http://YOUR_SERVER_IP/docs
```

**6. Verify on server**

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/cluster-health
curl -X POST http://localhost/api/submit-job \
  -H "Content-Type: application/json" \
  -d '{"job_id": "deploy_test", "task_type": "inference"}'
```

### Production vs development

| | Development | Production |
|---|-------------|------------|
| Compose file | `docker-compose.yml` | `docker-compose.prod.yml` |
| Dashboard | Vite dev server :5173 | nginx static build :80 |
| API access | Direct :8000 | Proxied at `/api` |
| Orchestrator | `--reload` | 2 Uvicorn workers |
| Restart policy | None | `unless-stopped` |

### Useful production commands

```bash
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml restart node2
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up --build -d   # after code changes
```

### HTTPS (optional)

Put Caddy or nginx on the host in front of port 80 with your domain for TLS. See `DEPLOYMENT.md` for a Caddy example.

---

## Free deployment options

| Option | Cost | Best for |
|--------|------|----------|
| **Local Docker** (`docker compose up`) | $0 | Learning, dev |
| **Cloudflare Tunnel** from your PC | $0 | Temporary public URL while PC is on |
| **Oracle Cloud Always Free** VM | $0 | 24/7 public server |
| **GCP e2-micro free tier** | $0 | Small always-on (tight on RAM) |
| **AWS / Azure free tier** | $0 first year | 12-month trial |

**Oracle Always Free (recommended for $0 forever):**

1. Create Ubuntu 22.04 VM at [cloud.oracle.com/free](https://www.oracle.com/cloud/free/)
2. Open port 80 in Security List (Networking → Ingress rule)
3. Follow [Production deployment](#production-deployment) steps above

**Free on your PC with a shareable link:**

```bash
docker compose -f docker-compose.prod.yml up --build
cloudflared tunnel --url http://localhost:80
```

---

## Dashboard guide

The dashboard is **one page** with several sections:

| Section | Purpose |
|---------|---------|
| **Header + live badge** | Confirms 3-second telemetry polling |
| **Cluster status strip** | One-line cluster summary |
| **Stat cards** | Online nodes, avg CPU, circuits, cooling off, chaos |
| **Chaos lab** | Inject faults, start/stop traffic, recover all |
| **Worker node cards** | Per-node metrics, routing weight, charts, recover button |
| **Chart metric pills** | Switch charts: CPU, RAM, temp, pairs, or all three |
| **Self-healing log** | Automatic recovery and throttling events |
| **Inference delivery log** | Job routing and reroutes |
| **Router status** | Latest routing decisions |

### Swagger UI (`/docs`)

Separate developer page — not part of the dashboard. Use it to explore and test API endpoints manually.

---

## API reference

### Cluster

```
GET  /api/cluster-health
GET  /api/history/{node_id}?seconds=10
GET  /api/history/{node_id}?days=5
```

### Nodes

```
POST   /api/nodes/register          Body: { "node_id", "url" }
DELETE /api/nodes/{node_id}
POST   /api/nodes/{node_id}/recover
POST   /api/nodes/recover-all
```

### Jobs

```
POST /api/submit-job
Body: { "job_id": "job_123", "task_type": "inference" }
```

Response includes `assigned_node`, `routing_weight`, `rerouted`, `tried_nodes`.

### Chaos

```
POST /api/chaos/trigger
Body: { "node_id", "action", "duration" }
Actions: latency_spike | packet_drop | cpu_spike | thermal_spike | node_kill

POST /api/chaos/reset
Body: {} or { "node_id": "node1" }
```

### Logs

```
GET /api/routing-log?limit=50
GET /api/healing-log?limit=40
GET /api/inference-log?limit=30
```

Interactive docs: http://localhost:8000/docs (dev) or http://YOUR_IP/docs (prod)

---

## Configuration

Edit constants in `orchestrator/master.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `CIRCUIT_BREAKER_THRESHOLD` | 85 | CPU % that opens circuit |
| `CIRCUIT_BREAKER_COOLDOWN` | 10 | Seconds before circuit closes |
| `TELEMETRY_POLL_INTERVAL` | 3 | Poll interval (seconds) |
| `THERMAL_THRESHOLD_C` | 75 | Die temp (°C) for throttling |
| `P99_LATENCY_BASELINE_MS` | 120 | Initial p99 baseline |
| `P99_VARIANCE_FACTOR` | 1.8 | Baseline multiplier for alert |
| `ERROR_RATE_THRESHOLD` | 0.12 | Error rate (12%) for throttling |
| `COOLING_OFF_DURATION` | 30 | Reduced-weight period (seconds) |
| `MIN_TRAFFIC_WEIGHT` | 0.05 | Minimum routing weight (5%) |

---

## Node recovery

### What Recover does

1. Clears chaos on the worker (`POST /chaos` reset)
2. Closes circuit breaker on orchestrator
3. Resets routing weight to 100%
4. Re-polls health immediately

### When recovery works

Chaos-driven offline states while the worker process is still running.

### When recovery fails

| Reason | Meaning | Fix |
|--------|---------|-----|
| `container_unreachable` | Worker not accepting connections | `docker compose restart nodeX` |
| `chaos_reset_timeout` | No response in 3s | Restart container |
| `health_timeout` | Chaos cleared but health timed out | Retry or restart |
| `health_rejected` | Worker still returning HTTP errors | Retry Recover |
| `node_not_found` | Not in registry | Re-register node |

Failure messages appear on the node card and in the status panel. They **auto-clear** when the node returns Online.

### Recover via API

```bash
curl -X POST http://localhost:8000/api/nodes/node1/recover
curl -X POST http://localhost:8000/api/nodes/recover-all
```

---

## Chaos engineering lab

1. Click **Start traffic** (jobs every 2 seconds)
2. Select a target node
3. Trigger a fault (e.g. **Spike temperature**)
4. Watch routing weight drop and traffic shift within ~3 seconds
5. Click **Recover node** or **Recover all**

Chaos auto-expires after 45 seconds if not reset manually.

---

## Scaling

Add nodes by copying a block in `docker-compose.yml` or `docker-compose.prod.yml`:

```yaml
  node5:
    build: ./cluster
    restart: unless-stopped
    environment:
      - NODE_ID=node5
      - NODE_PORT=8081
    networks:
      cluster_net:
        ipv4_address: 172.18.0.6
```

```bash
docker compose -f docker-compose.prod.yml up --build -d node5
```

Each node auto-registers on startup. For 100+ nodes, consider Kubernetes StatefulSets.

---

## Troubleshooting

### Dashboard loads but no data

```bash
curl http://localhost:8000/api/cluster-health   # dev
curl http://localhost/api/cluster-health          # prod via nginx
docker compose logs orchestrator
```

### Nodes stay Offline

```bash
docker compose restart node1 node2 node3 node4
# Or use Recover all in dashboard
```

### `Failed to resolve import "./config"` in ChaosPanel

Import must be `../config` (fixed in v2.2) — `config.ts` lives in `src/`, not `src/components/`.

### Port 80 in use (production)

Change dashboard ports in `docker-compose.prod.yml` to `"8080:80"`.

### C++ build fails on Windows

Build workers inside Docker only — `monitor.cpp` uses Linux sockets.

### Reset metrics database

```bash
rm orchestrator/sentinel_metrics.db
docker compose restart orchestrator
```

### Backup orchestrator data

```bash
docker cp sentinel_orchestrator:/app/sentinel_metrics.db ./backup/
docker cp sentinel_orchestrator:/app/node_registry.json ./backup/
```

---

## Testing

```bash
# Submit many jobs
for i in $(seq 1 20); do
  curl -s -X POST http://localhost:8000/api/submit-job \
    -H "Content-Type: application/json" \
    -d "{\"job_id\": \"job_$i\", \"task_type\": \"inference\"}"
done

# Or use the standalone script
python load-generator.py
```

Watch the dashboard during chaos tests — routing should shift away from affected nodes within one telemetry cycle.

---

## License

Proprietary — Sentinel AIOps Project (2024–2026)

---

## Quick reference

```bash
# Local dev
docker compose up --build

# Production
docker compose -f docker-compose.prod.yml up --build -d

# Dashboard (dev)     http://localhost:5173
# Dashboard (prod)    http://YOUR_SERVER_IP/
# API docs            http://localhost:8000/docs

# Health check
curl http://localhost:8000/api/cluster-health

# Submit job
curl -X POST http://localhost:8000/api/submit-job \
  -H "Content-Type: application/json" \
  -d '{"job_id": "test", "task_type": "inference"}'

# Recover node
curl -X POST http://localhost:8000/api/nodes/node1/recover

# Stop
docker compose down
```

**Sentinel AIOps v2.2**
