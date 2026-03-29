import { useEffect, useRef, useCallback } from 'react';
import { useSimulationStore } from '../store/simulationStore';
import { useUIStore } from '../store/uiStore';
// useUIStore.getState() used inside ws handler to check current selection without stale closure
import type { SimulationState, ExplanationResponse, ScenarioConfig } from '../types/simulation';
import type { MetricsHistoryPoint, ReportPayload } from '../store/simulationStore';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';
const RECONNECT_DELAY_MS = 2000;

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { applyState, setConnected, seedHistory, applyCommandAck, setReportGenerating, setReportReady } = useSimulationStore();
  const { setExplanation, setExplanationLoading } = useUIStore();

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;

    ws.current = new WebSocket(WS_URL);

    ws.current.onopen = () => {
      setConnected(true);
      console.log('[WS] Connected');
    };

    ws.current.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string);
        if (msg.type === 'sim_state') {
          applyState(msg as SimulationState);
        } else if (msg.type === 'explanation') {
          const r = msg as ExplanationResponse;
          const { selectedEntityId, selectedEntityType } = useUIStore.getState();
          if (r.target_id === selectedEntityId && r.target_type === selectedEntityType) {
            setExplanation(r.explanation);
          } else {
            setExplanationLoading(false);
          }
        } else if (msg.type === 'metrics_history') {
          seedHistory(msg.snapshots as MetricsHistoryPoint[]);
        } else if (msg.type === 'command_ack') {
          applyCommandAck(msg.is_running as boolean);
        } else if (msg.type === 'report_generating') {
          setReportGenerating();
        } else if (msg.type === 'report_ready') {
          setReportReady(msg.report as ReportPayload);
        }
      } catch (e) {
        console.error('[WS] Parse error', e);
      }
    };

    ws.current.onclose = () => {
      setConnected(false);
      console.log('[WS] Disconnected — reconnecting...');
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
    };

    ws.current.onerror = (err) => {
      console.error('[WS] Error', err);
      ws.current?.close();
    };
  }, [applyState, setConnected, seedHistory, setExplanation, applyCommandAck, setReportGenerating, setReportReady]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  const sendCommand = useCallback((payload: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(payload));
    } else {
      console.warn('[WS] Command dropped — not connected:', payload);
    }
  }, []);

  const requestExplanation = useCallback((entityType: 'patient' | 'doctor', id: number) => {
    setExplanationLoading(true);
    sendCommand({
      command: entityType === 'patient' ? 'explain_patient' : 'explain_doctor',
      target_id: id,
    });
  }, [sendCommand, setExplanationLoading]);

  const triggerSurge = useCallback(() => sendCommand({ command: 'trigger_surge' }), [sendCommand]);
  const triggerShortage = useCallback(() => sendCommand({ command: 'trigger_shortage' }), [sendCommand]);
  const triggerRecovery = useCallback(() => sendCommand({ command: 'trigger_recovery' }), [sendCommand]);
  const startSim = useCallback(() => sendCommand({ command: 'start' }), [sendCommand]);
  const pauseSim = useCallback(() => sendCommand({ command: 'pause' }), [sendCommand]);
  const resetSim = useCallback(() => sendCommand({ command: 'reset' }), [sendCommand]);
  const addDoctor = useCallback((specialty: string) => sendCommand({ command: 'add_doctor', specialty }), [sendCommand]);
  const removeDoctor = useCallback(() => sendCommand({ command: 'remove_doctor' }), [sendCommand]);
  const addBed = useCallback((ward: string, count: number = 1) => sendCommand({ command: 'add_bed', ward, count }), [sendCommand]);
  const removeBed = useCallback((ward: string, count: number = 1) => sendCommand({ command: 'remove_bed', ward, count }), [sendCommand]);
  const generateReport = useCallback(() => sendCommand({ command: 'generate_report' }), [sendCommand]);

  const updateConfig = useCallback((config: Partial<ScenarioConfig>) => {
    sendCommand({ command: 'update_config', config });
  }, [sendCommand]);

  return {
    triggerSurge,
    triggerShortage,
    triggerRecovery,
    startSim,
    pauseSim,
    resetSim,
    updateConfig,
    requestExplanation,
    addDoctor,
    removeDoctor,
    addBed,
    removeBed,
    generateReport,
  };
}
