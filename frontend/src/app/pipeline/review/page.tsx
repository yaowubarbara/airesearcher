'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import ReviewScores from '@/components/ReviewScores';
import TaskProgress from '@/components/TaskProgress';
import type { ReviewResult } from '@/lib/types';

export default function ReviewPage() {
  const router = useRouter();
  const {
    currentManuscriptId, reviewResult,
    setReviewResult, activeTaskId, setActiveTaskId, setStage,
  } = usePipelineStore();

  const [review, setReview] = useState<ReviewResult | null>(reviewResult);

  useEffect(() => {
    setStage('review');
  }, [setStage]);

  const startReview = async () => {
    if (!currentManuscriptId) return;
    try {
      const { task_id } = await api.startReview(currentManuscriptId);
      setActiveTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleReviewComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    setReview(result);
    setReviewResult(result);
  }, [setActiveTaskId, setReviewResult]);

  const handleProceed = () => {
    if (review?.overall_recommendation === 'accept') {
      router.push('/pipeline/submit');
    } else {
      router.push('/pipeline/revision');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Self-Review</h2>
          <p className="text-sm text-text-secondary mt-1">
            Multi-agent debate: 3 reviewers + meta-reviewer evaluate the manuscript.
          </p>
        </div>
        {!review && (
          <button
            onClick={startReview}
            disabled={!!activeTaskId || !currentManuscriptId}
            className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Start Review
          </button>
        )}
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handleReviewComplete}
        label="Running multi-agent review..."
      />

      {review ? (
        <>
          <ReviewScores review={review} />
          <div className="flex justify-between pt-4 border-t border-slate-700">
            <button
              onClick={() => { setReview(null); startReview(); }}
              disabled={!!activeTaskId}
              className="px-4 py-2 border border-slate-600 text-text-secondary text-sm rounded-lg hover:bg-bg-hover transition-colors"
            >
              Re-review
            </button>
            <button
              onClick={handleProceed}
              className="px-6 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
              {review.overall_recommendation === 'accept'
                ? 'Proceed to Submit'
                : 'Proceed to Revision'}
            </button>
          </div>
        </>
      ) : (
        <div className="text-center py-10">
          <p className="text-text-secondary">
            {currentManuscriptId
              ? 'Click "Start Review" to begin multi-agent evaluation.'
              : 'Generate a manuscript first.'}
          </p>
        </div>
      )}
    </div>
  );
}
