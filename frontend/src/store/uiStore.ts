import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type GraphPreset = 'overview' | 'surge' | 'capacity';

interface UIStore {
  selectedEntityId: number | null;
  selectedEntityType: 'patient' | 'doctor' | null;
  explanationText: string | null;
  explanationLoading: boolean;
  isPanelOpen: boolean;
  isSurgeActive: boolean;

  // Graph overlay state
  graphsOpen: boolean;
  activePreset: GraphPreset;

  selectEntity: (id: number, type: 'patient' | 'doctor') => void;
  clearSelection: () => void;
  setExplanation: (text: string | null) => void;
  setExplanationLoading: (v: boolean) => void;
  setSurgeActive: (v: boolean) => void;

  // Graph overlay actions
  openGraph: () => void;
  closeGraph: () => void;
  toggleGraphs: () => void;
  setPreset: (preset: GraphPreset) => void;
}

export const useUIStore = create<UIStore>()(
  persist(
    (set) => ({
      selectedEntityId: null,
      selectedEntityType: null,
      explanationText: null,
      explanationLoading: false,
      isPanelOpen: false,
      isSurgeActive: false,

      graphsOpen: false,
      activePreset: 'overview',

      selectEntity: (id, type) => set({
        selectedEntityId: id,
        selectedEntityType: type,
        isPanelOpen: true,
        explanationText: null,
      }),
      clearSelection: () => set({
        selectedEntityId: null,
        selectedEntityType: null,
        isPanelOpen: false,
        explanationText: null,
      }),
      setExplanation: (text) => set({ explanationText: text, explanationLoading: false }),
      setExplanationLoading: (v) => set({ explanationLoading: v }),
      setSurgeActive: (v) => set({ isSurgeActive: v }),

      openGraph: () => set({ graphsOpen: true }),
      closeGraph: () => set({ graphsOpen: false }),
      toggleGraphs: () => set((s) => ({ graphsOpen: !s.graphsOpen })),
      setPreset: (preset) => set({ activePreset: preset }),
    }),
    {
      name: 'hospital-sim-ui',
      partialize: (state) => ({
        graphsOpen: state.graphsOpen,
        activePreset: state.activePreset,
      }),
    }
  )
);
