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

export const Layout: React.FC = () => {
  const { connected, tick } = useSimulationStore();
  const { isPanelOpen, leftPanelVisible, toggleLeftPanel } = useUIStore();
  const { requestExplanation } = useWebSocket();

  return (
    <div className="h-screen bg-gray-100 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-xl">🏥</span>
          <h1 className="text-lg font-bold text-gray-900">Hospital Simulation</h1>
          <span className="text-xs text-gray-400">Agent-Based · LLM-Driven</span>
        </div>
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
      <div className="flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        <HospitalMap />
      </div>

      {/* Left panel — fixed bubble */}
      {leftPanelVisible && (
        <div
          className="fixed z-40 bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col"
          style={{ top: '140px', bottom: '24px', left: '24px', width: '400px' }}
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
        style={{ top: '140px', left: leftPanelVisible ? '432px' : '24px' }}
        title={leftPanelVisible ? 'Hide controls' : 'Show controls'}
      >
        {leftPanelVisible ? '‹' : '›'}
      </button>

      {/* Entity detail — fixed overlay, left of the graph panel */}
      {isPanelOpen && (
        <div className="fixed z-50" style={{ bottom: '24px', right: '448px' }}>
          <EntityDetailPanel requestExplanation={requestExplanation} />
        </div>
      )}

      {/* Always-visible graph/events panel */}
      <GraphOverlayPanel />
    </div>
  );
};
