# SENTINEL AIOps Load Balancer

A horizontally scalable FastAPI-based AIOps orchestrator that dynamically load balances compute tasks across 1000+ C++ inference nodes with intelligent routing, circuit breaking, and real-time telemetry monitoring.

## Project Overview

SENTINEL AIOPS v2.0 is a production-grade load balancing system featuring:

### Core Features

1. **Horizontally Scalable FastAPI Orchestrator**
   - Dynamic node registration and discovery
   - Support for 1000+ inference nodes
   - Non-blocking async/await architecture
   - JSON-based node registry with persistence

2. **Active Telemetry Polling (3-second interval)**
   - Continuously polls all registered nodes every 3 seconds
   - Captures CPU, RAM, and timestamp metrics
   - Persists data to SQLite for historical analysis

3. **Least Load Routing Algorithm**
   - Intelligently routes jobs to the node with minimum CPU utilization
   - Ensures even distribution across the cluster
   - Fallback to queuing when all nodes are overloaded

4. **Automated Circuit Breaking**
   - Triggers when node CPU exceeds 85% threshold
   - Isolates overloaded nodes from receiving new tasks
   - Auto-recovery cooldown of 10 seconds
   - Prevents cascading failures and timeouts

5. **Real-time React Dashboard**
   - Live visualization of routing decisions
   - 5 days of historical time-series data
   - Per-node CPU/RAM charts with area graphs
   - Cluster statistics and health overview
   - Traffic router log showing live decisions

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  React Dashboard (Port 5173)            │
│            ├─ Live Cluster Metrics                     │
│            ├─ Node Health Visualization               │
│            ├─ 5-Day Historical Charts                 │
│            └─ Routing Decision Timeline               │
└───────────────────────────┬─────────────────────────────┘
                            │
                            │ HTTP (3s polling)
                            ↓
┌─────────────────────────────────────────────────────────┐
│      FastAPI Orchestrator (Port 8000)                   │
│  ├─ Telemetry Collector (3s interval polling)          │
│  ├─ Circuit Breaker Manager                            │
│  ├─ Least Load Router                                  │
│  ├─ SQLite Time-Series DB (5-day retention)            │
│  └─ Node Registry (JSON persistence)                   │
└─────────────────┬──────────────────────────────────────┘
                  │
          ┌───────┴────────┐
          │                │
    [Node 1-4]        [Node N-1000+]
          │                │
    ┌─────▼─────┐    ┌─────▼─────┐
    │ C++ Monitor   │    │ C++ Monitor   │
    │ (Port 8080)   │    │ (Port 8080)   │
    ├─ Hardware Metrics
    ├─ CPU/RAM Sampling
    └─ Load Simulation   └─────────────┘
          │
    ┌─────▼──────────┐
    │ Python Receiver│
    │ (Port 8081)    │
    ├─ Health Check Endpoint
    ├─ Job Submission Handler
    └─ CORS Support
```

---

## 📂 File Structure

```
sentinel-node/
├── orchestrator/
│   ├── master.py                    # FastAPI orchestrator (1000+ node capable)
│   ├── Dockerfile                   # Container for orchestrator
│   ├── requirements.txt              # Python dependencies
│   └── node_registry.json           # Persistent node registry
├── cluster/
│   ├── monitor.cpp                  # C++ hardware metrics agent (Linux)
│   ├── receiver.py                  # Python API server for nodes
│   └── Dockerfile                   # Container for inference nodes
├── dashboard/
│   ├── src/App.tsx                 # React dashboard (Tailwind + Recharts)
│   ├── package.json                 # Dependencies
│   ├── Dockerfile                   # Container for dashboard
│   ├── vite.config.ts              # Vite bundler config
│   └── tailwind.config.js           # Tailwind CSS config
├── docker-compose.yml               # Multi-container orchestration
└── README.md                        # This file
```

---

## 🔧 Installation & Setup

### Prerequisites
- Docker & Docker Compose
- Node.js 18+ (for local dashboard development)
- Python 3.11+ (for local orchestrator development)
- G++ compiler (for C++ compilation)

### Quick Start

#### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
cd sentinel-node

# Start all services
docker-compose up --build

# Access services:
# - Dashboard: http://localhost:5173
# - Orchestrator API: http://localhost:8000
# - API Docs: http://localhost:8000/docs
```

#### Option 2: Local Development

```bash
# Install orchestrator dependencies
cd orchestrator
pip install -r requirements.txt
python -m uvicorn master:app --reload

# In another terminal, start the dashboard
cd dashboard
npm install
npm run dev
```

---

## 🔌 API Endpoints

### Cluster Management

```bash
# Get cluster health (includes all nodes' metrics)
GET /api/cluster-health
Response: {
  "nodes": [...],
  "cluster_stats": {
    "total_nodes": 4,
    "online_nodes": 4,
    "avg_cpu": 35.2,
    "critical_nodes": [],
    "open_circuits": []
  },
  "log": "✅ Cluster Stable | Online: 4/4 | Avg CPU: 35.2%"
}

# Register a new node dynamically
POST /api/nodes/register
Body: { "node_id": "node_100", "url": "http://node-100:8080" }

# Unregister a node
DELETE /api/nodes/{node_id}

# Get node telemetry history (up to 5 days)
GET /api/history/{node_id}?days=5
Response: [
  { "time": "2024-01-15 10:30:45", "cpu": 42, "ram": 58 },
  ...
]

# Submit job for load balancing
POST /api/submit-job
Body: { "job_id": "job_123", "task_type": "inference" }
Response: {
  "status": "Success",
  "job_id": "job_123",
  "assigned_node": "node_1",
  "node_load": "35%",
  "message": "✅ Job routed to node_1 (35% CPU) - Least Load algorithm active"
}

# Get recent routing decisions
GET /api/routing-log?limit=50
Response: [
  {
    "timestamp": "2024-01-15T10:35:20",
    "job_id": "job_123",
    "target_node": "node_1",
    "decision_reason": "Least Load: 35% CPU"
  },
  ...
]
```

---

## 🎯 Key Achievements (Resume Points)

### ✅ Engineered a horizontally scalable FastAPI AIOps orchestrator
- **Implementation**: `orchestrator/master.py` uses async/await with httpx for non-blocking I/O
- **Scalability**: Dynamic node registry (JSON) supports 1000+ nodes
- **Performance**: Batched concurrent polling of all nodes every 3 seconds

### ✅ Dynamically load balance compute tasks across 1000+ C++ inference nodes
- **Architecture**: C++ `monitor.cpp` runs on each node, exposing HTTP endpoints
- **Discovery**: Nodes register with orchestrator via `/api/nodes/register`
- **Concurrency**: All nodes polled in parallel using `asyncio.gather()`

### ✅ Active telemetry polling every 3 seconds
- **Frequency**: `TELEMETRY_POLL_INTERVAL = 3` seconds
- **Data**: CPU%, RAM%, timestamp collected from each node
- **Persistence**: SQLite `metrics` table stores historical data

### ✅ Least Load routing algorithm
- **Algorithm**: `min(available_nodes, key=lambda nid: node_registry.nodes[nid]['metrics']['cpu'])`
- **Routing Log**: All decisions logged to `routing_log` table with reasons
- **Dashboard**: Real-time visualization of routing choices

### ✅ Automated circuit breaking at 85% CPU threshold
- **Threshold**: `CIRCUIT_BREAKER_THRESHOLD = 85`
- **State Machine**: CLOSED → OPEN → CLOSED (after 10s cooldown)
- **Effect**: Overloaded nodes isolated from receiving new tasks
- **Prevention**: Avoids cascading failures and timeout storms

### ✅ Responsive React dashboard
- **Framework**: React 18 + Tailwind CSS + Framer Motion animations
- **Charting**: Recharts for beautiful area charts
- **Real-time**: Updates every 3 seconds to match telemetry interval
- **Historical**: Displays 5 days of time-series data (user selectable)
- **Features**:
  - Cluster overview stats (online nodes, avg CPU, open circuits)
  - Per-node metrics with circuit breaker status
  - Live routing log with decision reasons
  - System health logs
  - Responsive grid layout for all screen sizes

### ✅ SQLite time-series engine
- **Tables**: `metrics` (telemetry) + `routing_log` (decisions)
- **Retention**: 5 days of historical data
- **Queries**: Efficient filtering by node_id and timestamp range
- **Persistence**: Automatic ACID compliance

---

## ⚙️ Configuration

Edit `orchestrator/master.py` to customize:

```python
CIRCUIT_BREAKER_THRESHOLD = 85      # CPU percentage threshold
CIRCUIT_BREAKER_COOLDOWN = 10       # Seconds before recovery
TELEMETRY_POLL_INTERVAL = 3         # Seconds between health checks
```

---

## 📊 Monitoring

### Real-time Dashboard
Access http://localhost:5173 to view:
- Live cluster health
- Per-node CPU/RAM graphs (5-day history)
- Routing decisions in real-time
- System alerts and warnings

### API Documentation
Access http://localhost:8000/docs for interactive Swagger UI

### Database Inspection

```bash
# Connect to SQLite database
sqlite3 orchestrator/sentinel_metrics.db

# View recent metrics
SELECT node_id, cpu, ram, timestamp FROM metrics ORDER BY id DESC LIMIT 20;

# View routing decisions
SELECT timestamp, job_id, target_node, decision_reason FROM routing_log ORDER BY id DESC LIMIT 20;

# Node registry
cat orchestrator/node_registry.json | python -m json.tool
```

---

## 🧪 Testing

### Simulate High Load
```bash
# Trigger stress test on a specific node
curl -X POST http://localhost:8000/api/inject-load

# Submit multiple jobs
for i in {1..100}; do
  curl -X POST http://localhost:8000/api/submit-job \
    -H "Content-Type: application/json" \
    -d "{\"job_id\": \"job_$i\", \"task_type\": \"inference\"}"
done
```

### Monitor Circuit Breaker
Watch the dashboard as nodes approach 85% CPU - circuits will open and prevent new task allocation.

---

## 📈 Scaling to 1000+ Nodes

### Option 1: Docker Compose Generator
```bash
# Generate docker-compose.yml with N nodes
python3 -c "
services = {}
for i in range(1, 1001):
    services[f'node{i}'] = {
        'build': './cluster',
        'environment': ['NODE_PORT=8080'],
        'networks': {'cluster_net': {'ipv4_address': f'172.18.{i//256}.{i%256}'}}
    }
# ... write to docker-compose.yml
"
```

### Option 2: Kubernetes Deployment
Scale nodes using Kubernetes StatefulSet:
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: sentinel-nodes
spec:
  replicas: 1000
  serviceName: sentinel-node
  template:
    spec:
      containers:
      - name: node
        image: sentinel-cluster:latest
        ports:
        - containerPort: 8080
```

---

## 🐛 Troubleshooting

### Nodes not appearing in cluster
```bash
# Check if nodes are running
docker ps | grep sentinel

# Manually register a node
curl -X POST http://localhost:8000/api/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"node_id": "node_manual", "url": "http://node:8080"}'
```

### High latency in telemetry
- Increase `TELEMETRY_POLL_INTERVAL` if network is slow
- Check node availability with health check endpoint
- Monitor dashboard for circuit breaker states

### SQLite database locked
```bash
# Reset database
rm orchestrator/sentinel_metrics.db
```

---

## 📝 License

Proprietary - SENTINEL AIOps Project (2024-2026)

---

## 👤 Author

Built as part of the SENTINEL AIOps project for horizontally scalable load balancing.

---

**v2.0 - Production Ready** ✅
