import React, { useEffect, useRef, useMemo } from 'react';
import { useUIStore, type GraphPreset } from '../../store/uiStore';
import { useSimulationStore } from '../../store/simulationStore';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

// ── Preset definitions ────────────────────────────────────────────────────────

interface ChartConfig {
  title: string;
  type: 'area' | 'line' | 'bar';
  series: { key: string; name: string; color: string; fill?: string }[];
  yDomain?: [number, number];
  yFormatter?: (v: number) => string;
}

interface Preset {
  id: GraphPreset;
  label: string;
  description: string;
  charts: [ChartConfig, ChartConfig, ChartConfig];
}

const PRESETS: Preset[] = [
  {
    id: 'overview',
    label: 'Overview',
    description: 'General ward, queue and discharge throughput',
    charts: [
      {
        title: 'Ward Occupancy %',
        type: 'area',
        yDomain: [0, 100],
        yFormatter: (v) => `${v}%`,
        series: [
          { key: 'general_ward_occupancy_pct', name: 'General', color: '#22c55e', fill: '#dcfce7' },
          { key: 'icu_occupancy_pct',          name: 'ICU',     color: '#f59e0b', fill: '#fef3c7' },
        ],
      },
      {
        title: 'Queue & Critical Patients',
        type: 'line',
        series: [
          { key: 'current_queue_length',      name: 'Queue',    color: '#6366f1' },
          { key: 'critical_patients_waiting', name: 'Critical', color: '#ef4444' },
        ],
      },
      {
        title: 'Throughput (per 10 ticks)',
        type: 'bar',
        series: [
          { key: 'throughput_last_10_ticks', name: 'Discharged', color: '#22c55e', fill: '#22c55e' },
        ],
      },
    ],
  },
  {
    id: 'surge',
    label: 'Surge Watch',
    description: 'ICU pressure, critical backlog and staff load',
    charts: [
      {
        title: 'ICU Occupancy %',
        type: 'area',
        yDomain: [0, 100],
        yFormatter: (v) => `${v}%`,
        series: [
          { key: 'icu_occupancy_pct', name: 'ICU %', color: '#ef4444', fill: '#fee2e2' },
        ],
      },
      {
        title: 'Critical Patients Waiting',
        type: 'line',
        series: [
          { key: 'critical_patients_waiting', name: 'Critical waiting', color: '#ef4444' },
        ],
      },
      {
        title: 'Doctor Utilisation %',
        type: 'area',
        yDomain: [0, 100],
        yFormatter: (v) => `${v}%`,
        series: [
          { key: 'doctor_utilisation_pct', name: 'Utilisation', color: '#8b5cf6', fill: '#ede9fe' },
        ],
      },
    ],
  },
  {
    id: 'capacity',
    label: 'Capacity',
    description: 'Bed and staff capacity vs patient demand',
    charts: [
      {
        title: 'General Ward Occupancy %',
        type: 'area',
        yDomain: [0, 100],
        yFormatter: (v) => `${v}%`,
        series: [
          { key: 'general_ward_occupancy_pct', name: 'General Ward', color: '#22c55e', fill: '#dcfce7' },
        ],
      },
      {
        title: 'Doctor Utilisation %',
        type: 'line',
        yDomain: [0, 100],
        yFormatter: (v) => `${v}%`,
        series: [
          { key: 'doctor_utilisation_pct', name: 'Doctor load', color: '#8b5cf6' },
        ],
      },
      {
        title: 'Queue Depth',
        type: 'bar',
        series: [
          { key: 'current_queue_length', name: 'Waiting', color: '#6366f1', fill: '#6366f1' },
        ],
      },
    ],
  },
];

// ── Individual chart renderer ─────────────────────────────────────────────────

const ChartBlock: React.FC<{ config: ChartConfig; data: object[] }> = ({ config, data }) => {
  const tickStyle = { fontSize: 9 };
  const margin = { top: 4, right: 8, left: -16, bottom: 0 };

  const inner = (() => {
    if (config.type === 'area') {
      return (
        <AreaChart data={data} margin={margin}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="tick" tick={tickStyle} interval="preserveStartEnd" />
          <YAxis domain={config.yDomain} tick={tickStyle} tickFormatter={config.yFormatter} />
          <Tooltip contentStyle={{ fontSize: 11 }} formatter={(v: unknown) => config.yFormatter && typeof v === 'number' ? config.yFormatter(v) : String(v)} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {config.series.map(s => (
            <Area key={s.key} type="monotone" dataKey={s.key} name={s.name}
              stroke={s.color} fill={s.fill ?? s.color} strokeWidth={2} fillOpacity={0.6} />
          ))}
        </AreaChart>
      );
    }
    if (config.type === 'line') {
      return (
        <LineChart data={data} margin={margin}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="tick" tick={tickStyle} interval="preserveStartEnd" />
          <YAxis domain={config.yDomain} tick={tickStyle} tickFormatter={config.yFormatter} />
          <Tooltip contentStyle={{ fontSize: 11 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {config.series.map(s => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.name}
              stroke={s.color} strokeWidth={2} dot={false} />
          ))}
        </LineChart>
      );
    }
    return (
      <BarChart data={data} margin={margin}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
        <XAxis dataKey="tick" tick={tickStyle} interval="preserveStartEnd" />
        <YAxis tick={tickStyle} />
        <Tooltip contentStyle={{ fontSize: 11 }} />
        {config.series.map(s => (
          <Bar key={s.key} dataKey={s.key} name={s.name}
            fill={s.fill ?? s.color} radius={[2, 2, 0, 0]} />
        ))}
      </BarChart>
    );
  })();

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1 shrink-0">{config.title}</p>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          {inner}
        </ResponsiveContainer>
      </div>
    </div>
  );
};

// ── Main panel ────────────────────────────────────────────────────────────────

export const GraphOverlayPanel: React.FC = () => {
  const { graphsOpen, activePreset, closeGraph, setPreset } = useUIStore();
  const { metricsHistory } = useSimulationStore();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const data = useMemo(() => metricsHistory.slice(-60), [metricsHistory]);
  const preset = PRESETS.find(p => p.id === activePreset) ?? PRESETS[0];

  useEffect(() => {
    if (graphsOpen) closeButtonRef.current?.focus();
  }, [graphsOpen]);

  useEffect(() => {
    const handler = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && graphsOpen) closeGraph();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [graphsOpen, closeGraph]);

  if (!graphsOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={closeGraph} aria-hidden="true" />

      {/* Floating panel — right-aligned with margin */}
      <div
        role="dialog"
        aria-label="Live metric graphs"
        aria-modal="true"
        className="fixed z-50 bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col"
        style={{
          top: '72px',
          right: '24px',
          width: '400px',
          height: 'calc(100vh - 96px)',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
          <h2 className="text-sm font-semibold text-gray-800">Live Metrics</h2>
          <button
            ref={closeButtonRef}
            onClick={closeGraph}
            className="p-1.5 text-gray-400 hover:text-gray-700 rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
            aria-label="Close graph panel"
          >
            ✕
          </button>
        </div>

        {/* Preset selector */}
        <div className="px-4 py-3 border-b border-gray-100 shrink-0">
          <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide font-medium">Preset</p>
          <div className="flex gap-2">
            {PRESETS.map(p => (
              <button
                key={p.id}
                onClick={() => setPreset(p.id)}
                title={p.description}
                className={[
                  'flex-1 py-1.5 px-2 rounded-lg text-xs font-medium transition-colors border focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400',
                  activePreset === p.id
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300 hover:text-blue-600',
                ].join(' ')}
              >
                {p.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-1.5">{preset.description}</p>
        </div>

        {/* Three charts stacked */}
        <div className="flex-1 flex flex-col gap-4 p-4 overflow-hidden min-h-0">
          {preset.charts.map((cfg, i) => (
            <ChartBlock key={`${preset.id}-${i}`} config={cfg} data={data} />
          ))}
        </div>
      </div>
    </>
  );
};
