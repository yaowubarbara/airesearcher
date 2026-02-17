'use client';

import { usePipelineStore, STAGE_ORDER, getStageName, getStageIndex, type PipelineStage } from '@/lib/store';

export default function StageIndicator() {
  const { currentStage, completedStages } = usePipelineStore();
  const currentIdx = getStageIndex(currentStage);

  return (
    <div className="flex items-center gap-1 overflow-x-auto pb-1">
      {STAGE_ORDER.map((stage, idx) => {
        const completed = completedStages.includes(stage);
        const isCurrent = stage === currentStage;

        return (
          <div key={stage} className="flex items-center">
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs whitespace-nowrap ${
              isCurrent
                ? 'bg-accent-light text-accent font-medium'
                : completed
                ? 'text-success'
                : 'text-text-muted'
            }`}>
              <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold ${
                completed
                  ? 'bg-success/20 text-success'
                  : isCurrent
                  ? 'bg-accent-light text-accent'
                  : 'bg-gray-100 text-text-muted'
              }`}>
                {completed ? '\u2713' : idx + 1}
              </span>
              {getStageName(stage)}
            </div>
            {idx < STAGE_ORDER.length - 1 && (
              <div className={`w-4 h-px mx-0.5 ${
                completed ? 'bg-success/40' : 'bg-gray-100'
              }`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
