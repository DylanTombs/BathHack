import React, { useState } from 'react';
import type { SimEvent } from '../../types/simulation';

const SEVERITY_STYLE: Record<string, string> = {
  info: 'border-blue-200 bg-blue-50 text-blue-800',
  warning: 'border-amber-200 bg-amber-50 text-amber-800',
  critical: 'border-red-200 bg-red-50 text-red-800',
  deceased: 'border-gray-800 bg-gray-900 text-white',
};

export const EventItem: React.FC<{ event: SimEvent }> = ({ event }) => {
  const [expanded, setExpanded] = useState(false);
  const hasLLM = !!event.llm_explanation;
  const isDeceased = event.event_type === 'patient_deceased';

  return (
    <div className={`text-xs rounded border px-2 py-1.5 ${isDeceased ? SEVERITY_STYLE.deceased : (SEVERITY_STYLE[event.severity] ?? SEVERITY_STYLE.info)}`}>
      <div className="flex items-start gap-1">
        <span className="font-mono opacity-60 shrink-0">T{event.tick}</span>
        <span className="flex-1">
          {expanded && hasLLM ? event.llm_explanation : event.raw_description}
        </span>
        {hasLLM && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 font-medium opacity-70 hover:opacity-100 ml-1"
            title="Toggle LLM explanation"
          >
            {expanded ? '▲' : '🤖'}
          </button>
        )}
      </div>
    </div>
  );
};
