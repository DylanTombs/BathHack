import React from 'react';
import { HospitalMap } from '../map/HospitalMap';
import { ControlPanel } from '../controls/ControlPanel';
import { MetricsBanner } from './MetricsBanner';
import { EntityDetailPanel } from './EntityDetailPanel';
import { GraphOverlayPanel } from '../graphs/GraphOverlayPanel';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';
import { AISummary } from './AISummary';
import { useWebSocket } from '../../hooks/useWebSocket';

// Separate component so only it re-renders on every-frame position updates
const EntityDetailAnchor: React.FC<{ requestExplanation: (t: 'patient' | 'doctor', id: number) => void }> = ({ requestExplanation }) => {
  const x = useUIStore(s => s.entityScreenX);
  const y = useUIStore(s => s.entityScreenY);
  const left = x !== null ? Math.min(x + 20, window.innerWidth - 320) : window.innerWidth / 2 - 140;
  const top  = y !== null ? Math.max(y - 120, 80) : 200;
  return (
    <div className="fixed z-50" style={{ left, top }}>
      <EntityDetailPanel requestExplanation={requestExplanation} />
    </div>
  );
};

export const Layout: React.FC = () => {
  const { connected, tick } = useSimulationStore();
  const { isPanelOpen, leftPanelVisible, toggleLeftPanel } = useUIStore();
  const { requestExplanation } = useWebSocket();

  return (
    <div className="h-full bg-gray-100 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="relative bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">Agent-Based · LLM-Driven</span>
        </div>
        <h1 className="text-lg font-bold text-gray-900 absolute left-1/2 -translate-x-1/2">Hospital Simulation</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400 font-mono">Tick: {tick}</span>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
            <span className="text-xs text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
          </div>
        </div>
      </header>

      {/* Metrics banner */}
      <MetricsBanner />

      {/* Main layout: map fills space, fixed panels float over */}
      <div className="map-container flex-1" style={{ minHeight: 0 }}>
        <HospitalMap />
      </div>

      {/* Left panel — fixed bubble */}
      {leftPanelVisible && (
        <div
          className="fixed z-40 bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col"
          style={{ top: '195px', bottom: '24px', left: '24px', width: '400px' }}
        >
          <div className="p-4 space-y-3 overflow-y-auto scrollbar-hidden flex flex-col h-full">
            <ControlPanel />
            <div className="flex-1 flex flex-col justify-end">
              <AISummary />
            </div>
          </div>
        </div>
      )}

      {/* Left panel toggle button */}
      <button
        onClick={toggleLeftPanel}
        className="fixed z-50 bg-white border border-gray-200 shadow-md rounded-full w-11 h-11 flex items-center justify-center text-xl font-bold text-gray-500 hover:text-gray-800 hover:shadow-lg transition-all"
        style={{ top: '195px', left: leftPanelVisible ? '432px' : '24px' }}
        title={leftPanelVisible ? 'Hide controls' : 'Show controls'}
      >
        {leftPanelVisible ? '‹' : '›'}
      </button>

      {/* Entity detail — follows the selected entity on screen */}
      {isPanelOpen && <EntityDetailAnchor requestExplanation={requestExplanation} />}

      {/* Always-visible graph/events panel */}
      <GraphOverlayPanel />
    </div>
  );
};
