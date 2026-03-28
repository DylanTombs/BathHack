import React, { useRef, useEffect, useMemo } from 'react';
import { useUIStore, type GraphPreset, type RightPanelTab } from '../../store/uiStore';
import { useSimulationStore } from '../../store/simulationStore';
import { EventItem } from '../event-log/EventItem';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';

// ── Preset definitions ────────────────────────────────────────────────────────

interface SeriesConfig {
  key: string;
  name: string;
  color: string;
  fill?: string;
}

interface ChartConfig {
  title: string;
  type: 'area' | 'line' | 'bar';
  series: SeriesConfig[];
  yDomain?: [number, number];
  yFormatter?: (v: number) => string;
}

interface Preset {
  id: GraphPreset;
  label: string;
  description: string;
  charts: [ChartConfig, ChartConfig, ChartConfig];
}

const pct = (v: number) => `${v}%`;

const PRESETS: Preset[] = [
  {
    id: 'overview',
    label: 'Overview',
    description: 'Ward occupancy, queue pressure and discharge rate',
    charts: [
      {
        title: 'Ward Occupancy %',
        type: 'area',
        yDomain: [0, 100],
        yFormatter: pct,
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
        yFormatter: pct,
        series: [
          { key: 'icu_occupancy_pct', name: 'ICU', color: '#ef4444', fill: '#fee2e2' },
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
        yFormatter: pct,
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
        yFormatter: pct,
        series: [
          { key: 'general_ward_occupancy_pct', name: 'General Ward', color: '#22c55e', fill: '#dcfce7' },
        ],
      },
      {
        title: 'Doctor Utilisation %',
        type: 'line',
        yDomain: [0, 100],
        yFormatter: pct,
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

// ── Chart block ───────────────────────────────────────────────────────────────

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

// ── Right panel ───────────────────────────────────────────────────────────────

const TABS: { id: RightPanelTab; label: string }[] = [
  { id: 'metrics', label: 'Live Metrics' },
  { id: 'events',  label: 'Event Log'    },
];

export const GraphOverlayPanel: React.FC = () => {
  const { rightPanelTab, activePreset, setRightPanelTab, setPreset } = useUIStore();
  const { metricsHistory, events } = useSimulationStore();
  const data = useMemo(() => metricsHistory.slice(-60), [metricsHistory]);
  const preset = PRESETS.find(p => p.id === activePreset) ?? PRESETS[0];
  const eventBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (rightPanelTab === 'events') {
      eventBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [events, rightPanelTab]);

  return (
    <div
      className="fixed z-40 bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col"
      style={{
        top: '140px',
        bottom: '24px',
        right: '24px',
        width: '400px',
      }}
    >
      {/* Tab bar */}
      <div className="flex border-b border-gray-200 shrink-0 rounded-t-xl overflow-hidden">
        {TABS.map(tab => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={rightPanelTab === tab.id}
            onClick={() => setRightPanelTab(tab.id)}
            className={[
              'flex-1 py-3 text-sm font-medium border-b-2 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400 focus-visible:ring-inset',
              rightPanelTab === tab.id
                ? 'border-blue-500 text-blue-700 bg-white'
                : 'border-transparent text-gray-500 bg-gray-50 hover:text-gray-700 hover:border-gray-300',
            ].join(' ')}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Live Metrics tab */}
      {rightPanelTab === 'metrics' && (
        <>
          <div className="px-3 py-2.5 border-b border-gray-100 shrink-0">
            <div className="flex gap-1.5">
              {PRESETS.map(p => (
                <button
                  key={p.id}
                  onClick={() => setPreset(p.id)}
                  title={p.description}
                  className={[
                    'flex-1 py-1.5 px-1 rounded-lg text-xs font-medium transition-colors border focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400',
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

          <div className="flex-1 flex flex-col gap-3 p-3 overflow-hidden min-h-0">
            {preset.charts.map((cfg, i) => (
              <ChartBlock key={`${preset.id}-${i}`} config={cfg} data={data} />
            ))}
          </div>
        </>
      )}

      {/* Event Log tab */}
      {rightPanelTab === 'events' && (
        <div className="flex-1 overflow-y-auto scrollbar-hidden p-2 space-y-1">
          {events.length === 0 ? (
            <p className="text-xs text-gray-400 text-center pt-8">Waiting for events…</p>
          ) : (
            events.map((event, i) => (
              <EventItem key={`${event.tick}-${event.entity_id}-${i}`} event={event} />
            ))
          )}
          <div ref={eventBottomRef} />
        </div>
      )}
    </div>
  );
};
