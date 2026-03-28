// frontend/src/types/simulation.ts

export type Severity = 'low' | 'medium' | 'critical';
export type PatientCondition = 'stable' | 'worsening' | 'improving';
export type PatientLocation = 'waiting' | 'general_ward' | 'icu' | 'discharged';
export type WorkloadLevel = 'light' | 'moderate' | 'heavy' | 'overwhelmed';
export type WardName = 'waiting' | 'general_ward' | 'icu' | 'discharged';
export type EventSeverity = 'info' | 'warning' | 'critical';

export interface Patient {
  id: number;
  name: string;
  severity: Severity;
  condition: PatientCondition;
  location: PatientLocation;
  assigned_doctor_id: number | null;
  arrived_at_tick: number;
  treatment_started_tick: number | null;
  treatment_duration_ticks: number;
  wait_time_ticks: number;
  age: number;
  diagnosis: string;
  grid_x: number;
  grid_y: number;
  last_event_explanation: string | null;
  backstory: string | null;
  pending_destination: string | null;
  discharge_stay_ticks: number;
  discharge_started_tick: number | null;
}

export interface Doctor {
  id: number;
  name: string;
  assigned_patient_ids: number[];
  capacity: number;
  workload: WorkloadLevel;
  specialty: string;
  grid_x: number;
  grid_y: number;
  is_available: boolean;
  decisions_made: number;
  last_decision_reason: string | null;
  last_decision_confidence: number | null;
  last_decision_patient_id: number | null;
  ward: string;
}

export interface Bed {
  id: number;
  ward: WardName;
  occupied_by_patient_id: number | null;
  grid_x: number;
  grid_y: number;
}

export interface WardState {
  name: WardName;
  capacity: number;
  occupied: number;
  occupancy_pct: number;
  is_full: boolean;
}

export interface Metrics {
  tick: number;
  simulated_hour: number;
  total_patients_arrived: number;
  total_patients_discharged: number;
  avg_wait_time_ticks: number;
  avg_treatment_time_ticks: number;
  current_queue_length: number;
  general_ward_occupancy_pct: number;
  icu_occupancy_pct: number;
  doctor_utilisation_pct: number;
  throughput_last_10_ticks: number;
  critical_patients_waiting: number;
}

export interface SimEvent {
  tick: number;
  event_type: string;
  entity_id: number;
  entity_type: 'patient' | 'doctor';
  raw_description: string;
  llm_explanation: string | null;
  severity: EventSeverity;
}

export interface SimulationState {
  type: 'sim_state';
  tick: number;
  timestamp: number;
  sim_datetime: string;
  scenario: string;
  is_running: boolean;
  patients: Patient[];
  doctors: Doctor[];
  beds: Bed[];
  wards: Record<WardName, WardState>;
  metrics: Metrics;
  events: SimEvent[];
  arrival_rate: number;
  surge_ticks_remaining: number;
  shortage_ticks_remaining: number;
  tick_speed_seconds?: number;
}

export interface ExplanationResponse {
  type: 'explanation';
  target_id: number;
  target_type: 'patient' | 'doctor';
  explanation: string;
  tick: number;
}

export interface ScenarioConfig {
  general_ward_beds: number;
  icu_beds: number;
  num_doctors: number;
  arrival_rate_per_tick: number;
  tick_speed_seconds: number;
}
