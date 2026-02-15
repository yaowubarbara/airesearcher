'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import ManuscriptViewer from '@/components/ManuscriptViewer';
import TaskProgress from '@/components/TaskProgress';
import type { Manuscript } from '@/lib/types';

export default function WritePage() {
  const router = useRouter();
  const {
    currentPlanId, currentManuscriptId,
    setManuscriptId, activeTaskId, setActiveTaskId, setStage,
  } = usePipelineStore();

  const [manuscript, setManuscript] = useState<Manuscript | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setStage('write');
    if (currentManuscriptId) {
      setLoading(true);
      api.getManuscript(currentManuscriptId)
        .then((data) => setManuscript(data))
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [setStage, currentManuscriptId]);

  const startWriting = async () => {
    if (!currentPlanId) return;
    try {
      const { task_id } = await api.startWriting(currentPlanId);
      setActiveTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleWriteComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    if (result?.id) {
      setManuscriptId(result.id);
      setManuscript(result);
    }
  }, [setActiveTaskId, setManuscriptId]);

  const handleProceed = () => {
    if (currentManuscriptId) {
      router.push('/pipeline/review');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Manuscript Generation</h2>
          <p className="text-sm text-text-secondary mt-1">
            AI writes the manuscript with Self-Refine iteration.
          </p>
        </div>
        {!manuscript && (
          <button
            onClick={startWriting}
            disabled={!!activeTaskId || !currentPlanId}
            className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Start Writing
          </button>
        )}
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handleWriteComplete}
        label="Writing manuscript..."
      />

      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : manuscript ? (
        <>
          <ManuscriptViewer manuscript={manuscript} />
          <div className="flex justify-end pt-4 border-t border-slate-700">
            <button
              onClick={handleProceed}
              className="px-6 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
              Continue to Review
            </button>
          </div>
        </>
      ) : (
        <div className="text-center py-10">
          <p className="text-text-secondary">
            {currentPlanId
              ? 'Click "Start Writing" to generate the manuscript.'
              : 'Create a research plan first.'}
          </p>
        </div>
      )}
    </div>
  );
}
