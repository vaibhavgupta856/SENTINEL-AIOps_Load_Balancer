import React, { useState, useEffect, useRef } from 'react';

import { motion, AnimatePresence } from 'framer-motion';

import {
  ShieldAlert,
  Server,
  Network,
  Activity,
  Cpu,
  Thermometer,
  Zap,
  Radio,
  Flame,
  RotateCcw,
} from 'lucide-react';

import ChaosPanel from './components/ChaosPanel';
import NodeMetricsChart, { ChartView, ChartViewSelector } from './components/NodeMetricsChart';



const API = 'http://127.0.0.1:8000';



type StatCardProps = {

  label: string;

  value: string | number;

  icon: React.ElementType;

  accent: 'cyan' | 'violet' | 'rose' | 'amber' | 'emerald';

  alert?: boolean;

};



const ACCENT = {

  cyan: {

    icon: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',

    value: 'text-cyan-300',

    bar: 'from-cyan-500/60 to-cyan-400/20',

    glow: 'shadow-glow',

  },

  violet: {

    icon: 'text-violet-400 bg-violet-500/10 border-violet-500/20',

    value: 'text-violet-300',

    bar: 'from-violet-500/60 to-violet-400/20',

    glow: 'shadow-glow-violet',

  },

  rose: {

    icon: 'text-rose-400 bg-rose-500/10 border-rose-500/20',

    value: 'text-rose-300',

    bar: 'from-rose-500/60 to-rose-400/20',

    glow: 'shadow-glow-rose',

  },

  amber: {

    icon: 'text-amber-400 bg-amber-500/10 border-amber-500/20',

    value: 'text-amber-300',

    bar: 'from-amber-500/60 to-amber-400/20',

    glow: 'shadow-glow-amber',

  },

  emerald: {

    icon: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20',

    value: 'text-emerald-300',

    bar: 'from-emerald-500/60 to-emerald-400/20',

    glow: '',

  },

};



function StatCard({ label, value, icon: Icon, accent, alert }: StatCardProps) {
  const style = ACCENT[accent];
  return (
    <div className={`stat-card group ${alert ? style.glow : ''}`}>
      <div className={`absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r ${style.bar} opacity-70 group-hover:opacity-100 transition-opacity`} />
      <div className="flex items-start justify-between relative z-10">
        <div>
          <p className="text-[9px] font-orbitron uppercase tracking-[0.25em] text-slate-500 mb-2">{label}</p>
          <p className={`text-3xl font-bold font-mono tracking-tight stat-value ${style.value}`}>{value}</p>
        </div>
        <div className={`p-2.5 rounded-lg border ${style.icon} group-hover:scale-110 transition-transform duration-300`}>
          <Icon size={18} />
        </div>
      </div>
    </div>
  );
}

function HudCorners() {
  return (
    <>
      <span className="corner corner-tl" />
      <span className="corner corner-tr" />
      <span className="corner corner-bl" />
      <span className="corner corner-br" />
    </>
  );
}

function MeshBackground() {
  return (
    <>
      <div className="mesh-bg">
        <div className="mesh-orb w-[600px] h-[600px] bg-cyan-400/25 -top-40 -left-40 animate-float" />
        <div className="mesh-orb w-[450px] h-[450px] bg-violet-500/30 top-1/4 -right-32 animate-float" style={{ animationDelay: '-4s' }} />
        <div className="mesh-orb w-[380px] h-[380px] bg-fuchsia-500/15 bottom-10 left-1/4 animate-float" style={{ animationDelay: '-7s' }} />
      </div>
      <div className="perspective-grid" />
      <div className="grid-overlay" />
      <div className="scanlines" />
      <div className="noise-overlay" />
    </>
  );
}



export default function App() {

  const [data, setData] = useState<any>({ nodes: [], cluster_stats: {}, log: "" });

  const [history, setHistory] = useState<any>({});

  const [routingLog, setRoutingLog] = useState<any[]>([]);

  const [healingLog, setHealingLog] = useState<any[]>([]);

  const [inferenceLog, setInferenceLog] = useState<any[]>([]);

  const [timeFilter, setTimeFilter] = useState(0);

  const [statusNote, setStatusNote] = useState("Waiting for first telemetry poll...");

  const [trafficRunning, setTrafficRunning] = useState(false);
  const [chartView, setChartView] = useState<ChartView>('all');
  const [recoveringNode, setRecoveringNode] = useState<string | null>(null);
  const [recoveryErrors, setRecoveryErrors] = useState<Record<string, string>>({});

  const trafficRef = useRef<ReturnType<typeof setInterval> | null>(null);



  const fetchTelemetry = async () => {

    try {

      const res = await fetch(`${API}/api/cluster-health`);

      const json = await res.json();

      setData(json);



      const newHistory: any = {};

      for (const node of json.nodes) {

        if (node.status === 'Online') {

          try {

            const url = timeFilter === 0

              ? `${API}/api/history/${node.node_id}?seconds=10`

              : `${API}/api/history/${node.node_id}?days=${timeFilter}`;

            const histRes = await fetch(url);

            newHistory[node.node_id] = await histRes.json();

          } catch {

            console.error(`Failed to fetch history for ${node.node_id}`);

          }

        }

      }

      setHistory(newHistory);



      const [routingRes, healingRes, inferenceRes] = await Promise.all([

        fetch(`${API}/api/routing-log?limit=20`),

        fetch(`${API}/api/healing-log?limit=25`),

        fetch(`${API}/api/inference-log?limit=20`),

      ]);



      setRoutingLog(await routingRes.json());

      setHealingLog(await healingRes.json());

      setInferenceLog(await inferenceRes.json());

    } catch {

      console.error("Backend unreachable");

    }

  };



  useEffect(() => {

    fetchTelemetry();

    const interval = setInterval(fetchTelemetry, 3000);

    return () => clearInterval(interval);

  }, [timeFilter]);

  useEffect(() => {
    const onlineIds = new Set(
      (data.nodes || [])
        .filter((n: any) => n.status === 'Online')
        .map((n: any) => n.node_id)
    );

    if (onlineIds.size === 0) return;

    setRecoveryErrors((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const nodeId of onlineIds) {
        if (next[nodeId]) {
          delete next[nodeId];
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [data.nodes]);

  useEffect(() => {

    if (trafficRef.current) {

      clearInterval(trafficRef.current);

      trafficRef.current = null;

    }



    if (!trafficRunning) return;



    const sendJob = async () => {

      try {

        const jobId = `infer_${Date.now()}`;

        const res = await fetch(`${API}/api/submit-job`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({ job_id: jobId, task_type: 'inference' }),

        });

        const json = await res.json();

        const stamp = new Date().toLocaleTimeString();

        setStatusNote(`[${stamp}] ${json.message}`);

      } catch {

        setStatusNote('Traffic generator lost connection to orchestrator.');

      }

    };



    sendJob();

    trafficRef.current = setInterval(sendJob, 2000);

    return () => {

      if (trafficRef.current) clearInterval(trafficRef.current);

    };

  }, [trafficRunning]);



  const submitJob = async () => {
    try {
      const jobId = `job_${Date.now()}`;
      const res = await fetch(`${API}/api/submit-job`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: jobId, task_type: 'inference' }),
      });
      const json = await res.json();
      setStatusNote(`[${new Date().toLocaleTimeString()}] ${json.message}`);
    } catch {
      setStatusNote('Router unreachable.');
    }
  };

  const recoverNode = async (nodeId: string) => {
    setRecoveringNode(nodeId);
    try {
      const res = await fetch(`${API}/api/nodes/${nodeId}/recover`, { method: 'POST' });
      const json = await res.json();
      const stamp = new Date().toLocaleTimeString();

      if (json.ok || json.status === 'recovered') {
        setRecoveryErrors((prev) => {
          const next = { ...prev };
          delete next[nodeId];
          return next;
        });
        setStatusNote(`[${stamp}] ${json.message}`);
      } else {
        const failMsg = json.message || `${nodeId} could not be recovered. No details from orchestrator.`;
        setRecoveryErrors((prev) => ({ ...prev, [nodeId]: failMsg }));
        setStatusNote(`[${stamp}] ${failMsg}`);
      }
      await fetchTelemetry();
    } catch {
      const failMsg = `Could not reach the orchestrator to recover ${nodeId}. Is it running on port 8000?`;
      setRecoveryErrors((prev) => ({ ...prev, [nodeId]: failMsg }));
      setStatusNote(failMsg);
    } finally {
      setRecoveringNode(null);
    }
  };



  const clusterStats = data.cluster_stats || {};

  const avgCpu = clusterStats.avg_cpu || 0;

  const onlineCount = clusterStats.online_nodes || 0;

  const totalCount = clusterStats.total_nodes || 0;

  const chaosNodes: string[] = clusterStats.chaos_nodes || [];

  const throttledNodes: string[] = clusterStats.throttled_nodes || [];

  const isAlert = data.log?.includes('ALERT');



  const chaosLabel = (node: any) => {

    const chaos = node.chaos;

    if (!chaos?.active) return null;

    const labels: Record<string, string> = {

      latency_spike: 'latency spike',

      packet_drop: 'packet loss',

      cpu_spike: 'cpu overload',

      thermal_spike: 'thermal spike',

      node_kill: 'killed',

    };

    return labels[chaos.action] || chaos.action;

  };



  return (

    <div className="min-h-screen relative text-slate-200">

      <MeshBackground />



      <div className="relative z-10 max-w-[1600px] mx-auto px-4 md:px-8 py-6 md:py-10">

        {/* Header */}

        <header className="flex flex-col xl:flex-row justify-between items-start xl:items-center mb-10 gap-6">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <div className="live-badge">
                <span className="status-dot status-dot-live bg-emerald-400 text-emerald-400" />
                <span className="text-[10px] uppercase tracking-[0.2em] text-emerald-300">Live telemetry</span>
              </div>
              <span className="text-[10px] font-mono text-slate-600 tracking-wider">POLL / 3S</span>
            </div>
            <h1 className="text-5xl md:text-6xl font-extrabold tracking-wider mb-1">
              <span className="gradient-text gradient-text-animate">SENTINEL</span>
            </h1>
            <p className="text-slate-500 text-sm mt-2 max-w-lg leading-relaxed font-light">
              Thermal-aware orchestration with cooling-off routing.
              <span className="text-cyan-500/60"> Watch the cluster reroute before nodes fail.</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <select
              value={timeFilter}
              onChange={(e) => { setTimeFilter(Number(e.target.value)); setHistory({}); }}
              className="cyber-select"
            >
              <option className="bg-[#0a0c14]" value={0}>Live window</option>
              <option className="bg-[#0a0c14]" value={1}>24 hours</option>
              <option className="bg-[#0a0c14]" value={2}>2 days</option>
              <option className="bg-[#0a0c14]" value={5}>5 days</option>
            </select>
            <button onClick={submitJob} className="btn-primary">
              Route one job
            </button>
          </div>
        </header>

        <div className={`alert-strip mb-8 ${isAlert ? 'alert-strip-danger' : 'alert-strip-normal'}`}>
          <Radio size={14} className={isAlert ? 'text-rose-400' : 'text-cyan-400'} />
          <p className={`text-sm font-mono tracking-wide ${isAlert ? 'text-rose-200' : 'text-slate-300'}`}>
            {data.log || 'Polling cluster...'}
          </p>
        </div>



        {/* Stats */}

        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">

          <StatCard label="Nodes online" value={`${onlineCount}/${totalCount}`} icon={Server} accent="cyan" />

          <StatCard label="Avg CPU" value={`${avgCpu.toFixed(1)}%`} icon={Cpu} accent="amber" alert={avgCpu > 80} />

          <StatCard label="Open circuits" value={(clusterStats.open_circuits || []).length} icon={Zap} accent="violet" />

          <StatCard label="Cooling off" value={throttledNodes.length} icon={Thermometer} accent="amber" alert={throttledNodes.length > 0} />

          <StatCard label="Under chaos" value={chaosNodes.length} icon={Flame} accent="rose" alert={chaosNodes.length > 0} />

        </div>



        {/* Chaos */}

        <div className="mb-10">

          <ChaosPanel

            nodes={data.nodes || []}

            onChaosResult={setStatusNote}

            trafficRunning={trafficRunning}

            onToggleTraffic={() => setTrafficRunning((v) => !v)}

          />

        </div>



        {/* Section label + chart metric picker */}

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-5">
          <div className="flex items-center gap-3">
            <Activity size={16} className="text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.6)]" />
            <h2 className="section-label section-bracket">Worker nodes</h2>
            <div className="hidden sm:block flex-1 h-px bg-gradient-to-r from-cyan-500/40 via-violet-500/20 to-transparent min-w-[40px]" />
          </div>
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 p-3 rounded-lg border border-white/[0.05] bg-black/30">
            <span className="text-[9px] font-orbitron uppercase tracking-[0.2em] text-slate-600 shrink-0">Chart metrics</span>
            <ChartViewSelector value={chartView} onChange={setChartView} />
          </div>
        </div>



        {/* Node grid */}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-10">

          <AnimatePresence mode="popLayout">

            {(data.nodes || []).map((node: any, index: number) => {

              const underChaos = chaosNodes.includes(node.node_id) || node.chaos?.active;

              const coolingOff = throttledNodes.includes(node.node_id) || (node.routing_weight ?? 1) < 0.8;

              const chaosText = chaosLabel(node);

              const weight = Math.round((node.routing_weight ?? 1) * 100);

              const temp = node.temperature_c ?? 0;



              const needsRecovery = node.status === 'Offline'
                || node.circuit_breaker === 'OPEN'
                || underChaos
                || coolingOff;

              const cardClass = underChaos
                ? 'node-card shadow-glow-rose border-rose-500/30'
                : coolingOff
                  ? 'node-card shadow-glow-amber border-amber-500/30'
                  : 'node-card node-card-healthy';

              return (
                <motion.div
                  key={node.node_id}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.06 }}
                  className={cardClass}
                >
                  <HudCorners />

                  <div className="flex justify-between items-start mb-5 relative z-10">

                    <div className="flex items-center gap-3">

                      <div className={`p-3 rounded-xl border ${

                        underChaos ? 'bg-rose-500/10 border-rose-500/25 text-rose-400'

                          : coolingOff ? 'bg-amber-500/10 border-amber-500/25 text-amber-400'

                          : 'bg-cyan-500/10 border-cyan-500/25 text-cyan-400'

                      }`}>

                        <Server size={20} />

                      </div>

                      <div>

                        <h3 className="font-mono font-bold text-white text-lg tracking-wide">{node.node_id}</h3>
                        <div className="flex flex-wrap gap-1.5 mt-1.5">
                          <span className={`status-chip ${
                            node.status === 'Online'
                              ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
                              : 'text-rose-300 border-rose-500/40 bg-rose-500/10'
                          }`}>
                            {node.status}
                          </span>
                          {chaosText && (
                            <span className="status-chip text-rose-300 border-rose-500/40 bg-rose-500/10">
                              {chaosText}
                            </span>
                          )}
                          {coolingOff && (
                            <span className="status-chip text-amber-300 border-amber-500/40 bg-amber-500/10">
                              cooling off
                            </span>
                          )}
                          {node.circuit_breaker === 'OPEN' && (
                            <span className="status-chip text-violet-300 border-violet-500/40 bg-violet-500/10">
                              circuit open
                            </span>
                          )}
                        </div>
                        {needsRecovery && (
                          <button
                            type="button"
                            onClick={() => recoverNode(node.node_id)}
                            disabled={recoveringNode === node.node_id}
                            className="mt-2 flex items-center gap-1.5 text-[9px] font-orbitron uppercase tracking-wider px-2.5 py-1 rounded border border-emerald-500/35 text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 hover:border-emerald-400/50 disabled:opacity-50 transition-all"
                          >
                            <RotateCcw size={10} className={recoveringNode === node.node_id ? 'animate-spin' : ''} />
                            {recoveringNode === node.node_id ? 'Recovering...' : 'Recover node'}
                          </button>
                        )}
                        {recoveryErrors[node.node_id] && (
                          <p className="mt-2 text-[10px] leading-relaxed text-rose-300/90 border border-rose-500/25 bg-rose-500/10 rounded px-2 py-1.5 max-w-xs">
                            {recoveryErrors[node.node_id]}
                          </p>
                        )}
                      </div>

                    </div>

                    <div className="text-right">
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="metric-ring">
                          <p className="text-[8px] text-slate-600 uppercase tracking-wider mb-0.5 font-orbitron">CPU</p>
                          <p className={`font-mono text-sm font-semibold ${node.cpu > 85 ? 'text-rose-400' : 'text-cyan-300'}`}>
                            {node.cpu}%
                          </p>
                        </div>
                        <div className="metric-ring">
                          <p className="text-[8px] text-slate-600 uppercase tracking-wider mb-0.5 font-orbitron">RAM</p>
                          <p className="font-mono text-sm font-semibold text-violet-300">{node.ram}%</p>
                        </div>
                        <div className="metric-ring">
                          <p className="text-[8px] text-slate-600 uppercase tracking-wider mb-0.5 font-orbitron">Temp</p>
                          <p className={`font-mono text-sm font-semibold ${temp >= 75 ? 'text-amber-300' : 'text-emerald-300'}`}>
                            {temp || '--'}C
                          </p>
                        </div>
                      </div>
                    </div>

                  </div>



                  {/* Routing weight bar */}

                  <div className="mb-4 relative z-10">

                    <div className="flex justify-between text-[10px] mb-1.5">

                      <span className="text-slate-500 uppercase tracking-wider">Routing weight</span>

                      <span className="font-mono text-cyan-300">{weight}%</span>

                    </div>

                    <div className="weight-bar">

                      <div className="weight-bar-fill" style={{ width: `${weight}%` }} />

                    </div>

                    <p className="text-[10px] text-slate-600 mt-1.5 font-mono">

                      p99 {node.inference_latency_p99_ms ?? 0}ms

                    </p>

                  </div>



                  {/* Chart */}

                  <div className={`chart-well relative z-10 ${
                    chartView === 'cpu' || chartView === 'ram' || chartView === 'temp' ? 'h-32' : 'h-40'
                  }`}>

                    {history[node.node_id]?.length > 0 ? (

                      <NodeMetricsChart
                        nodeId={node.node_id}
                        data={history[node.node_id]}
                        view={chartView}
                      />

                    ) : (

                      <div className="flex items-center justify-center h-full text-xs text-slate-600 font-mono">

                        {node.status === 'Online' ? 'Collecting telemetry...' : 'Node offline'}

                      </div>

                    )}

                  </div>

                </motion.div>

              );

            })}

          </AnimatePresence>

        </div>



        {/* Logs */}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="log-panel">
            <HudCorners />
            <div className="flex items-center gap-2 mb-4 relative z-10">
              <ShieldAlert size={15} className="text-emerald-400 drop-shadow-[0_0_6px_rgba(52,211,153,0.5)]" />
              <h2 className="section-label">Self-healing log</h2>
            </div>
            <div className="terminal-log p-4 rounded-lg h-52 overflow-y-auto scrollbar-thin space-y-2.5 relative z-10">

              {healingLog.length > 0 ? healingLog.map((entry, idx) => (

                <div key={idx} className="text-slate-300 border-l-2 border-emerald-500/40 pl-3 py-0.5">

                  <span className="text-emerald-600/80">[{new Date(entry.timestamp).toLocaleTimeString()}]</span>{' '}

                  {entry.message}

                </div>

              )) : (

                <p className="text-slate-600">No healing events yet. Start traffic and trigger chaos to watch reroutes.</p>

              )}

            </div>

          </div>



          <div className="log-panel">
            <HudCorners />
            <div className="flex items-center gap-2 mb-4 relative z-10">
              <Network size={15} className="text-violet-400 drop-shadow-[0_0_6px_rgba(167,139,250,0.5)]" />
              <h2 className="section-label">Inference delivery</h2>
            </div>
            <div className="terminal-log p-4 rounded-lg h-52 overflow-y-auto scrollbar-thin space-y-2.5 relative z-10">

              {inferenceLog.length > 0 ? inferenceLog.map((entry, idx) => (

                <div key={idx} className={`border-l-2 pl-3 py-0.5 ${

                  entry.status === 'rerouted'

                    ? 'border-amber-500/50 text-amber-100'

                    : 'border-violet-500/40 text-violet-100'

                }`}>

                  <span className="text-slate-600">[{new Date(entry.timestamp).toLocaleTimeString()}]</span>{' '}

                  <span className="text-cyan-400">{entry.job_id}</span>

                  <span className="text-slate-500"> → </span>

                  {entry.target_node}

                  <span className="text-slate-500 block mt-0.5">{entry.detail}</span>

                </div>

              )) : (

                <p className="text-slate-600">No inference jobs logged yet.</p>

              )}

            </div>

          </div>



          <div className="log-panel">
            <HudCorners />
            <div className="flex items-center gap-2 mb-4 relative z-10">
              <Activity size={15} className="text-cyan-400 drop-shadow-[0_0_6px_rgba(34,211,238,0.5)]" />
              <h2 className="section-label">Router status</h2>
            </div>
            <div className="terminal-log p-4 rounded-lg h-52 overflow-y-auto scrollbar-thin space-y-2.5 relative z-10">

              <div className={isAlert ? 'text-rose-300' : 'text-emerald-300'}>

                {data.log || 'Polling cluster...'}

              </div>

              <div className="text-slate-400 border-t border-white/[0.06] pt-2">{statusNote}</div>

              {routingLog.slice(0, 5).map((entry: any, idx: number) => (

                <div key={idx} className="text-slate-500">

                  <span className="text-cyan-500/80">{entry.target_node}</span>

                  <span className="text-slate-600"> — </span>

                  {entry.decision_reason}

                </div>

              ))}

            </div>

          </div>

        </div>



        <footer className="mt-14 text-center relative z-10">
          <div className="inline-flex items-center gap-4 px-6 py-3 rounded-full border border-white/[0.05] bg-black/30">
            <span className="h-px w-8 bg-gradient-to-r from-transparent to-cyan-500/40" />
            <p className="text-[10px] font-orbitron text-slate-600 uppercase tracking-[0.4em]">
              Sentinel AIOps v2.2
            </p>
            <span className="h-px w-8 bg-gradient-to-l from-transparent to-violet-500/40" />
          </div>
        </footer>

      </div>

    </div>

  );

}

