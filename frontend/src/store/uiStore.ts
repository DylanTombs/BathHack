import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type GraphPreset = 'overview' | 'surge' | 'capacity';
export type RightPanelTab = 'metrics' | 'events';

interface UIStore {
  selectedEntityId: number | null;
  selectedEntityType: 'patient' | 'doctor' | null;
  explanationText: string | null;
  explanationLoading: boolean;
  isPanelOpen: boolean;
  isSurgeActive: boolean;

  // Right panel state
  rightPanelTab: RightPanelTab;
  activePreset: GraphPreset;

  // Panel visibility
  leftPanelVisible: boolean;
  rightPanelVisible: boolean;

  selectEntity: (id: number, type: 'patient' | 'doctor') => void;
  clearSelection: () => void;
  setExplanation: (text: string | null) => void;
  setExplanationLoading: (v: boolean) => void;
  setSurgeActive: (v: boolean) => void;
  setRightPanelTab: (tab: RightPanelTab) => void;
  setPreset: (preset: GraphPreset) => void;
  toggleLeftPanel: () => void;
  toggleRightPanel: () => void;
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

      rightPanelTab: 'metrics',
      activePreset: 'overview',
      leftPanelVisible: true,
      rightPanelVisible: true,

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
      setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
      setPreset: (preset) => set({ activePreset: preset }),
      toggleLeftPanel: () => set((s) => ({ leftPanelVisible: !s.leftPanelVisible })),
      toggleRightPanel: () => set((s) => ({ rightPanelVisible: !s.rightPanelVisible })),
    }),
    {
      name: 'hospital-sim-ui',
      partialize: (state) => ({
        rightPanelTab: state.rightPanelTab,
        activePreset: state.activePreset,
      }),
    }
  )
);
