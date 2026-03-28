import React, { useRef, useEffect } from 'react';
import { useSimulationStore } from '../../store/simulationStore';
import { EventItem } from './EventItem';

export const EventLog: React.FC = () => {
  const { events } = useSimulationStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase">Event Log</h3>
        <span className="text-xs text-gray-400">{events.length} events</span>
      </div>
      <div className="h-64 overflow-y-auto p-2 space-y-2">
        {events.length === 0 ? (
          <p className="text-sm text-gray-400 text-center pt-8">Waiting for events…</p>
        ) : (
          events.slice(-4).map((event, i) => <EventItem key={`${event.tick}-${event.entity_id}-${i}`} event={event} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
