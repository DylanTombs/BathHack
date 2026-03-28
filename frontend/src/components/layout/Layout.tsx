import React from 'react';
import { HospitalMap } from '../map/HospitalMap';
import { ControlPanel } from '../controls/ControlPanel';
import { MetricsBanner } from './MetricsBanner';
import { EntityDetailPanel } from './EntityDetailPanel';
import { GraphOverlayPanel } from '../graphs/GraphOverlayPanel';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';
import { AISummary } from './AISummary';

export const Layout: React.FC = () => {
  const { connected, tick } = useSimulationStore();
  const { isPanelOpen } = useUIStore();

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
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

      {/* Main layout: left controls | map */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
          <div className="w-80 shrink-0 p-4 space-y-3 overflow-y-auto border-r border-gray-200 bg-white flex flex-col" style={{height: '100%'}}>
            <ControlPanel />
            <div className="flex-1 flex flex-col justify-end">
              <AISummary />
            </div>
          </div>
        <div className="flex-1 overflow-auto p-4">
          <HospitalMap />
        </div>
    	  </div>

      {/* Entity detail — fixed overlay, left of the graph panel */}
      {isPanelOpen && (
        <div className="fixed z-50" style={{ bottom: '24px', right: '448px' }}>
          <EntityDetailPanel />
        </div>
      )}

      {/* Always-visible graph/events panel */}
      <GraphOverlayPanel />
    </div>
  );
};
