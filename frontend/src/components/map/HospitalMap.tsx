import React, { useRef, useEffect, useCallback } from 'react';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';

export const HospitalMap: React.FC = () => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const patients      = useSimulationStore(s => s.patients);
  const doctors       = useSimulationStore(s => s.doctors);
  const tick          = useSimulationStore(s => s.tick);
  const shortageTicks = useSimulationStore(s => s.shortageTicks);

  const pushState = useCallback(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: 'sim_state', patients, doctors, tick, shortageTicks },
      '*'
    );
  }, [patients, doctors, tick, shortageTicks]);

  // Send on every tick
  useEffect(() => { pushState(); }, [pushState]);

  // Re-send after iframe (re)loads
  const onLoad = useCallback(() => { pushState(); }, [pushState]);

  // Listen for messages from the 3D scene
  useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      const msg = ev.data;
      if (!msg) return;
      if (msg.type === 'entity_click') {
        useUIStore.getState().selectEntity(msg.entityId, msg.entityType);
        const rect = iframeRef.current?.getBoundingClientRect();
        if (rect && msg.nx != null) {
          useUIStore.getState().setEntityScreenPos(
            rect.left + msg.nx * rect.width,
            rect.top  + msg.ny * rect.height,
          );
        }
      } else if (msg.type === 'entity_pos') {
        const rect = iframeRef.current?.getBoundingClientRect();
        if (rect) {
          useUIStore.getState().setEntityScreenPos(
            rect.left + msg.nx * rect.width,
            rect.top  + msg.ny * rect.height,
          );
        }
      } else if (msg.type === 'entity_deselect') {
        useUIStore.getState().clearSelection();
        useUIStore.getState().setEntityScreenPos(null, null);
      }
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  return (
    <iframe
      ref={iframeRef}
      src="/hospital3d.html"
      style={{ display: 'block', width: '100%', height: '100%', border: 'none' }}
      title="Hospital 3D"
      onLoad={onLoad}
    />
  );
};
