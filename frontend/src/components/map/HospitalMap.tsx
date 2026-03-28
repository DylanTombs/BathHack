import React from 'react';
import { AnimatePresence } from 'framer-motion';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';
import { WardZone } from './WardZone';
import { PatientIcon } from './PatientIcon';
import { DoctorIcon } from './DoctorIcon';


const CELL_SIZE = 44;
const GRID_W = 20;
const GRID_H = 15;
const SVG_W = GRID_W * CELL_SIZE; // 880
const SVG_H = GRID_H * CELL_SIZE; // 660

const WARDS = [
  { name: 'waiting',      label: 'Waiting Area',  x: 0,  y: 0,  w: 8,  h: 6,  color: '#e0f2fe' },
  { name: 'general_ward', label: 'General Ward',   x: 0,  y: 6,  w: 12, h: 7,  color: '#dcfce7' },
  { name: 'icu',          label: 'ICU',            x: 12, y: 6,  w: 8,  h: 7,  color: '#fef3c7' },
  { name: 'discharged',   label: 'Discharge',      x: 8,  y: 0,  w: 12, h: 6,  color: '#f1f5f9' },
] as const;

const GridLines: React.FC<{ w: number; h: number; cellSize: number }> = ({ w, h, cellSize }) => (
  <g opacity={0.06}>
    {Array.from({ length: Math.floor(w / cellSize) + 1 }).map((_, i) => (
      <line key={`v${i}`} x1={i * cellSize} y1={0} x2={i * cellSize} y2={h} stroke="#94a3b8" strokeWidth={0.5} />
    ))}
    {Array.from({ length: Math.floor(h / cellSize) + 1 }).map((_, i) => (
      <line key={`h${i}`} x1={0} y1={i * cellSize} x2={w} y2={i * cellSize} stroke="#94a3b8" strokeWidth={0.5} />
    ))}
  </g>
);

const Legend: React.FC = () => (
  <g transform={`translate(${SVG_W - 180}, 10)`}>
    <rect x={0} y={0} width={170} height={110} rx={6} fill="white" opacity={0.9} stroke="#e5e7eb" strokeWidth={1} />
    <text x={8} y={16} fontSize={9} fontWeight="700" fill="#6b7280">SEVERITY</text>
    {[
      { color: '#22c55e', label: 'Low' },
      { color: '#f59e0b', label: 'Medium' },
      { color: '#ef4444', label: 'Critical' },
    ].map((item, i) => (
      <g key={item.label} transform={`translate(8, ${24 + i * 14})`}>
        <circle cx={5} cy={5} r={5} fill={item.color} />
        <text x={14} y={9} fontSize={9} fill="#374151">{item.label}</text>
      </g>
    ))}
    <text x={8} y={75} fontSize={9} fontWeight="700" fill="#6b7280">DOCTOR WORKLOAD</text>
    {[
      { color: '#3b82f6', label: 'Light' },
      { color: '#f97316', label: 'Heavy' },
      { color: '#dc2626', label: 'Overwhelmed' },
    ].map((item, i) => (
      <g key={item.label} transform={`translate(8, ${83 + i * 14})`}>
        <rect x={0} y={0} width={10} height={10} rx={2} fill={item.color} transform="rotate(45 5 5)" />
        <text x={14} y={9} fontSize={9} fill="#374151">{item.label}</text>
      </g>
    ))}
  </g>
);

export const HospitalMap: React.FC = () => {
  const { patients, doctors } = useSimulationStore();
  const { selectEntity, selectedEntityId } = useUIStore();

  return (
    <div className="relative w-full overflow-auto bg-gray-50 rounded-xl border border-gray-200 shadow-inner">
      <svg
        width={SVG_W}
        height={SVG_H}
        viewBox={`0 0 ${SVG_W} ${SVG_H}`}
        className="block"
        style={{ maxWidth: '100%' }}
      >
        {/* Ward backgrounds */}
        {WARDS.map(zone => (
          <WardZone key={zone.name} zone={zone} cellSize={CELL_SIZE} />
        ))}

        {/* Grid lines */}
        <GridLines w={SVG_W} h={SVG_H} cellSize={CELL_SIZE} />

        {/* Patients */}
        <AnimatePresence>
          {patients.map(patient => (
            <PatientIcon
              key={patient.id}
              patient={patient}
              cellSize={CELL_SIZE}
              isSelected={selectedEntityId === patient.id}
              onClick={() => selectEntity(patient.id, 'patient')}
              opacity={patient.location === 'discharged' ? 0.45 : 1}
            />
          ))}
        </AnimatePresence>

        {/* Doctors */}
        <AnimatePresence>
          {doctors.map(doctor => (
            <DoctorIcon
              key={doctor.id}
              doctor={doctor}
              cellSize={CELL_SIZE}
              isSelected={selectedEntityId === doctor.id}
              onClick={() => selectEntity(doctor.id, 'doctor')}
            />
          ))}
        </AnimatePresence>

        {/* Legend */}
        <Legend />
      </svg>
    </div>
  );
};
