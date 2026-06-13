# Deploying Sentinel

This guide covers how to run the full Sentinel stack — orchestrator, dashboard, and four worker nodes — in development and production.

---

## What gets deployed

| Component | Role | Dev port | Production port |
|-----------|------|----------|-----------------|
| **Orchestrator** | FastAPI brain — routing, telemetry, recovery | 8000 | Internal (proxied) |
| **Dashboard** | React UI | 5173 | **80** |
| **node1 – node4** | C++ monitor + Python worker | Internal | Internal |

---

## Prerequisites

- **Docker** 24+ and **Docker Compose** v2
- **4 GB RAM** minimum (comfortable for 4 nodes + orchestrator + dashboard)
- **Linux server** for production (Ubuntu 22.04 recommended), or Windows/Mac for local dev
- Open port **80** (production) or **5173 + 8000** (local dev)

Verify Docker works:

```bash
docker --version
docker compose version
```

---

## Option 1 — Local development (fastest)

Best for coding and testing on your machine.

```bash
cd sentinal-node
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| Orchestrator API | http://localhost:8000 |
| Swagger docs | http://localhost:8000/docs |

This uses Vite dev server (hot reload) and orchestrator with `--reload`. The dashboard talks directly to `http://127.0.0.1:8000`.

**Stop:**

```bash
docker compose down
```

---

## Option 2 — Production on a VPS (recommended)

Best for a demo server, portfolio deployment, or single-machine production.

### Step 1 — Get a server

Any cloud VM works (AWS EC2, DigitalOcean, Hetzner, Azure, etc.):

- **OS:** Ubuntu 22.04 LTS
- **Size:** 2 vCPU / 4 GB RAM
- **Open inbound port:** 80 (HTTP)

### Step 2 — Install Docker on the server

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in, then:
docker compose version
```

### Step 3 — Copy the project to the server

```bash
# From your local machine
scp -r sentinal-node user@YOUR_SERVER_IP:~/
```

Or clone from Git if you have pushed the repo:

```bash
git clone <your-repo-url> sentinal-node
cd sentinal-node
```

### Step 4 — Build and start (production compose)

```bash
cd sentinal-node
docker compose -f docker-compose.prod.yml up --build -d
```

This will:

- Build the orchestrator with **2 Uvicorn workers** (no dev reload)
- Build the dashboard as a **static React app served by nginx**
- nginx proxies `/api/*` to the orchestrator (same origin — no CORS issues)
- Start **4 worker nodes** that auto-register with the orchestrator
- Set `restart: unless-stopped` on all services

### Step 5 — Verify

```bash
# All containers running?
docker compose -f docker-compose.prod.yml ps

# Cluster healthy?
curl http://localhost/api/cluster-health

# Submit a test job
curl -X POST http://localhost/api/submit-job \
  -H "Content-Type: application/json" \
  -d '{"job_id": "deploy_test", "task_type": "inference"}'
```

Open in your browser:

```
http://YOUR_SERVER_IP/
```

Swagger API docs (proxied through nginx):

```
http://YOUR_SERVER_IP/docs
```

### Step 6 — View logs

```bash
# All services
docker compose -f docker-compose.prod.yml logs -f

# One service
docker compose -f docker-compose.prod.yml logs -f orchestrator
docker compose -f docker-compose.prod.yml logs -f node1
```

### Step 7 — Stop / update

```bash
# Stop
docker compose -f docker-compose.prod.yml down

# Rebuild after code changes
docker compose -f docker-compose.prod.yml up --build -d
```

---

## Option 3 — HTTPS with a domain (production + TLS)

Put **Caddy** or **nginx** in front of port 80 for automatic HTTPS.

### Example with Caddy (simplest)

Install Caddy on the host, then create `/etc/caddy/Caddyfile`:

```
sentinel.yourdomain.com {
    reverse_proxy localhost:80
}
```

Run Sentinel on an internal port instead — edit `docker-compose.prod.yml`:

```yaml
dashboard:
  ports:
    - "8080:80"   # bind internal port, Caddy handles 443
```

Then:

```bash
sudo caddy reload
```

Your dashboard is now at `https://sentinel.yourdomain.com`.

---

## Architecture in production

```
Internet
    │
    ▼
┌─────────────────┐
│  nginx :80      │  ← dashboard (static React build)
│  /api → proxy   │  ← forwards to orchestrator
└────────┬────────┘
         │  cluster_net (172.18.0.0/16)
         ▼
┌─────────────────┐     ┌──────────┐
│ orchestrator    │────▶│ node1-4  │
│ :8000 (internal)│     │ :8081    │
└─────────────────┘     └──────────┘
```

Workers register at `http://sentinel_orchestrator:8000` over the Docker network. The browser never talks to workers directly.

---

## Adding more worker nodes

Copy a node block in `docker-compose.prod.yml`:

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

Then:

```bash
docker compose -f docker-compose.prod.yml up --build -d node5
```

Each node auto-registers on startup.

---

## Persisting orchestrator data

By default, metrics (SQLite) and the node registry live inside the orchestrator container. They are lost if you remove the container.

To persist across redeploys, add a bind mount:

```yaml
orchestrator:
  volumes:
    - ./deploy/data:/app/persist
  environment:
    - SENTINEL_DATA_DIR=/app/persist
```

> Note: `SENTINEL_DATA_DIR` support requires a small env-var change in `master.py` if you need this today. For demos, the default in-container storage is fine.

**Quick backup:**

```bash
docker cp sentinel_orchestrator:/app/sentinel_metrics.db ./backup/
docker cp sentinel_orchestrator:/app/node_registry.json ./backup/
```

---

## Environment summary

| Mode | Compose file | Dashboard | API |
|------|-------------|-----------|-----|
| Development | `docker-compose.yml` | :5173 (Vite) | :8000 direct |
| Production | `docker-compose.prod.yml` | :80 (nginx) | proxied at `/api` |

---

## Troubleshooting deployment

### Dashboard loads but shows no data

- Check orchestrator is running: `docker compose -f docker-compose.prod.yml ps`
- Test API through nginx: `curl http://localhost/api/cluster-health`
- Check nginx logs: `docker compose -f docker-compose.prod.yml logs dashboard`

### Nodes stay Offline

- Workers need the orchestrator to be up first. Restart nodes:
  ```bash
  docker compose -f docker-compose.prod.yml restart node1 node2 node3 node4
  ```
- Or use **Recover all** in the dashboard chaos lab.

### Port 80 already in use

Change the dashboard port mapping:

```yaml
dashboard:
  ports:
    - "8080:80"
```

Access at `http://YOUR_SERVER_IP:8080`.

### Build fails on Windows

The C++ worker uses Linux sockets. Always build inside Docker — do not compile `monitor.cpp` natively on Windows.

### Out of memory

Reduce workers in orchestrator command from `--workers 2` to `--workers 1`, or run fewer nodes.

---

## Quick reference

```bash
# Development
docker compose up --build

# Production (detached)
docker compose -f docker-compose.prod.yml up --build -d

# Status
docker compose -f docker-compose.prod.yml ps

# Logs
docker compose -f docker-compose.prod.yml logs -f

# Stop everything
docker compose -f docker-compose.prod.yml down

# Restart one node
docker compose -f docker-compose.prod.yml restart node2
```

---

## Checklist before going live

- [ ] `docker compose -f docker-compose.prod.yml ps` — all services **Up**
- [ ] `curl http://localhost/api/cluster-health` — 4 nodes **Online**
- [ ] Browser opens dashboard at `http://YOUR_SERVER_IP/`
- [ ] Submit a job from dashboard or curl — returns **Success**
- [ ] Chaos lab + Recover works on at least one node
- [ ] (Optional) HTTPS configured with Caddy/nginx + domain

Your Sentinel cluster is fully deployed when all checklist items pass.
