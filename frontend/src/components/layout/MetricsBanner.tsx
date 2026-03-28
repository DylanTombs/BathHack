import React, { useEffect, useRef, useState } from 'react';
import { useSimulationStore } from '../../store/simulationStore';

interface MetricCardProps {
  label: string;
  value: string | number;
  highlight?: boolean;
  highlightColor?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, highlight, highlightColor = 'bg-red-100' }) => {
  const prevValue = useRef(value);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (prevValue.current !== value) {
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 600);
      prevValue.current = value;
      return () => clearTimeout(t);
    }
  }, [value]);

  return (
    <div className={`flex flex-col items-center px-4 py-2 rounded-lg transition-colors ${
      flash ? highlightColor : 'bg-white'
    } ${highlight ? 'ring-1 ring-red-300' : ''}`}>
      <span className="text-xs text-gray-500 uppercase font-medium">{label}</span>
      <span className={`text-lg font-bold ${highlight ? 'text-red-600' : 'text-gray-900'}`}>{value}</span>
    </div>
  );
};

export const MetricsBanner: React.FC = () => {
  const { metrics, tick, simDatetime } = useSimulationStore();

  return (
    <div className="bg-gray-50 border-b border-gray-200 px-4 py-2">
      <div className="flex items-center gap-2 overflow-x-auto">
        <div className="flex flex-col items-center px-4 py-2 rounded-lg bg-indigo-50 ring-1 ring-indigo-200 min-w-30">
          <span className="text-xs text-indigo-500 uppercase font-medium">Sim Time</span>
          <span className="text-lg font-bold text-indigo-700 whitespace-nowrap">{simDatetime}</span>
        </div>
        <MetricCard label="Tick" value={tick} highlightColor="bg-blue-50" />
        <MetricCard label="Arrived" value={metrics?.total_patients_arrived ?? 0} highlightColor="bg-blue-50" />
        <MetricCard label="Discharged" value={metrics?.total_patients_discharged ?? 0} highlightColor="bg-green-50" />
        <MetricCard
          label="Deceased"
          value={metrics?.total_patients_deceased ?? 0}
          highlight={(metrics?.total_patients_deceased ?? 0) > 0}
          highlightColor="bg-red-100"
        />
        <MetricCard
          label="Mortality"
          value={`${(metrics?.mortality_rate_pct ?? 0).toFixed(1)}%`}
          highlight={(metrics?.mortality_rate_pct ?? 0) > 5}
          highlightColor="bg-red-100"
        />
        <MetricCard
          label="Queue"
          value={metrics?.current_queue_length ?? 0}
          highlight={(metrics?.current_queue_length ?? 0) > 10}
          highlightColor="bg-amber-100"
        />
        <MetricCard
          label="ICU"
          value={`${(metrics?.icu_occupancy_pct ?? 0).toFixed(0)}%`}
          highlight={(metrics?.icu_occupancy_pct ?? 0) >= 90}
          highlightColor="bg-red-100"
        />
        <MetricCard
          label="Critical Waiting"
          value={metrics?.critical_patients_waiting ?? 0}
          highlight={(metrics?.critical_patients_waiting ?? 0) > 0}
          highlightColor="bg-red-100"
        />
        <MetricCard
          label="Dr Utilisation"
          value={`${(metrics?.doctor_utilisation_pct ?? 0).toFixed(0)}%`}
          highlight={(metrics?.doctor_utilisation_pct ?? 0) >= 90}
          highlightColor="bg-orange-100"
        />
      </div>
    </div>
  );
};
