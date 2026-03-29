import React, { useCallback } from 'react';
import { createPortal } from 'react-dom';
import { InterventionTimeline } from './InterventionTimeline';
import type { ReportPayload } from '../../store/simulationStore';

interface Props {
  report: ReportPayload;
  onClose: () => void;
}

export const ReportModal: React.FC<Props> = ({ report, onClose }) => {
  const handleExport = useCallback(() => {
    const content = [
      `C Clinic Report`,
      `Duration: ${report.total_ticks} ticks`,
      ``,
      `HEADLINE STATS`,
      `Patients arrived: ${report.total_arrived}`,
      `Discharged: ${report.total_discharged}`,
      `Deceased: ${report.total_deceased}`,
      `Mortality rate: ${report.final_mortality_rate_pct.toFixed(1)}%`,
      `Avg wait time: ${report.avg_wait_time_ticks.toFixed(1)} ticks`,
      `Peak queue: ${report.peak_queue_length}`,
      `Peak ICU occupancy: ${report.peak_icu_occupancy_pct.toFixed(1)}%`,
      ``,
      report.llm_analysis,
    ].join('\n');
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `simulation-report-t${report.total_ticks}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, [report]);

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Simulation Report</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {report.total_ticks} ticks · {report.total_simulated_hours} simulated hours
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleExport}
              className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
            >
              Download .txt
            </button>
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm rounded-lg bg-gray-900 text-white hover:bg-gray-700 transition-colors"
            >
              Close
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-6">
          {/* Headline stats cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Patients" value={report.total_arrived} color="blue" />
            <StatCard label="Discharged" value={report.total_discharged} color="green" />
            <StatCard label="Deceased" value={report.total_deceased} color="red" />
            <StatCard
              label="Mortality"
              value={`${report.final_mortality_rate_pct.toFixed(1)}%`}
              color={report.final_mortality_rate_pct > 10 ? 'red' : 'amber'}
            />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Avg Wait" value={`${report.avg_wait_time_ticks.toFixed(1)} t`} color="gray" />
            <StatCard label="Peak Queue" value={report.peak_queue_length} color="orange" />
            <StatCard label="Peak ICU" value={`${report.peak_icu_occupancy_pct.toFixed(0)}%`} color="purple" />
            <StatCard label="Peak General" value={`${report.peak_general_occupancy_pct.toFixed(0)}%`} color="teal" />
          </div>

          {/* Intervention Timeline */}
          {report.interventions.length > 0 && (
            <Section title="Intervention Timeline">
              <InterventionTimeline
                interventions={report.interventions}
                totalTicks={report.total_ticks}
              />
            </Section>
          )}

          {/* Phase Table */}
          {report.phases.length > 0 && (
            <Section title="Phase Breakdown">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-100">
                      <th className="pb-2 pr-3 font-medium">Phase</th>
                      <th className="pb-2 pr-3 font-medium">Ticks</th>
                      <th className="pb-2 pr-3 font-medium">Avg Queue</th>
                      <th className="pb-2 pr-3 font-medium">ICU %</th>
                      <th className="pb-2 pr-3 font-medium">General %</th>
                      <th className="pb-2 pr-3 font-medium">Discharged</th>
                      <th className="pb-2 font-medium">Deaths</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.phases.map((p, i) => (
                      <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-1.5 pr-3 font-medium text-gray-800">{p.label}</td>
                        <td className="py-1.5 pr-3 text-gray-500 font-mono">{p.start_tick}–{p.end_tick}</td>
                        <td className="py-1.5 pr-3">{p.avg_queue.toFixed(1)}</td>
                        <td className="py-1.5 pr-3">
                          <span className={p.avg_icu_pct > 80 ? 'text-red-600 font-semibold' : ''}>
                            {p.avg_icu_pct.toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-1.5 pr-3">{p.avg_general_pct.toFixed(1)}%</td>
                        <td className="py-1.5 pr-3 text-green-700">{p.discharges}</td>
                        <td className="py-1.5">
                          <span className={p.deaths > 0 ? 'text-red-600 font-semibold' : 'text-gray-400'}>
                            {p.deaths}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          {/* AI Analysis */}
          <Section title="AI Analysis">
            <MarkdownText text={report.llm_analysis} />
          </Section>
        </div>
      </div>
    </div>,
    document.body
  );
};


// ── Sub-components ─────────────────────────────────────────────────────────────

const COLOR_MAP: Record<string, string> = {
  blue: 'bg-blue-50 text-blue-800',
  green: 'bg-green-50 text-green-800',
  red: 'bg-red-50 text-red-800',
  amber: 'bg-amber-50 text-amber-800',
  orange: 'bg-orange-50 text-orange-800',
  purple: 'bg-purple-50 text-purple-800',
  teal: 'bg-teal-50 text-teal-800',
  gray: 'bg-gray-50 text-gray-700',
};

const StatCard: React.FC<{ label: string; value: string | number; color: string }> = ({ label, value, color }) => (
  <div className={`rounded-xl p-3 ${COLOR_MAP[color] ?? COLOR_MAP.gray}`}>
    <div className="text-xs opacity-70 mb-0.5">{label}</div>
    <div className="text-xl font-bold">{value}</div>
  </div>
);

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <div>
    <h3 className="text-sm font-semibold text-gray-700 mb-2 pb-1 border-b border-gray-100">{title}</h3>
    {children}
  </div>
);

/** Renders LLM markdown output without a library dependency. */
const MarkdownText: React.FC<{ text: string }> = ({ text }) => {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={elements.length} className="list-disc list-inside space-y-1 text-sm text-gray-700 mb-3">
          {listItems.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: renderInline(item) }} />
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  lines.forEach((line, i) => {
    if (line.startsWith('## ')) {
      flushList();
      elements.push(
        <h2 key={i} className="text-base font-bold text-gray-900 mt-4 mb-1">
          {line.slice(3)}
        </h2>
      );
    } else if (line.startsWith('### ')) {
      flushList();
      elements.push(
        <h3 key={i} className="text-sm font-semibold text-gray-800 mt-3 mb-1">
          {line.slice(4)}
        </h3>
      );
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      listItems.push(line.slice(2));
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      elements.push(
        <p key={i} className="text-sm text-gray-700 mb-2"
          dangerouslySetInnerHTML={{ __html: renderInline(line) }}
        />
      );
    }
  });
  flushList();

  return <div className="prose-sm">{elements}</div>;
};

function renderInline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-gray-100 px-1 rounded text-xs">$1</code>');
}
