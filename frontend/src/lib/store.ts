import { create } from 'zustand';

interface PipelineState {
  // Domain selection
  selectedDomain: string;
  selectDomain: (domain: string) => void;

  // Journal selection
  selectedJournal: string | null;
  selectJournal: (journal: string) => void;

  // Pipeline state
  currentStep: string;
  setStep: (step: string) => void;

  // Reset
  resetPipeline: () => void;
}

export const usePipelineStore = create<PipelineState>((set) => ({
  selectedDomain: 'comparative_literature',
  selectDomain: (domain) => set({ selectedDomain: domain, selectedJournal: null }),

  selectedJournal: null,
  selectJournal: (journal) => set({ selectedJournal: journal }),

  currentStep: 'discover',
  setStep: (step) => set({ currentStep: step }),

  resetPipeline: () =>
    set({
      selectedJournal: null,
      currentStep: 'discover',
    }),
}));
