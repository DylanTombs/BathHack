import { useEffect, useRef, useCallback } from 'react';
import { useSimulationStore } from '../store/simulationStore';
import { useUIStore } from '../store/uiStore';
import type { SimulationState, ExplanationResponse, ScenarioConfig } from '../types/simulation';
import type { MetricsHistoryPoint } from '../store/simulationStore';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';
const RECONNECT_DELAY_MS = 2000;

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { applyState, setConnected, seedHistory, applyCommandAck } = useSimulationStore();
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
          setExplanation((msg as ExplanationResponse).explanation);
        } else if (msg.type === 'metrics_history') {
          seedHistory(msg.snapshots as MetricsHistoryPoint[]);
        } else if (msg.type === 'command_ack') {
          applyCommandAck(msg.is_running as boolean);
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
  }, [applyState, setConnected, seedHistory, setExplanation, applyCommandAck]);

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
  };
}
