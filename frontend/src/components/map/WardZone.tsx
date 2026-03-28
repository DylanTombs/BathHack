import React from 'react';
import { useSimulationStore } from '../../store/simulationStore';
import type { WardName } from '../../types/simulation';

interface ZoneConfig {
  name: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
}

interface Props {
  zone: ZoneConfig;
  cellSize: number;
}

function getOccupancyBorderColor(pct: number): string {
  if (pct >= 90) return '#ef4444'; // red
  if (pct >= 70) return '#f59e0b'; // amber
  return '#22c55e';                // green
}

export const WardZone: React.FC<Props> = ({ zone, cellSize }) => {
  const { wards } = useSimulationStore();
  const ward = wards[zone.name as WardName];
  const occupancyPct = ward?.occupancy_pct ?? 0;
  const borderColor = getOccupancyBorderColor(occupancyPct);

  const px = zone.x * cellSize;
  const py = zone.y * cellSize;
  const pw = zone.w * cellSize;
  const ph = zone.h * cellSize;

  return (
    <g>
      {/* Background fill */}
      <rect
        x={px} y={py} width={pw} height={ph}
        fill={zone.color}
        stroke={borderColor}
        strokeWidth={2}
        rx={4}
        opacity={0.85}
      />
      {/* Ward label */}
      <text
        x={px + 8}
        y={py + 16}
        fontSize={11}
        fontWeight="600"
        fill="#374151"
        opacity={0.8}
      >
        {zone.label}
      </text>
      {/* Occupancy badge */}
      {ward && (
        <g>
          <rect
            x={px + pw - 44}
            y={py + 6}
            width={38}
            height={16}
            fill={borderColor}
            rx={8}
            opacity={0.15}
          />
          <text
            x={px + pw - 25}
            y={py + 17}
            fontSize={9}
            fontWeight="700"
            fill={borderColor}
            textAnchor="middle"
          >
            {occupancyPct.toFixed(0)}%
          </text>
        </g>
      )}
    </g>
  );
};
