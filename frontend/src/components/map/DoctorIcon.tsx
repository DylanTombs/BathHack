import React, { useState } from 'react';
import ReactDOM from 'react-dom';
import { motion } from 'framer-motion';
import type { Doctor, WorkloadLevel } from '../../types/simulation';

const WORKLOAD_COLOR: Record<WorkloadLevel, string> = {
  light: '#3b82f6',
  moderate: '#8b5cf6',
  heavy: '#f97316',
  overwhelmed: '#dc2626',
};

interface Props {
  doctor: Doctor;
  cellSize: number;
  isSelected: boolean;
  onClick: () => void;
}

export const DoctorIcon: React.FC<Props> = ({ doctor, cellSize, isSelected, onClick }) => {
  const [tooltip, setTooltip] = useState<{ x: number; y: number } | null>(null);
  const cx = (doctor.grid_x + 0.5) * cellSize;
  const cy = (doctor.grid_y + 0.5) * cellSize;
  const color = WORKLOAD_COLOR[doctor.workload];

  // Shift overlay 8px down and right
  return (
    <motion.g
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1, x: cx - 12 + 8, y: cy - 14 + 8 }}
      exit={{ opacity: 0, scale: 0 }}
      transition={{ type: 'spring', stiffness: 100, damping: 18 }}
      onClick={onClick}
      onMouseEnter={(e) => setTooltip({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setTooltip(null)}
      style={{ cursor: 'pointer' }}
    >
      {/* Diamond shape */}
      <rect
        x={0} y={0} width={24} height={24}
        rx={4}
        fill={color}
        stroke={isSelected ? '#1d4ed8' : 'white'}
        strokeWidth={isSelected ? 3 : 1.5}
        transform="rotate(45 12 12)"
        opacity={0.95}
      />
      <text
        x={12} y={16}
        textAnchor="middle"
        fontSize={9}
        fontWeight="bold"
        fill="white"
      >
        Dr
      </text>
      {/* Capacity bar */}
      {doctor.capacity > 0 && (
        <g>
          {Array.from({ length: doctor.capacity }).map((_, i) => (
            <rect
              key={i}
              x={i * 7} y={26} width={5} height={3}
              fill={i < doctor.assigned_patient_ids.length ? color : '#e5e7eb'}
              rx={1}
            />
          ))}
        </g>
      )}
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
          <div style={{ fontWeight: 700 }}>{doctor.name}</div>
          <div>Workload: <span style={{ color }}>{doctor.workload}</span> · {doctor.assigned_patient_ids.length}/{doctor.capacity} pts</div>
          <div style={{ opacity: 0.75, fontSize: 10 }}>{doctor.specialty}</div>
        </div>,
        document.body
      )}
    </motion.g>
  );
};
