import React, { Suspense, useRef, useMemo } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { useGLTF, OrbitControls, Html, Environment } from '@react-three/drei';
import * as THREE from 'three';
import { useSimulationStore } from '../../store/simulationStore';
import { useUIStore } from '../../store/uiStore';
import type { Patient, Doctor } from '../../types/simulation';

const GRID_W = 20;
const GRID_H = 15;

const SEVERITY_COLOR: Record<string, string> = {
  low: '#22c55e',
  medium: '#f59e0b',
  critical: '#ef4444',
};

const WORKLOAD_COLOR: Record<string, string> = {
  light: '#3b82f6',
  moderate: '#8b5cf6',
  heavy: '#f97316',
  overwhelmed: '#dc2626',
};

// Converts 2D grid position to 3D world position within the model bounds
function gridToWorld(
  gx: number,
  gy: number,
  bounds: THREE.Box3,
): [number, number, number] {
  const size = new THREE.Vector3();
  bounds.getSize(size);
  const center = new THREE.Vector3();
  bounds.getCenter(center);

  const x = center.x - size.x / 2 + (gx / GRID_W) * size.x;
  const z = center.z - size.z / 2 + (gy / GRID_H) * size.z;
  const y = bounds.max.y + 1.5;

  return [x, y, z];
}

// Pulsing ring for critical patients
const PulsingRing: React.FC<{ color: string }> = ({ color }) => {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const s = 1 + 0.4 * Math.abs(Math.sin(clock.getElapsedTime() * 2));
    ref.current.scale.set(s, s, s);
    (ref.current.material as THREE.MeshBasicMaterial).opacity =
      0.6 - 0.4 * Math.abs(Math.sin(clock.getElapsedTime() * 2));
  });
  return (
    <mesh ref={ref}>
      <ringGeometry args={[0.55, 0.75, 24]} />
      <meshBasicMaterial color={color} transparent opacity={0.5} side={THREE.DoubleSide} />
    </mesh>
  );
};

const PatientMarker: React.FC<{
  patient: Patient;
  position: [number, number, number];
  isSelected: boolean;
  onClick: () => void;
}> = ({ patient, position, isSelected, onClick }) => {
  const color = SEVERITY_COLOR[patient.severity] ?? '#94a3b8';
  const opacity = patient.location === 'discharged' ? 0.45 : 1;

  return (
    <group position={position} onClick={(e) => { e.stopPropagation(); onClick(); }}>
      {patient.severity === 'critical' && <PulsingRing color={color} />}
      <mesh>
        <sphereGeometry args={[0.4, 16, 16]} />
        <meshStandardMaterial
          color={color}
          transparent
          opacity={opacity}
          emissive={isSelected ? '#ffffff' : '#000000'}
          emissiveIntensity={isSelected ? 0.3 : 0}
        />
      </mesh>
      {isSelected && (
        <Html distanceFactor={10} center>
          <div className="bg-white rounded shadow px-2 py-1 text-xs whitespace-nowrap pointer-events-none border border-blue-400">
            <div className="font-semibold">{patient.name}</div>
            <div className="text-gray-500">{patient.severity} · {patient.diagnosis}</div>
          </div>
        </Html>
      )}
    </group>
  );
};

const DoctorMarker: React.FC<{
  doctor: Doctor;
  position: [number, number, number];
  isSelected: boolean;
  onClick: () => void;
}> = ({ doctor, position, isSelected, onClick }) => {
  const color = WORKLOAD_COLOR[doctor.workload] ?? '#6b7280';

  return (
    <group
      position={position}
      rotation={[0, Math.PI / 4, 0]}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
    >
      <mesh>
        <boxGeometry args={[0.55, 0.55, 0.55]} />
        <meshStandardMaterial
          color={color}
          emissive={isSelected ? '#ffffff' : '#000000'}
          emissiveIntensity={isSelected ? 0.3 : 0}
        />
      </mesh>
      {isSelected && (
        <Html distanceFactor={10} center>
          <div className="bg-white rounded shadow px-2 py-1 text-xs whitespace-nowrap pointer-events-none border border-blue-400">
            <div className="font-semibold">{doctor.name}</div>
            <div className="text-gray-500">{doctor.specialty} · {doctor.workload}</div>
          </div>
        </Html>
      )}
    </group>
  );
};

const HospitalModel: React.FC<{
  onBoundsReady: (bounds: THREE.Box3) => void;
}> = ({ onBoundsReady }) => {
  const { scene } = useGLTF('/hospital/scene.glb', true);
  const boundsReported = useRef(false);

  const cloned = useMemo(() => {
    const c = scene.clone(true);
    if (!boundsReported.current) {
      const box = new THREE.Box3().setFromObject(c);
      onBoundsReady(box);
      boundsReported.current = true;
    }
    return c;
  }, [scene, onBoundsReady]);

  return <primitive object={cloned} />;
};

const SceneContent: React.FC = () => {
  const { patients, doctors } = useSimulationStore();
  const { selectEntity, selectedEntityId } = useUIStore();
  const { camera } = useThree();
  const boundsRef = useRef<THREE.Box3 | null>(null);
  const [, forceUpdate] = React.useReducer((x) => x + 1, 0);

  const handleBoundsReady = React.useCallback((bounds: THREE.Box3) => {
    boundsRef.current = bounds;

    // Position camera to look down at the scene
    const size = new THREE.Vector3();
    bounds.getSize(size);
    const center = new THREE.Vector3();
    bounds.getCenter(center);
    const maxDim = Math.max(size.x, size.z);

    camera.position.set(center.x, center.y + maxDim, center.z -80);
    camera.lookAt(center);

    forceUpdate();
  }, [camera]);

  const bounds = boundsRef.current;

  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[10, 20, 10]} intensity={1.2} castShadow />
      <directionalLight position={[-10, 10, -10]} intensity={0.4} />

      <Suspense fallback={null}>
        <HospitalModel onBoundsReady={handleBoundsReady} />
      </Suspense>

      {bounds && patients.map((patient) => (
        <PatientMarker
          key={patient.id}
          patient={patient}
          position={gridToWorld(patient.grid_x, patient.grid_y, bounds)}
          isSelected={selectedEntityId === patient.id}
          onClick={() => selectEntity(patient.id, 'patient')}
        />
      ))}

      {bounds && doctors.map((doctor) => (
        <DoctorMarker
          key={doctor.id}
          doctor={doctor}
          position={gridToWorld(doctor.grid_x, doctor.grid_y, bounds)}
          isSelected={selectedEntityId === doctor.id}
          onClick={() => selectEntity(doctor.id, 'doctor')}
        />
      ))}

      <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
    </>
  );
};

const LoadingFallback: React.FC = () => (
  <div className="flex items-center justify-center w-full h-full bg-gray-100 rounded-xl">
    <div className="text-center space-y-2">
      <div className="w-8 h-8 border-4 border-blue-400 border-t-transparent rounded-full animate-spin mx-auto" />
      <p className="text-sm text-gray-500">Loading hospital scene…</p>
    </div>
  </div>
);

export const HospitalScene3D: React.FC = () => (
  <div className="relative w-full h-full min-h-[600px] bg-gray-900 rounded-xl border border-gray-200 shadow-inner overflow-hidden">
    <Suspense fallback={<LoadingFallback />}>
      <Canvas
        shadows
        gl={{ antialias: true }}
        camera={{ fov: 50, near: 0.1, far: 10000 }}
      >
        <SceneContent />
      </Canvas>
    </Suspense>
    <div className="absolute bottom-3 left-3 bg-white/80 backdrop-blur rounded-lg px-3 py-2 text-xs text-gray-600 space-y-0.5 pointer-events-none">
      <div className="flex items-center gap-2">
        <span className="w-3 h-3 rounded-full bg-green-500 inline-block" /> Low severity
      </div>
      <div className="flex items-center gap-2">
        <span className="w-3 h-3 rounded-full bg-amber-400 inline-block" /> Medium severity
      </div>
      <div className="flex items-center gap-2">
        <span className="w-3 h-3 rounded-full bg-red-500 inline-block" /> Critical
      </div>
      <div className="flex items-center gap-2">
        <span className="w-3 h-3 rounded bg-blue-500 inline-block" /> Doctor (light)
      </div>
      <div className="flex items-center gap-2">
        <span className="w-3 h-3 rounded bg-red-600 inline-block" /> Doctor (overwhelmed)
      </div>
    </div>
  </div>
);
