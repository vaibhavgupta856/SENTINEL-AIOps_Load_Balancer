import React, { useState } from 'react';
import { AlertTriangle, RotateCcw, Zap, WifiOff, Timer, Skull, Thermometer, Play, Square } from 'lucide-react';
import { API } from '../config';

type ChaosPanelProps = {
  nodes: any[];
  onChaosResult: (msg: string) => void;
  trafficRunning: boolean;
  onToggleTraffic: () => void;
};

const ACTIONS = [
  {
    id: 'latency_spike',
    label: 'Spike latency',
    hint: 'Health checks slow down. Orchestrator marks the node offline.',
    icon: Timer,
    hover: 'hover:border-violet-500/50 hover:shadow-[0_0_20px_-6px_rgba(167,139,250,0.4)]',
  },
  {
    id: 'packet_drop',
    label: 'Drop packets',
    hint: 'Most health probes fail. Simulates a flaky network link.',
    icon: WifiOff,
    hover: 'hover:border-cyan-500/50 hover:shadow-[0_0_20px_-6px_rgba(34,211,238,0.4)]',
  },
  {
    id: 'cpu_spike',
    label: 'Overload CPU',
    hint: 'Forces CPU past the circuit breaker threshold.',
    icon: Zap,
    hover: 'hover:border-amber-500/50 hover:shadow-[0_0_20px_-6px_rgba(251,191,36,0.4)]',
  },
  {
    id: 'thermal_spike',
    label: 'Spike temperature',
    hint: 'Pushes die temp past threshold. Traffic weight drops before crash.',
    icon: Thermometer,
    hover: 'hover:border-orange-500/50 hover:shadow-[0_0_20px_-6px_rgba(251,146,60,0.4)]',
  },
  {
    id: 'node_kill',
    label: 'Kill node',
    hint: 'Node stops answering entirely. Hard failure scenario.',
    icon: Skull,
    hover: 'hover:border-rose-500/50 hover:shadow-[0_0_20px_-6px_rgba(251,113,133,0.4)]',
  },
];

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

export default function ChaosPanel({ nodes, onChaosResult, trafficRunning, onToggleTraffic }: ChaosPanelProps) {
  const [selectedNode, setSelectedNode] = useState('');
  const [busy, setBusy] = useState(false);

  const target = selectedNode || nodes[0]?.node_id || '';

  const trigger = async (action: string) => {
    if (!target) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/chaos/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: target, action, duration: 45 }),
      });
      const json = await res.json();
      onChaosResult(json.message || `Chaos applied to ${target}`);
    } catch {
      onChaosResult('Could not reach orchestrator. Is it running on port 8000?');
    } finally {
      setBusy(false);
    }
  };

  const resetAll = async () => {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/chaos/reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const json = await res.json();
      if (json.failed_details?.length) {
        const summary = json.failed_details
          .map((f: { node_id: string; message: string }) => `${f.node_id}: ${f.message}`)
          .join(' | ');
        onChaosResult(`${json.message} Failures — ${summary}`);
      } else {
        onChaosResult(json.message || 'Recovery attempted on all nodes.');
      }
    } catch {
      onChaosResult('Recovery failed. Check orchestrator connection.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chaos-panel">
      <div className="chaos-accent" />
      <HudCorners />

      <div className="p-6 relative z-10">
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 shadow-[0_0_16px_-4px_rgba(251,113,133,0.4)]">
                <AlertTriangle size={16} className="text-rose-400" />
              </div>
              <h2 className="font-orbitron font-bold text-sm uppercase tracking-[0.25em] text-slate-100">
                Chaos lab
              </h2>
            </div>
            <p className="text-xs text-slate-500 max-w-xl leading-relaxed">
              Break a node on purpose, then watch Sentinel pull traffic away without dropping
              in-flight requests. Turn on steady traffic first for the clearest demo.
            </p>
          </div>

          <button
            onClick={onToggleTraffic}
            className={`flex items-center gap-2 text-[10px] font-orbitron font-semibold uppercase tracking-wider px-5 py-2.5 rounded-lg border transition-all duration-300 ${
              trafficRunning
                ? 'traffic-btn-active text-emerald-300'
                : 'bg-black/40 text-slate-400 border-white/10 hover:border-white/25 hover:text-slate-200'
            }`}
          >
            {trafficRunning ? <Square size={13} /> : <Play size={13} />}
            {trafficRunning ? 'Stop traffic' : 'Start traffic'}
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-3 mb-6 p-4 rounded-lg border border-white/[0.06] bg-black/40">
          <label className="text-[9px] font-orbitron text-slate-500 uppercase tracking-[0.2em]">Target</label>
          <select
            value={target}
            onChange={(e) => setSelectedNode(e.target.value)}
            className="flex-1 min-w-[140px] cyber-select py-2"
          >
            {nodes.map((n: any) => (
              <option key={n.node_id} value={n.node_id} className="bg-[#0a0c14]">
                {n.node_id} ({n.status})
              </option>
            ))}
          </select>
          <button
            onClick={resetAll}
            disabled={busy}
            className="flex items-center gap-2 text-[10px] font-orbitron font-semibold uppercase tracking-wider px-4 py-2 rounded-lg border border-slate-600/40 text-slate-400 hover:text-slate-200 hover:border-slate-400 disabled:opacity-40 transition-all"
          >
            <RotateCcw size={13} />
            Recover all
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
          {ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.id}
                onClick={() => trigger(action.id)}
                disabled={busy || !target}
                className={`group chaos-action-btn disabled:opacity-40 ${action.hover}`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Icon size={15} className="text-rose-400/90 group-hover:scale-110 transition-transform" />
                  <span className="text-xs font-semibold text-slate-200">{action.label}</span>
                </div>
                <p className="text-[10px] text-slate-600 leading-relaxed">{action.hint}</p>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
