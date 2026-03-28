import React, { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useSimulationStore } from '../../store/simulationStore';

interface Props {
  bare?: boolean;
}

export const OccupancyChart: React.FC<Props> = ({ bare = false }) => {
  const { metricsHistory } = useSimulationStore();
  const data = useMemo(() => metricsHistory.slice(-60), [metricsHistory]);

  const chart = (
    <>
      <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2 shrink-0">Ward Occupancy %</h3>
      <ResponsiveContainer width="100%" height={bare ? '100%' : 140}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis dataKey="tick" tick={{ fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis domain={[0, 100]} tick={{ fontSize: 9 }} />
          <Tooltip
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            formatter={(val: any) => typeof val === 'number' ? `${val.toFixed(0)}%` : String(val)}
            contentStyle={{ fontSize: 11 }}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Area type="monotone" dataKey="general_ward_occupancy_pct" name="General" stroke="#22c55e" fill="#dcfce7" strokeWidth={2} />
          <Area type="monotone" dataKey="icu_occupancy_pct" name="ICU" stroke="#f59e0b" fill="#fef3c7" strokeWidth={2} />
        </AreaChart>
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
