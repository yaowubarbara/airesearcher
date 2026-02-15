import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type PipelineStage =
  | 'journal'
  | 'discover'
  | 'references'
  | 'plan'
  | 'write'
  | 'review'
  | 'revision'
  | 'submit';

interface PipelineState {
  // Current stage
  currentStage: PipelineStage;
  setStage: (stage: PipelineStage) => void;

  // Selections
  selectedJournal: string | null;
  selectJournal: (name: string) => void;

  selectedTopicId: string | null;
  selectTopic: (id: string) => void;

  currentPlanId: string | null;
  setPlanId: (id: string) => void;

  currentManuscriptId: string | null;
  setManuscriptId: (id: string) => void;

  reviewResult: any | null;
  setReviewResult: (result: any) => void;

  // Task tracking
  activeTaskId: string | null;
  setActiveTaskId: (id: string | null) => void;

  // Stage unlocking
  completedStages: PipelineStage[];
  completeStage: (stage: PipelineStage) => void;
  isStageUnlocked: (stage: PipelineStage) => boolean;

  // Reset
  resetPipeline: () => void;
}

const STAGE_ORDER: PipelineStage[] = [
  'journal', 'discover', 'references', 'plan', 'write', 'review', 'revision', 'submit',
];

function addUnique(arr: PipelineStage[], item: PipelineStage): PipelineStage[] {
  return arr.includes(item) ? arr : [...arr, item];
}

const initialState = {
  currentStage: 'journal' as PipelineStage,
  selectedJournal: null,
  selectedTopicId: null,
  currentPlanId: null,
  currentManuscriptId: null,
  reviewResult: null,
  activeTaskId: null,
  completedStages: [] as PipelineStage[],
};

export const usePipelineStore = create<PipelineState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setStage: (stage) => set({ currentStage: stage }),

      selectJournal: (name) =>
        set({
          selectedJournal: name,
          currentStage: 'discover',
          completedStages: addUnique(get().completedStages, 'journal'),
        }),

      selectTopic: (id) =>
        set({
          selectedTopicId: id,
          completedStages: addUnique(get().completedStages, 'discover'),
        }),

      setPlanId: (id) =>
        set({
          currentPlanId: id,
          completedStages: addUnique(get().completedStages, 'plan'),
        }),

      setManuscriptId: (id) =>
        set({
          currentManuscriptId: id,
          completedStages: addUnique(get().completedStages, 'write'),
        }),

      setReviewResult: (result) =>
        set({
          reviewResult: result,
          completedStages: addUnique(get().completedStages, 'review'),
        }),

      setActiveTaskId: (id) => set({ activeTaskId: id }),

      completeStage: (stage) =>
        set({
          completedStages: addUnique(get().completedStages, stage),
        }),

      isStageUnlocked: (stage) => {
        const { completedStages, selectedJournal } = get();
        if (stage === 'journal') return true;
        if (stage === 'discover') return !!selectedJournal;
        if (stage === 'references') return completedStages.includes('discover');
        if (stage === 'plan') return completedStages.includes('discover');
        if (stage === 'write') return completedStages.includes('plan');
        if (stage === 'review') return completedStages.includes('write');
        if (stage === 'revision') return completedStages.includes('review');
        if (stage === 'submit') return completedStages.includes('review');
        return false;
      },

      resetPipeline: () => set(initialState),
    }),
    { name: 'ai-researcher-pipeline' }
  )
);

export function getStageName(stage: PipelineStage): string {
  const names: Record<PipelineStage, string> = {
    journal: 'Journal',
    discover: 'Discover',
    references: 'References',
    plan: 'Plan',
    write: 'Write',
    review: 'Review',
    revision: 'Revision',
    submit: 'Submit',
  };
  return names[stage];
}

export function getStageIndex(stage: PipelineStage): number {
  return STAGE_ORDER.indexOf(stage);
}

export { STAGE_ORDER };
