import React from 'react';

export interface InterventionEntry {
  tick: number;
  intervention_type: string;
  detail: Record<string, unknown>;
  metrics_at_time: {
    current_queue_length: number;
    icu_occupancy_pct: number;
    general_ward_occupancy_pct: number;
  };
}

interface Props {
  interventions: InterventionEntry[];
  totalTicks: number;
}

const IV_COLORS: Record<string, string> = {
  surge: 'bg-red-500',
  shortage: 'bg-orange-500',
  recovery: 'bg-blue-500',
  add_doctor: 'bg-green-500',
  remove_doctor: 'bg-yellow-500',
  add_bed: 'bg-teal-500',
  remove_bed: 'bg-pink-500',
  update_arrival_rate: 'bg-purple-500',
  update_severity: 'bg-indigo-500',
};

const IV_LABELS: Record<string, string> = {
  surge: 'Surge',
  shortage: 'Shortage',
  recovery: 'Recovery',
  add_doctor: '+Doctor',
  remove_doctor: '−Doctor',
  add_bed: '+Bed',
  remove_bed: '−Bed',
  update_arrival_rate: 'Rate',
  update_severity: 'Severity',
};

export const InterventionTimeline: React.FC<Props> = ({ interventions, totalTicks }) => {
  if (totalTicks === 0) return null;

  return (
    <div className="relative">
      {/* Track bar */}
      <div className="h-3 bg-gray-100 rounded-full relative overflow-hidden">
        {interventions.map((iv, i) => {
          const pct = totalTicks > 0 ? (iv.tick / totalTicks) * 100 : 0;
          const color = IV_COLORS[iv.intervention_type] ?? 'bg-gray-400';
          return (
            <div
              key={i}
              className={`absolute top-0 bottom-0 w-1 ${color} rounded-sm`}
              style={{ left: `${pct}%` }}
              title={`Tick ${iv.tick}: ${iv.intervention_type}`}
            />
          );
        })}
      </div>

      {/* Tick labels */}
      <div className="flex justify-between text-xs text-gray-400 mt-1">
        <span>0</span>
        <span>{totalTicks}</span>
      </div>

      {/* Legend chips */}
      {interventions.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {interventions.map((iv, i) => {
            const color = IV_COLORS[iv.intervention_type] ?? 'bg-gray-400';
            const label = IV_LABELS[iv.intervention_type] ?? iv.intervention_type;
            return (
              <span
                key={i}
                className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full text-white ${color}`}
                title={`Tick ${iv.tick}: queue=${iv.metrics_at_time.current_queue_length}, ICU=${iv.metrics_at_time.icu_occupancy_pct.toFixed(0)}%`}
              >
                <span className="font-mono opacity-75">t{iv.tick}</span> {label}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
};
