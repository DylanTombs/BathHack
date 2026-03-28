import React, { useState } from 'react';
import ReactDOM from 'react-dom';
import { motion } from 'framer-motion';
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
}

interface TooltipData {
  x: number;
  y: number;
}

export const PatientIcon: React.FC<Props> = ({ patient, cellSize, isSelected, onClick }) => {
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);
  const cx = (patient.grid_x + 0.5) * cellSize;
  const cy = (patient.grid_y + 0.5) * cellSize;
  const r = isSelected ? 12 : 9;

  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0 }}
      transition={{ duration: 0.3 }}
      onClick={onClick}
      onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setTooltip(null)}
      style={{ cursor: 'pointer' }}
    >
      {/* Pulsing ring for critical patients */}
      {patient.severity === 'critical' && (
        <motion.circle
          cx={cx} cy={cy}
          r={14}
          fill="none"
          stroke="#ef4444"
          strokeWidth={2}
          animate={{ opacity: [1, 0, 1], r: [14, 18, 14] }}
          transition={{ repeat: Infinity, duration: 1.5 }}
        />
      )}
      {/* Position animation wrapper */}
      <motion.g
        animate={{ x: cx - (isSelected ? 12 : 9), y: cy - (isSelected ? 12 : 9) }}
        initial={false}
        transition={{ type: 'spring', stiffness: 120, damping: 20 }}
      >
        {/* Body circle */}
        <circle
          cx={isSelected ? 12 : 9}
          cy={isSelected ? 12 : 9}
          r={r}
          fill={SEVERITY_COLOR[patient.severity]}
          stroke={isSelected ? '#1d4ed8' : CONDITION_STROKE[patient.condition]}
          strokeWidth={isSelected ? 3 : 2}
          opacity={0.9}
        />
        {/* P label */}
        <text
          x={isSelected ? 12 : 9}
          y={(isSelected ? 12 : 9) + 4}
          textAnchor="middle"
          fontSize={10}
          fontWeight="bold"
          fill="white"
        >
          P
        </text>
      </motion.g>
      {/* Tooltip — portal renders above all SVG elements */}
      {tooltip && ReactDOM.createPortal(
        <div
          style={{
            position: 'fixed',
            left: tooltip.x + 14,
            top: tooltip.y - 40,
            zIndex: 9999,
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
          <div>Sev: <span style={{ color: SEVERITY_COLOR[patient.severity] }}>{patient.severity}</span> · {patient.condition}</div>
          <div style={{ opacity: 0.75, fontSize: 10 }}>{patient.diagnosis}</div>
        </div>,
        document.body
      )}
    </motion.g>
  );
};
