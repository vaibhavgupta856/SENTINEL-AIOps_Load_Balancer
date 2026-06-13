import React from 'react';
import {
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
  Legend,
} from 'recharts';

export type ChartView =
  | 'cpu'
  | 'ram'
  | 'temp'
  | 'cpu_ram'
  | 'cpu_temp'
  | 'ram_temp'
  | 'all';

export const CHART_VIEW_OPTIONS: { id: ChartView; label: string }[] = [
  { id: 'cpu', label: 'CPU' },
  { id: 'ram', label: 'RAM' },
  { id: 'temp', label: 'Temp' },
  { id: 'cpu_ram', label: 'CPU + RAM' },
  { id: 'cpu_temp', label: 'CPU + Temp' },
  { id: 'ram_temp', label: 'RAM + Temp' },
  { id: 'all', label: 'All three' },
];

type MetricDef = {
  dataKey: string;
  label: string;
  color: string;
  unit: string;
  axis: 'left' | 'right';
  domain: [number, number];
};

const METRICS: Record<'cpu' | 'ram' | 'temp', MetricDef> = {
  cpu: {
    dataKey: 'cpu',
    label: 'CPU',
    color: '#22d3ee',
    unit: '%',
    axis: 'left',
    domain: [0, 100],
  },
  ram: {
    dataKey: 'ram',
    label: 'RAM',
    color: '#a78bfa',
    unit: '%',
    axis: 'left',
    domain: [0, 100],
  },
  temp: {
    dataKey: 'temperature_c',
    label: 'Temp',
    color: '#fbbf24',
    unit: 'C',
    axis: 'right',
    domain: [20, 100],
  },
};

const VIEW_METRICS: Record<ChartView, Array<'cpu' | 'ram' | 'temp'>> = {
  cpu: ['cpu'],
  ram: ['ram'],
  temp: ['temp'],
  cpu_ram: ['cpu', 'ram'],
  cpu_temp: ['cpu', 'temp'],
  ram_temp: ['ram', 'temp'],
  all: ['cpu', 'ram', 'temp'],
};

function activeMetrics(view: ChartView): MetricDef[] {
  return VIEW_METRICS[view].map((key) => METRICS[key]);
}

function usesDualAxis(view: ChartView): boolean {
  const axes = new Set(VIEW_METRICS[view].map((k) => METRICS[k].axis));
  return axes.size > 1;
}

type NodeMetricsChartProps = {
  nodeId: string;
  data: any[];
  view: ChartView;
};

export function ChartViewSelector({
  value,
  onChange,
}: {
  value: ChartView;
  onChange: (view: ChartView) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {CHART_VIEW_OPTIONS.map((option) => {
        const active = value === option.id;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            className={active ? 'cyber-pill-active' : 'cyber-pill-idle'}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export default function NodeMetricsChart({ nodeId, data, view }: NodeMetricsChartProps) {
  const metrics = activeMetrics(view);
  const dualAxis = usesDualAxis(view);
  const showLegend = metrics.length > 1;

  const chartData = data.map((point) => ({
    ...point,
    temperature_c: point.temperature_c ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData} margin={{ top: showLegend ? 8 : 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          {metrics.map((metric) => (
            <linearGradient
              key={`grad-${nodeId}-${metric.dataKey}`}
              id={`grad-${nodeId}-${metric.dataKey}`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" stopColor={metric.color} stopOpacity={0.4} />
              <stop offset="100%" stopColor={metric.color} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>

        <XAxis dataKey="time" hide />

        {dualAxis ? (
          <>
            <YAxis yAxisId="left" domain={[0, 100]} hide />
            <YAxis yAxisId="right" domain={[20, 100]} orientation="right" hide />
          </>
        ) : (
          <YAxis domain={metrics[0].domain} hide />
        )}

        <Tooltip
          contentStyle={{
            backgroundColor: 'rgba(2, 3, 8, 0.95)',
            border: '1px solid rgba(34, 211, 238, 0.25)',
            borderRadius: '6px',
            fontSize: '10px',
            fontFamily: 'JetBrains Mono',
            boxShadow: '0 0 20px -4px rgba(34, 211, 238, 0.3)',
          }}
          formatter={(value: number, name: string) => {
            const metric = metrics.find((m) => m.dataKey === name || m.label === name);
            if (!metric) return [value, name];
            return [`${Number(value).toFixed(1)}${metric.unit}`, metric.label];
          }}
          labelFormatter={(label) => String(label).split(' ').slice(-1)[0] || label}
        />

        {showLegend && (
          <Legend
            verticalAlign="top"
            height={20}
            iconType="circle"
            iconSize={6}
            wrapperStyle={{ fontSize: '9px', fontFamily: 'JetBrains Mono', color: '#94a3b8' }}
            formatter={(value) => {
              const metric = metrics.find((m) => m.dataKey === value);
              return metric?.label ?? value;
            }}
          />
        )}

        {metrics.map((metric) => (
          <Area
            key={metric.dataKey}
            type="monotone"
            dataKey={metric.dataKey}
            name={metric.dataKey}
            stroke={metric.color}
            strokeWidth={2}
            fill={`url(#grad-${nodeId}-${metric.dataKey})`}
            dot={false}
            yAxisId={dualAxis ? metric.axis : undefined}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
