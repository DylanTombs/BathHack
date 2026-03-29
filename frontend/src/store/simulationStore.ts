import { create } from 'zustand';
import type {
  SimulationState, Patient, Doctor, Metrics,
  SimEvent, WardName, WardState
} from '../types/simulation';

export interface ReportPhase {
  label: string;
  start_tick: number;
  end_tick: number;
  avg_queue: number;
  avg_icu_pct: number;
  avg_general_pct: number;
  discharges: number;
  deaths: number;
  intervention_type: string | null;
}

export interface ReportIntervention {
  tick: number;
  simulated_hour: number;
  intervention_type: string;
  detail: Record<string, unknown>;
  metrics_at_time: {
    current_queue_length: number;
    icu_occupancy_pct: number;
    general_ward_occupancy_pct: number;
    critical_patients_waiting: number;
  };
}

export interface ReportPayload {
  total_ticks: number;
  total_simulated_hours: number;
  total_arrived: number;
  total_discharged: number;
  total_deceased: number;
  final_mortality_rate_pct: number;
  avg_wait_time_ticks: number;
  avg_treatment_time_ticks: number;
  peak_queue_length: number;
  peak_icu_occupancy_pct: number;
  peak_general_occupancy_pct: number;
  peak_critical_waiting: number;
  phases: ReportPhase[];
  interventions: ReportIntervention[];
  llm_analysis: string;
}

export interface MetricsHistoryPoint {
  tick: number;
  general_ward_occupancy_pct: number;
  icu_occupancy_pct: number;
  current_queue_length: number;
  throughput_last_10_ticks: number;
  critical_patients_waiting: number;
  doctor_utilisation_pct: number;
}

interface SimulationStore {
  // Core state
  tick: number;
  isRunning: boolean;
  scenario: string;
  simDatetime: string;
  arrivalRate: number;
  tickSpeedSeconds: number;
  severityLevel: number;
  surgeTicks: number;
  shortageTicks: number;
  patients: Patient[];
  doctors: Doctor[];
  metrics: Metrics | null;
  wards: Record<WardName, WardState>;
  events: SimEvent[];

  // History for charts (last 100 ticks)
  metricsHistory: MetricsHistoryPoint[];

  // WebSocket status
  connected: boolean;

  // Report state
  reportState: 'idle' | 'generating' | 'ready';
  report: ReportPayload | null;

  // Actions
  applyState: (state: SimulationState) => void;
  appendEvents: (events: SimEvent[]) => void;
  setConnected: (v: boolean) => void;
  seedHistory: (history: MetricsHistoryPoint[]) => void;
  applyCommandAck: (isRunning: boolean) => void;
  setReportGenerating: () => void;
  setReportReady: (report: ReportPayload) => void;
  clearReport: () => void;
}

export const useSimulationStore = create<SimulationStore>((set, get) => ({
  tick: 0,
  isRunning: false,
  scenario: 'normal',
  simDatetime: 'Monday 06:00',
  arrivalRate: 1.5,
  tickSpeedSeconds: 1.0,
  severityLevel: 2,
  surgeTicks: 0,
  shortageTicks: 0,
  patients: [],
  doctors: [],
  metrics: null,
  wards: {} as Record<WardName, WardState>,
  events: [],
  metricsHistory: [],
  connected: false,
  reportState: 'idle',
  report: null,

  applyState: (state: SimulationState) => {
    set({
      tick: state.tick,
      isRunning: state.is_running,
      scenario: state.scenario,
      simDatetime: state.sim_datetime,
      arrivalRate: state.arrival_rate,
      tickSpeedSeconds: state.tick_speed_seconds ?? get().tickSpeedSeconds,
      severityLevel: state.severity_level ?? get().severityLevel,
      surgeTicks: state.surge_ticks_remaining,
      shortageTicks: state.shortage_ticks_remaining,
      patients: state.patients,
      doctors: state.doctors,
      metrics: state.metrics,
      wards: state.wards,
    });
    // Append new events, deduplicating by tick+entity+type+description
    const prev = get().events;
    const seen = new Set(prev.map(e => `${e.tick}-${e.entity_id}-${e.event_type}-${e.raw_description}`));
    const fresh = state.events.filter(e => !seen.has(`${e.tick}-${e.entity_id}-${e.event_type}-${e.raw_description}`));
    if (fresh.length > 0) {
      const combined = [...prev, ...fresh].sort((a, b) => a.tick - b.tick).slice(-50);
      set({ events: combined });
    }
    // Append to history
    if (state.metrics) {
      const { metrics } = state;
      const point: MetricsHistoryPoint = {
        tick: metrics.tick,
        general_ward_occupancy_pct: metrics.general_ward_occupancy_pct,
        icu_occupancy_pct: metrics.icu_occupancy_pct,
        current_queue_length: metrics.current_queue_length,
        throughput_last_10_ticks: metrics.throughput_last_10_ticks,
        critical_patients_waiting: metrics.critical_patients_waiting,
        doctor_utilisation_pct: metrics.doctor_utilisation_pct,
      };
      const hist = [...get().metricsHistory, point].slice(-100);
      set({ metricsHistory: hist });
    }
  },

  appendEvents: (events) => {
    const prev = get().events;
    set({ events: [...prev, ...events].slice(-50) });
  },

  setConnected: (v) => set({ connected: v }),
  seedHistory: (history) => set({ metricsHistory: history }),
  applyCommandAck: (isRunning) => set({ isRunning }),
  setReportGenerating: () => set({ reportState: 'generating', report: null }),
  setReportReady: (report) => set({ reportState: 'ready', report }),
  clearReport: () => set({ reportState: 'idle', report: null }),
}));
