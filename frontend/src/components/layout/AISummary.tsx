import React, { useMemo } from 'react';
import { useSimulationStore } from '../../store/simulationStore';

const WORD_CAP = 50;

function capWords(text: string): string {
  const words = text.split(' ');
  if (words.length <= WORD_CAP) return text;
  // Trim to cap, then back up to last sentence boundary
  const trimmed = words.slice(0, WORD_CAP).join(' ');
  const lastStop = Math.max(trimmed.lastIndexOf('.'), trimmed.lastIndexOf('!'), trimmed.lastIndexOf('?'));
  return lastStop > 20 ? trimmed.slice(0, lastStop + 1) : trimmed + '…';
}

function interpret(metrics: ReturnType<typeof useSimulationStore.getState>['metrics'], doctors: ReturnType<typeof useSimulationStore.getState>['doctors']): string {
  if (!metrics) return 'Waiting for simulation data…';

  const icuPct   = metrics.icu_occupancy_pct;
  const gwPct    = metrics.general_ward_occupancy_pct;
  const queue    = metrics.current_queue_length;
  const critical = metrics.critical_patients_waiting;
  const drUtil   = metrics.doctor_utilisation_pct;
  const mort     = metrics.mortality_rate_pct;
  const available = doctors.filter(d => d.is_available).length;

  const parts: string[] = [];

  // Capacity — lead with most pressing
  if (icuPct >= 100 && gwPct >= 100) {
    parts.push('The hospital is at full capacity — both ICU and general ward are completely full, leaving no room to absorb new admissions.');
  } else if (icuPct >= 90 && gwPct >= 90) {
    parts.push('The hospital is under severe strain with both wards nearly full.');
  } else if (icuPct >= 90) {
    parts.push('ICU is critically close to capacity and cannot safely accept many more patients.');
  } else if (gwPct >= 90) {
    parts.push('The general ward is almost full, limiting admission options for incoming patients.');
  } else if (icuPct < 50 && gwPct < 50) {
    parts.push('The hospital has good capacity headroom in both wards and is coping comfortably.');
  } else {
    parts.push('Bed availability is manageable but worth monitoring.');
  }

  // Critical waiting — highest urgency
  if (critical >= 3) {
    parts.push(`There are ${critical} critical patients waiting without care — this is a serious triage failure risk and needs immediate attention.`);
  } else if (critical === 2) {
    parts.push('Two critical patients are currently waiting unattended, which poses an escalating mortality risk.');
  } else if (critical === 1) {
    parts.push('One critical patient is waiting for care — priority triage required.');
  }

  // Queue
  if (queue > 15) {
    parts.push(`The waiting queue has grown to ${queue} patients, suggesting arrivals are outpacing the team's ability to process them.`);
  } else if (queue > 8) {
    parts.push(`A queue of ${queue} is building — throughput needs to increase to prevent further backlog.`);
  } else if (queue === 0) {
    parts.push('The waiting room is clear — the team is keeping pace with demand.');
  }

  // Doctors
  if (drUtil >= 100) {
    parts.push('All doctors are fully occupied with no slack in the system — any new critical arrivals will face delays.');
  } else if (drUtil >= 85) {
    parts.push(`Doctors are heavily utilised at ${drUtil.toFixed(0)}%, leaving little room for unexpected surges.`);
  } else if (available >= 2 && drUtil < 50) {
    parts.push(`${available} doctors are currently free — the clinical team has capacity to respond.`);
  }

  // Mortality
  if (mort > 10) {
    parts.push(`Mortality rate of ${mort.toFixed(1)}% is critically high — systemic triage or capacity issues are likely causing preventable deaths.`);
  } else if (mort > 5) {
    parts.push(`Mortality at ${mort.toFixed(1)}% is above acceptable levels and warrants a review of critical patient pathways.`);
  } else if (mort > 0) {
    parts.push(`Mortality rate is ${mort.toFixed(1)}% — within range but worth monitoring.`);
  }

  return capWords(parts.join(' '));
}

export const AISummary: React.FC = () => {
  const { metrics, doctors, patients, wards, tick, simDatetime } = useSimulationStore();

  const summary = useMemo(() => interpret(metrics, doctors), [metrics, doctors]);

  const icu = wards['icu'];
  const gw  = wards['general_ward'];
  const available = doctors.filter(d => d.is_available).length;
  const waiting   = patients.filter(p => p.location === 'waiting').length;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase">Situation Report</h3>
        <span className="text-xs text-gray-400 font-mono">{simDatetime} · T{tick}</span>
      </div>

      {/* Stats grid */}
      {metrics && icu && gw && (
        <div className="grid grid-cols-2 gap-2">
          {[
            { label: 'ICU',          value: `${icu.occupied}/${icu.capacity}`,   sub: `${metrics.icu_occupancy_pct.toFixed(0)}% full`,           hot: metrics.icu_occupancy_pct >= 90 },
            { label: 'General Ward', value: `${gw.occupied}/${gw.capacity}`,     sub: `${metrics.general_ward_occupancy_pct.toFixed(0)}% full`,   hot: metrics.general_ward_occupancy_pct >= 90 },
            { label: 'Queue',        value: metrics.current_queue_length,         sub: `${waiting} in waiting`,                                    hot: metrics.current_queue_length > 10 },
            { label: 'Critical ⚠',  value: metrics.critical_patients_waiting,    sub: 'waiting untreated',                                        hot: metrics.critical_patients_waiting > 0 },
            { label: 'Doctors',      value: `${available}/${doctors.length}`,     sub: `${metrics.doctor_utilisation_pct.toFixed(0)}% utilised`,   hot: metrics.doctor_utilisation_pct >= 90 },
            { label: 'Mortality',    value: `${metrics.mortality_rate_pct.toFixed(1)}%`, sub: `${metrics.total_patients_deceased} deceased`,       hot: metrics.mortality_rate_pct > 5 },
          ].map(({ label, value, sub, hot }) => (
            <div key={label} className={`rounded-lg px-3 py-2 border ${hot ? 'bg-red-50 border-red-200' : 'bg-gray-50 border-gray-100'}`}>
              <div className="text-xs font-semibold text-gray-500 uppercase">{label}</div>
              <div className={`text-lg font-extrabold ${hot ? 'text-red-600' : 'text-gray-800'}`}>{value}</div>
              <div className="text-xs text-gray-400">{sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* Semantic summary */}
      <div className="border-t border-gray-100 pt-3">
        <p className="text-base font-semibold text-gray-800 leading-relaxed">{summary}</p>
      </div>
    </div>
  );
};
