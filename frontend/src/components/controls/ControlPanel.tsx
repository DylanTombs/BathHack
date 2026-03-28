import React, { useState } from 'react';
import { useWebSocket } from '../../hooks/useWebSocket';
import { useSimulationStore } from '../../store/simulationStore';

export const ControlPanel: React.FC = () => {
  const { isRunning, scenario } = useSimulationStore();
  const { startSim, pauseSim, resetSim, triggerSurge, triggerShortage, triggerRecovery, updateConfig } = useWebSocket();
  const [arrivalRate, setArrivalRate] = useState(1.5);
  const [numDoctors, setNumDoctors] = useState(4);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4 shadow-sm">
      {/* Simulation controls */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Simulation</h3>
        <div className="flex gap-2">
          <button
            onClick={isRunning ? pauseSim : startSim}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
              isRunning
                ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                : 'bg-green-100 text-green-700 hover:bg-green-200'
            }`}
          >
            {isRunning ? '⏸ Pause' : '▶ Start'}
          </button>
          <button
            onClick={resetSim}
            className="px-3 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200"
          >
            ↺ Reset
          </button>
        </div>
      </div>

      {/* Scenario buttons */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Scenarios</h3>
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={triggerSurge}
            className="py-2 px-2 rounded-lg text-xs font-medium bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
          >
            🚨 Surge
          </button>
          <button
            onClick={triggerShortage}
            className="py-2 px-2 rounded-lg text-xs font-medium bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
          >
            👨‍⚕️ Shortage
          </button>
          <button
            onClick={triggerRecovery}
            className="py-2 px-2 rounded-lg text-xs font-medium bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
          >
            ✅ Normal
          </button>
        </div>
        {scenario !== 'normal' && (
          <div className={`mt-2 text-xs text-center font-medium py-1 rounded ${
            scenario === 'surge' ? 'text-red-600 bg-red-50' : 'text-orange-600 bg-orange-50'
          }`}>
            {scenario === 'surge' ? '🚨 Mass Casualty Event Active' : '⚠️ Staff Shortage Active'}
          </div>
        )}
      </div>

      {/* Config sliders */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Configuration</h3>
        <div className="space-y-3">
          <label className="block">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Arrival Rate</span>
              <span className="font-mono">{arrivalRate.toFixed(1)}/tick</span>
            </div>
            <input
              type="range" min={0.5} max={5} step={0.5}
              value={arrivalRate}
              onChange={e => {
                const v = parseFloat(e.target.value);
                setArrivalRate(v);
                updateConfig({ arrival_rate_per_tick: v });
              }}
              className="w-full accent-blue-500"
            />
          </label>
          <label className="block">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Doctors</span>
              <span className="font-mono">{numDoctors}</span>
            </div>
            <input
              type="range" min={1} max={10} step={1}
              value={numDoctors}
              onChange={e => {
                const v = parseInt(e.target.value);
                setNumDoctors(v);
                updateConfig({ num_doctors: v });
              }}
              className="w-full accent-purple-500"
            />
          </label>
        </div>
      </div>
    </div>
  );
};
