import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { Patient, Severity } from '../../types/simulation';

const SEVERITY_COLOR: Record<Severity, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  critical: '#ef4444',
};

const CONDITION_STROKE: Record<string, string> = {
  stable: '#6b7280',
  improving: '#22c55e',
  worsening: '#ef4444',
};

interface Props {
  patient: Patient;
  cellSize: number;
  isSelected: boolean;
  onClick: () => void;
  opacity?: number;
}

interface TooltipData {
  x: number;
  y: number;
}

export const PatientIcon: React.FC<Props> = ({ patient, cellSize, isSelected, onClick, opacity = 1 }) => {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const r = isSelected ? 12 : 9;
  // Pixel center of the patient's grid cell
  const cx = (patient.grid_x + 0.5) * cellSize;
  const cy = (patient.grid_y + 0.5) * cellSize;
  // Group origin is top-left of the circle bounding box; scale is applied around circle center (r,r)
  // Shift overlay 8px down and right
  const gx = cx - r + 8;
  const gy = cy - r + 8;

  return (
    <motion.g
      // Single element handles both position (x/y) and entrance animation (scale/opacity)
      // transformOrigin set to circle center so scale doesn't jump to SVG origin (0,0)
      initial={{ opacity: 0, scale: 0.5, x: gx, y: gy }}
      animate={{ opacity: opacity, scale: 1, x: gx, y: gy }}
      exit={{ opacity: 0, scale: 0 }}
      transition={{ duration: 0.25 }}
      style={{ transformOrigin: `${r}px ${r}px`, cursor: 'pointer' }}
      onClick={onClick}
      onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setTooltip(null)}
    >
      {/* Pulsing ring for critical patients — position relative to circle center */}
      {patient.severity === 'critical' && (
        <motion.circle
          cx={r} cy={r}
          r={14}
          fill="none"
          stroke="#ef4444"
          strokeWidth={2}
          animate={{ opacity: [1, 0, 1], r: [14, 18, 14] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        />
      )}
      {/* Body circle */}
      <circle
        cx={r} cy={r}
        r={r}
        fill={SEVERITY_COLOR[patient.severity]}
        stroke={isSelected ? '#1d4ed8' : CONDITION_STROKE[patient.condition]}
        strokeWidth={isSelected ? 3 : 2}
        opacity={0.9}
      />
      {/* P label */}
      <text
        x={r} y={r + 4}
        textAnchor="middle"
        fontSize={10}
        fontWeight="bold"
        fill="white"
      >
        P
      </text>
      {/* Tooltip */}
      <AnimatePresence>
        {tooltip && (
          <foreignObject x={r * 2 + 5} y={r - 40} width={160} height={90} style={{ overflow: 'visible' }}>
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              style={{
                background: 'rgba(17,24,39,0.95)',
                color: 'white',
                borderRadius: 6,
                padding: '6px 8px',
                fontSize: 11,
                lineHeight: 1.5,
                pointerEvents: 'none',
                whiteSpace: 'nowrap',
                boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
              }}
            >
              <div style={{ fontWeight: 700 }}>{patient.name}</div>
              <div>Severity: <span style={{ color: SEVERITY_COLOR[patient.severity] }}>{patient.severity}</span></div>
              <div>Condition: {patient.condition}</div>
              <div style={{ opacity: 0.8, fontSize: 10 }}>{patient.diagnosis}</div>
              <div style={{ opacity: 0.7, fontSize: 10 }}>Wait: {patient.wait_time_ticks} ticks</div>
            </motion.div>
          </foreignObject>
        )}
      </AnimatePresence>
    </motion.g>
  );
};
