import React from 'react';
import { useUIStore } from '../../store/uiStore';
import { useSimulationStore } from '../../store/simulationStore';
import { useWebSocket } from '../../hooks/useWebSocket';

const SEVERITY_COLOR: Record<string, string> = {
  low: 'bg-green-100 text-green-800',
  medium: 'bg-amber-100 text-amber-800',
  critical: 'bg-red-100 text-red-800',
};

const WORKLOAD_COLOR: Record<string, string> = {
  light: 'bg-blue-100 text-blue-800',
  moderate: 'bg-purple-100 text-purple-800',
  heavy: 'bg-orange-100 text-orange-800',
  overwhelmed: 'bg-red-100 text-red-800',
};

const CONDITION_COLOR: Record<string, string> = {
  stable: 'text-gray-600',
  improving: 'text-green-600',
  worsening: 'text-red-600',
};

export const EntityDetailPanel: React.FC = () => {
  const { selectedEntityId, selectedEntityType, explanationText, explanationLoading, clearSelection } = useUIStore();
  const { patients, doctors } = useSimulationStore();
  const { requestExplanation } = useWebSocket();

  if (!selectedEntityId || !selectedEntityType) return null;

  const patient = selectedEntityType === 'patient'
    ? patients.find(p => p.id === selectedEntityId)
    : null;
  const doctor = selectedEntityType === 'doctor'
    ? doctors.find(d => d.id === selectedEntityId)
    : null;

  if (!patient && !doctor) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase">
          {selectedEntityType === 'patient' ? 'Patient Detail' : 'Doctor Detail'}
        </h3>
        <button
          onClick={clearSelection}
          className="text-gray-400 hover:text-gray-600 text-sm font-bold"
        >
          ✕
        </button>
      </div>
      <div className="p-4 space-y-3">
        {patient && (
          <>
            <div>
              <div className="font-semibold text-gray-900">{patient.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">{patient.diagnosis} · Age {patient.age}</div>
            </div>
            <div className="flex gap-2 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEVERITY_COLOR[patient.severity]}`}>
                {patient.severity}
              </span>
              <span className={`text-xs font-medium ${CONDITION_COLOR[patient.condition]}`}>
                ● {patient.condition}
              </span>
            </div>
            <div className="text-xs space-y-1 text-gray-600">
              <div>Location: <span className="font-medium text-gray-800">{patient.location.replace('_', ' ')}</span></div>
              <div>Arrived tick: <span className="font-mono">{patient.arrived_at_tick}</span></div>
              <div>Wait time: <span className="font-mono">{patient.wait_time_ticks} ticks</span></div>
              {patient.assigned_doctor_id && (
                <div>Assigned Dr: <span className="font-mono">#{patient.assigned_doctor_id}</span></div>
              )}
            </div>
            {patient.last_event_explanation && (
              <div className="text-xs bg-blue-50 border border-blue-100 rounded p-2 text-blue-700">
                <div className="font-semibold mb-1">Last event:</div>
                {patient.last_event_explanation}
              </div>
            )}
          </>
        )}

        {doctor && (
          <>
            <div>
              <div className="font-semibold text-gray-900">{doctor.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">{doctor.specialty} Specialist</div>
            </div>
            <div className="flex gap-2 flex-wrap">
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${WORKLOAD_COLOR[doctor.workload]}`}>
                {doctor.workload}
              </span>
              {doctor.is_available && (
                <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-green-100 text-green-800">Available</span>
              )}
            </div>
            <div className="text-xs space-y-1 text-gray-600">
              <div>Patients: <span className="font-mono">{doctor.assigned_patient_ids.length}/{doctor.capacity}</span></div>
              <div>Decisions made: <span className="font-mono">{doctor.decisions_made}</span></div>
            </div>
            {doctor.assigned_patient_ids.length > 0 && (
              <div className="text-xs text-gray-500">
                Treating: {doctor.assigned_patient_ids.map(id => `#${id}`).join(', ')}
              </div>
            )}
            {doctor.last_decision_reason && (
              <div className="bg-violet-50 border border-violet-200 rounded-lg p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-violet-700">🧠 Last Triage Decision</span>
                  {doctor.last_decision_confidence != null && (
                    <span className="text-xs font-mono text-violet-500">
                      {(doctor.last_decision_confidence * 100).toFixed(0)}% confidence
                    </span>
                  )}
                </div>
                {doctor.last_decision_patient_id != null && (
                  <div className="text-xs font-medium text-violet-600">
                    → Patient #{doctor.last_decision_patient_id}
                  </div>
                )}
                <div className="text-xs text-violet-900 leading-relaxed">
                  {doctor.last_decision_reason}
                </div>
              </div>
            )}
          </>
        )}

        {/* Explain button */}
        <button
          onClick={() => requestExplanation(selectedEntityType, selectedEntityId)}
          disabled={explanationLoading}
          className="w-full py-2 rounded-lg text-xs font-medium bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {explanationLoading ? '⏳ Loading…' : explanationText ? '🔄 Update AI Summary' : '🤖 Get AI Summary'}
        </button>

        {/* Explanation text */}
        {explanationText && (
          <div className="text-xs bg-indigo-50 border border-indigo-100 rounded p-3 text-indigo-800 leading-relaxed">
            <div className="font-semibold mb-1">AI Explanation:</div>
            {explanationText}
          </div>
        )}
      </div>
    </div>
  );
};
