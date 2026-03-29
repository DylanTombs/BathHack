import React, { useState, useCallback, useEffect } from 'react';
import { useWebSocket } from '../../hooks/useWebSocket';
import { useSimulationStore } from '../../store/simulationStore';
import { ReportModal } from '../report/ReportModal';

const SPECIALTIES = ['General', 'ICU', 'Triage'];

export const ControlPanel: React.FC = () => {
  const {
    isRunning,
    scenario,
    connected,
    doctors,
    wards,
    arrivalRate: storeArrivalRate,
    severityLevel: storeSeverityLevel,
    surgeTicks,
    shortageTicks,
    reportState,
    report,
    clearReport,
  } = useSimulationStore();
  const { startSim, pauseSim, resetSim, triggerSurge, triggerShortage, triggerRecovery, updateConfig, addDoctor, removeDoctor, addBed, removeBed, generateReport } = useWebSocket();
  const [arrivalRate, setArrivalRate] = useState(1.5);
  const [severityLevel, setSeverityLevel] = useState(2);
  // Sync sliders from backend state
  useEffect(() => { setArrivalRate(storeArrivalRate); }, [storeArrivalRate]);
  useEffect(() => { setSeverityLevel(storeSeverityLevel); }, [storeSeverityLevel]);

  const [selectedSpecialty, setSelectedSpecialty] = useState('General');
  const [selectedWard, setSelectedWard] = useState<'general_ward' | 'icu'>('general_ward');
  const [pending, setPending] = useState(false);
  const [pendingScenario, setPendingScenario] = useState<string | null>(null);

  // Clear queued indicator once backend confirms the scenario has changed
  useEffect(() => {
    if (pendingScenario && scenario === pendingScenario) {
      setPendingScenario(null);
    }
  }, [scenario, pendingScenario]);

  const handleStartPause = useCallback(() => {
    if (pending || !connected) return;
    setPending(true);
    if (isRunning) {
      pauseSim();
    } else {
      startSim();
    }
    setTimeout(() => setPending(false), 1500);
  }, [pending, connected, isRunning, pauseSim, startSim]);

  const handleReset = useCallback(() => {
    if (!connected) return;
    resetSim();
  }, [connected, resetSim]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 space-y-4 shadow-sm">
      {/* Simulation controls */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Simulation</h3>
        <div className="flex gap-2">
          <button
            onClick={handleStartPause}
            disabled={pending || !connected}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              pending
                ? 'bg-gray-100 text-gray-400'
                : isRunning
                ? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                : 'bg-green-100 text-green-700 hover:bg-green-200'
            }`}
          >
            {pending ? '...' : isRunning ? 'Pause' : 'Start'}
          </button>
          <button
            onClick={handleReset}
            disabled={!connected}
            className="px-3 py-2 rounded-lg text-sm font-medium bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            ↺ Reset
          </button>
        </div>
        <button
          onClick={generateReport}
          disabled={!connected || reportState === 'generating'}
          className="mt-2 w-full py-2 px-3 rounded-lg text-sm font-medium bg-indigo-100 text-indigo-700 hover:bg-indigo-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {reportState === 'generating' ? 'Generating Report…' : 'End & Generate Report'}
        </button>
      </div>

      {reportState === 'ready' && report && (
        <ReportModal report={report} onClose={clearReport} />
      )}

      {/* Scenario buttons */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Scenarios</h3>
        <div className="grid grid-cols-3 gap-2">
          <button
            onClick={() => { triggerSurge(); setPendingScenario('surge'); }}
            className={`py-2 px-2 rounded-lg text-xs font-medium transition-colors ${
              pendingScenario === 'surge'
                ? 'bg-red-200 text-red-800 animate-pulse'
                : 'bg-red-100 text-red-700 hover:bg-red-200'
            }`}
          >
            {pendingScenario === 'surge' ? 'Queued…' : surgeTicks > 0 ? `${surgeTicks * 15} min` : 'Surge'}
          </button>
          <button
            onClick={() => { triggerShortage(); setPendingScenario('shortage'); }}
            className={`py-2 px-2 rounded-lg text-xs font-medium transition-colors ${
              pendingScenario === 'shortage'
                ? 'bg-orange-200 text-orange-800 animate-pulse'
                : 'bg-orange-100 text-orange-700 hover:bg-orange-200'
            }`}
          >
            {pendingScenario === 'shortage' ? 'Queued…' : shortageTicks > 0 ? `${shortageTicks * 15} min` : 'Shortage'}
          </button>
          <button
            onClick={() => { triggerRecovery(); setPendingScenario('normal'); }}
            className={`py-2 px-2 rounded-lg text-xs font-medium transition-colors ${
              pendingScenario === 'normal'
                ? 'bg-blue-200 text-blue-800 animate-pulse'
                : 'bg-blue-100 text-blue-700 hover:bg-blue-200'
            }`}
          >
            {pendingScenario === 'normal' ? 'Queued…' : 'Normal'}
          </button>
        </div>
        {scenario !== 'normal' && (
          <div className={`mt-2 text-xs text-center font-medium py-1 rounded ${
            scenario === 'surge' ? 'text-red-600 bg-red-50' : 'text-orange-600 bg-orange-50'
          }`}>
            {scenario === 'surge' ? 'Mass Casualty Event Active' : 'Staff Shortage Active'}
          </div>
        )}
      </div>

      {/* Configuration */}
      <div>
        <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Configuration</h3>
        <div className="space-y-3">
          {/* Arrival rate slider */}
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

          {/* Casualty rate slider */}
          <label className="block">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Casualty Rate</span>
              <span className="font-mono font-semibold" style={{
                color: ['', '#22c55e', '#f59e0b', '#f97316', '#ef4444'][severityLevel]
              }}>
                {['', 'Mild', 'Moderate', 'Serious', 'Critical'][severityLevel]}
              </span>
            </div>
            <input
              type="range" min={1} max={4} step={1}
              value={severityLevel}
              onChange={e => {
                const v = parseInt(e.target.value);
                setSeverityLevel(v);
                updateConfig({ severity_level: v });
              }}
              className="w-full accent-rose-500"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-0.5">
              <span>Mild</span><span>Moderate</span><span>Serious</span><span>Critical</span>
            </div>
          </label>

          {/* Doctors +/- with specialty dropdown */}
          <div>
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Doctors</span>
              <span className="font-mono">{doctors.length} on duty</span>
            </div>
            <div className="flex gap-2 items-center">
              <select
                value={selectedSpecialty}
                onChange={e => setSelectedSpecialty(e.target.value)}
                className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-purple-400"
              >
                {SPECIALTIES.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <button
                onClick={() => addDoctor(selectedSpecialty)}
                disabled={!connected}
                className="px-3 py-1.5 rounded-lg text-sm font-bold bg-purple-100 text-purple-700 hover:bg-purple-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={`Add ${selectedSpecialty} doctor`}
              >
                +
              </button>
              <button
                onClick={removeDoctor}
                disabled={!connected || doctors.length <= 1}
                className="px-3 py-1.5 rounded-lg text-sm font-bold bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="Remove last doctor"
              >
                −
              </button>
            </div>
          </div>

          {/* Beds + with ward dropdown */}
          <div>
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Beds</span>
              <span className="font-mono">
                GW {wards['general_ward']?.capacity ?? '--'} / ICU {wards['icu']?.capacity ?? '--'}
              </span>
            </div>
            <div className="flex gap-2 items-center">
              <select
                value={selectedWard}
                onChange={e => setSelectedWard(e.target.value as 'general_ward' | 'icu')}
                className="flex-1 text-xs border border-gray-200 rounded-lg px-2 py-1.5 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
              >
                <option value="general_ward">General Ward</option>
                <option value="icu">ICU</option>
              </select>
              <button
                onClick={() => addBed(selectedWard)}
                disabled={!connected}
                className="px-3 py-1.5 rounded-lg text-sm font-bold bg-blue-100 text-blue-700 hover:bg-blue-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={`Add bed to ${selectedWard === 'general_ward' ? 'General Ward' : 'ICU'}`}
              >
                +
              </button>
              <button
                onClick={() => removeBed(selectedWard)}
                disabled={!connected || (selectedWard === 'general_ward' ? (wards['general_ward']?.capacity ?? 1) <= 1 : (wards['icu']?.capacity ?? 1) <= 1)}
                className="px-3 py-1.5 rounded-lg text-sm font-bold bg-gray-100 text-gray-600 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={`Remove bed from ${selectedWard === 'general_ward' ? 'General Ward' : 'ICU'}`}
              >
                −
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
