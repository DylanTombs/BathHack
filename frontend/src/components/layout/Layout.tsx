import React from 'react';
import { HospitalMap } from '../map/HospitalMap';
import { ControlPanel } from '../controls/ControlPanel';
import { EventLog } from '../event-log/EventLog';
import { MetricsBanner } from './MetricsBanner';
import { EntityDetailPanel } from './EntityDetailPanel';
import { GraphOverlayPanel } from '../graphs/GraphOverlayPanel';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';

export const Layout: React.FC = () => {
  const { connected, tick } = useSimulationStore();
  const { isPanelOpen, graphsOpen, toggleGraphs } = useUIStore();

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-xl">🏥</span>
          <h1 className="text-lg font-bold text-gray-900">Hospital Simulation</h1>
          <span className="text-xs text-gray-400">Agent-Based · LLM-Driven</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-gray-400 font-mono">Tick: {tick}</span>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`} />
            <span className="text-xs text-gray-500">{connected ? 'Live' : 'Disconnected'}</span>
          </div>
          {/* Graphs toggle — hamburger */}
          <button
            onClick={toggleGraphs}
            aria-label="Toggle live graphs"
            aria-expanded={graphsOpen}
            className={[
              'flex flex-col justify-center gap-1 w-8 h-8 rounded transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400',
              graphsOpen ? 'text-blue-600' : 'text-gray-500 hover:text-gray-800',
            ].join(' ')}
          >
            <span className="block h-0.5 w-5 bg-current rounded" />
            <span className="block h-0.5 w-5 bg-current rounded" />
            <span className="block h-0.5 w-5 bg-current rounded" />
          </button>
        </div>
      </header>

      {/* Metrics banner */}
      <MetricsBanner />

      {/* Main layout: left panel | map | right panel */}
      <div className="flex flex-1 gap-4 p-4 overflow-hidden" style={{ minHeight: 0 }}>
        {/* Left: controls only (charts moved to floating overlay) */}
        <div className="w-48 shrink-0 space-y-3 overflow-y-auto">
          <ControlPanel />
        </div>

        {/* Centre: hospital map */}
        <div className="flex-1 overflow-auto">
          <HospitalMap />
        </div>

        {/* Right: event log + entity detail */}
        <div className="w-72 shrink-0 space-y-3 overflow-y-auto">
          {isPanelOpen && <EntityDetailPanel />}
          <EventLog />
        </div>
      </div>

      {/* Fixed floating graph system */}
      <GraphOverlayPanel />
    </div>
  );
};
