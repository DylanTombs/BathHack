import React, { useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useSimulationStore } from '../../store/simulationStore';

interface Props {
  bare?: boolean;
}

export const QueueChart: React.FC<Props> = ({ bare = false }) => {
  const { metricsHistory } = useSimulationStore();
  const data = useMemo(() => metricsHistory.slice(-60), [metricsHistory]);

  const chart = (
    <>
      <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 shrink-0">Queue & Critical</h3>
      <ResponsiveContainer width="100%" height={bare ? '100%' : 120}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis tick={{ fontSize: 9 }} />
          <Tooltip contentStyle={{ fontSize: 11 }} />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Line type="monotone" dataKey="current_queue_length" name="Queue" stroke="#6366f1" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="critical_patients_waiting" name="Critical" stroke="#ef4444" strokeWidth={2} dot={false} />
        </LineChart>
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
