import { create } from 'zustand';

interface UIStore {
  selectedEntityId: number | null;
  selectedEntityType: 'patient' | 'doctor' | null;
  explanationText: string | null;
  explanationLoading: boolean;
  isPanelOpen: boolean;
  isSurgeActive: boolean;

  selectEntity: (id: number, type: 'patient' | 'doctor') => void;
  clearSelection: () => void;
  setExplanation: (text: string | null) => void;
  setExplanationLoading: (v: boolean) => void;
  setSurgeActive: (v: boolean) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  selectedEntityId: null,
  selectedEntityType: null,
  explanationText: null,
  explanationLoading: false,
  isPanelOpen: false,
  isSurgeActive: false,

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
}));
