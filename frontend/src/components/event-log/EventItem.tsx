import React, { useState } from 'react';
import type { SimEvent } from '../../types/simulation';

const SEVERITY_STYLE: Record<string, string> = {
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  critical: 'border-red-200 bg-red-50 text-red-800',
  deceased: 'border-gray-800 bg-gray-900 text-white',
};

export const EventItem: React.FC<{ event: SimEvent }> = ({ event }) => {
  const isDeceased = event.event_type === 'patient_deceased';

  return (
    <div className={`rounded border px-3 py-2.5 ${isDeceased ? SEVERITY_STYLE.deceased : (SEVERITY_STYLE[event.severity] ?? SEVERITY_STYLE.info)}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="font-mono opacity-60 shrink-0 text-xs">T{event.tick}</span>
        <span className="text-sm font-extrabold leading-snug">{event.raw_description}</span>
      </div>
      {event.llm_explanation && (
        <p className="text-sm opacity-80 leading-snug pl-7">{event.llm_explanation}</p>
      )}
    </div>
  );
};
