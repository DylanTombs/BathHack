import React from 'react';
import { HospitalMap } from '../map/HospitalMap';
import { ControlPanel } from '../controls/ControlPanel';
import { OccupancyChart } from '../charts/OccupancyChart';
import { QueueChart } from '../charts/QueueChart';
import { ThroughputChart } from '../charts/ThroughputChart';
import { EventLog } from '../event-log/EventLog';
import { MetricsBanner } from './MetricsBanner';
import { EntityDetailPanel } from './EntityDetailPanel';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';

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

      {/* Main layout: left panel | map | right panel */}
      <div className="flex flex-1 gap-4 p-4 overflow-hidden" style={{ minHeight: 0 }}>
        {/* Left: charts + controls */}
        <div className="w-64 shrink-0 space-y-3 overflow-y-auto">
          <ControlPanel />
          <OccupancyChart />
          <QueueChart />
          <ThroughputChart />
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
    </div>
  );
};
