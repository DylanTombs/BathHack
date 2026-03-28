import React, { useMemo } from 'react';
import { useSimulationStore } from '../../store/simulationStore';

export const AISummary: React.FC = () => {
  const { tick, simDatetime, patients, doctors, wards, metrics, events } = useSimulationStore();

  // Compose detailed stats summary
  const stats = useMemo(() => {
    if (!metrics) return null;
    const title = `Hospital State at ${simDatetime} (Tick ${tick})`;
    const icu = wards['icu'];
    const gw = wards['general_ward'];
    const totalDoctors = doctors.length;
    const availableDoctors = doctors.filter(d => d.is_available).length;
    const totalPatients = patients.length;
    const icuPatients = patients.filter(p => p.location === 'icu').length;
    const gwPatients = patients.filter(p => p.location === 'general_ward').length;
    const waitingPatients = patients.filter(p => p.location === 'waiting').length;
    const dischargedPatients = patients.filter(p => p.location === 'discharged').length;
    return (
      <>
        <div className="font-bold text-blue-900 mb-2 text-lg">{title}</div>
        <div className="mb-1 text-blue-800">ICU: <b>{icu.occupied}</b> / {icu.capacity} beds occupied ({metrics.icu_occupancy_pct}% full)</div>
        <div className="mb-1 text-blue-800">General Ward: <b>{gw.occupied}</b> / {gw.capacity} beds occupied ({metrics.general_ward_occupancy_pct}% full)</div>
        <div className="mb-1 text-blue-800">Queue: <b>{metrics.current_queue_length}</b> waiting</div>
        <div className="mb-1 text-blue-800">Throughput (last 10 ticks): <b>{metrics.throughput_last_10_ticks}</b></div>
        <div className="mb-1 text-blue-800">Avg Wait Time: <b>{metrics.avg_wait_time_ticks}</b> ticks</div>
        <div className="mb-1 text-blue-800">Avg Treatment Time: <b>{metrics.avg_treatment_time_ticks}</b> ticks</div>
        <div className="mb-1 text-blue-800">Critical Patients Waiting: <b>{metrics.critical_patients_waiting}</b></div>
        <div className="mb-1 text-blue-800">Doctor Utilisation: <b>{metrics.doctor_utilisation_pct}%</b></div>
        <div className="mb-1 text-blue-800">Doctors: <b>{availableDoctors}</b> available / {totalDoctors} total</div>
        <div className="mb-1 text-blue-800">Patients: <b>{totalPatients}</b> (ICU: {icuPatients}, General: {gwPatients}, Waiting: {waitingPatients}, Discharged: {dischargedPatients})</div>
      </>
    );
  }, [tick, simDatetime, patients, doctors, wards, metrics]);

  // Find the latest event with an LLM explanation
  const latestLLMEvent = useMemo(() => {
    if (!events || events.length === 0) return null;
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].llm_explanation) return events[i];
    }
    return null;
  }, [events]);

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 shadow-sm flex flex-col h-full">
      <div className="flex-1 flex flex-col justify-start">
        {stats}
      </div>
      <div className="mt-4">
        <div className="text-blue-900 text-base font-semibold mb-1">AI Interpretation</div>
        <div className="text-blue-800 text-sm whitespace-pre-line min-h-[4rem]">
          {latestLLMEvent?.llm_explanation || 'No AI summary available yet.'}
        </div>
      </div>
    </div>
  );
};
