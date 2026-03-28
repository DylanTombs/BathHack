import React, { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useSimulationStore } from '../../store/simulationStore';

interface Props {
  bare?: boolean;
}

export const ThroughputChart: React.FC<Props> = ({ bare = false }) => {
  const { metricsHistory } = useSimulationStore();
  const data = useMemo(() => metricsHistory.slice(-60), [metricsHistory]);

  const chart = (
    <>
      <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 shrink-0">Throughput (per 10 ticks)</h3>
      <ResponsiveContainer width="100%" height={bare ? '100%' : 100}>
        <BarChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9 }} />
          <Tooltip contentStyle={{ fontSize: 11 }} />
          <Bar dataKey="throughput_last_10_ticks" name="Discharged" fill="#22c55e" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </>
  );

  if (bare) return <>{chart}</>;

  return (
    <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-100">
      {chart}
    </div>
  );
};
