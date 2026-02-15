'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { usePipelineStore } from '@/lib/store';

export default function RevisionPage() {
  const router = useRouter();
  const { reviewResult, currentManuscriptId, setStage, completeStage } = usePipelineStore();

  useEffect(() => {
    setStage('revision');
  }, [setStage]);

  const handleSkip = () => {
    completeStage('revision');
    router.push('/pipeline/submit');
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-text-primary">Revision</h2>
        <p className="text-sm text-text-secondary mt-1">
          Review the feedback and decide whether to revise the manuscript.
        </p>
      </div>

      {reviewResult && (
        <div className="bg-bg-card rounded-lg p-6 border border-slate-700">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3">
            Reviewer Recommendation
          </h3>
          <p className="text-lg font-bold text-warning mb-4">
            {reviewResult.overall_recommendation?.replace('_', ' ').toUpperCase()}
          </p>

          {reviewResult.revision_instructions?.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-text-primary">Required Changes</h4>
              <ol className="space-y-1.5">
                {reviewResult.revision_instructions.map((inst: string, i: number) => (
                  <li key={i} className="text-sm text-text-secondary flex gap-2">
                    <span className="text-accent font-mono flex-shrink-0">{i + 1}.</span>
                    {inst}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      <div className="bg-bg-card rounded-lg p-6 border border-slate-700">
        <p className="text-sm text-text-secondary mb-4">
          Automatic revision will re-run the writing agent with review feedback incorporated.
          This may take several minutes.
        </p>
        <div className="flex gap-3">
          <button
            disabled
            className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg opacity-50 cursor-not-allowed"
          >
            Auto-Revise (Coming Soon)
          </button>
          <button
            onClick={handleSkip}
            className="px-4 py-2 border border-slate-600 text-text-secondary text-sm rounded-lg hover:bg-bg-hover transition-colors"
          >
            Skip to Submission
          </button>
        </div>
      </div>
    </div>
  );
}
