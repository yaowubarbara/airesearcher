'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import PlanOutline from '@/components/PlanOutline';
import TaskProgress from '@/components/TaskProgress';
import type { ResearchPlan } from '@/lib/types';

export default function PlanPage() {
  const router = useRouter();
  const {
    selectedTopicId, selectedJournal, currentPlanId,
    setPlanId, activeTaskId, setActiveTaskId, setStage,
  } = usePipelineStore();

  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setStage('plan');
    if (currentPlanId) {
      setLoading(true);
      api.getPlan(currentPlanId)
        .then((data) => setPlan(data))
        .catch(() => {})
        .finally(() => setLoading(false));
    }
  }, [setStage, currentPlanId]);

  const createPlan = async () => {
    if (!selectedTopicId || !selectedJournal) return;
    try {
      const { task_id } = await api.createPlan(selectedTopicId, selectedJournal);
      setActiveTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handlePlanComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    if (result?.id) {
      setPlanId(result.id);
      setPlan(result);
    }
  }, [setActiveTaskId, setPlanId]);

  const handleProceed = () => {
    if (currentPlanId) {
      router.push('/pipeline/write');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Research Plan</h2>
          <p className="text-sm text-text-secondary mt-1">
            Generate a detailed outline with thesis statement and section structure.
          </p>
        </div>
        {!plan && (
          <button
            onClick={createPlan}
            disabled={!!activeTaskId || !selectedTopicId}
            className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Create Plan
          </button>
        )}
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handlePlanComplete}
        label="Creating research plan..."
      />

      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : plan ? (
        <>
          <PlanOutline plan={plan} />
          <div className="flex justify-between pt-4 border-t border-slate-700">
            <button
              onClick={createPlan}
              disabled={!!activeTaskId}
              className="px-4 py-2 border border-slate-600 text-text-secondary text-sm rounded-lg hover:bg-bg-hover transition-colors"
            >
              Regenerate Plan
            </button>
            <button
              onClick={handleProceed}
              className="px-6 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
              Approve & Write
            </button>
          </div>
        </>
      ) : (
        <div className="text-center py-10">
          <p className="text-text-secondary">
            {selectedTopicId
              ? 'Click "Create Plan" to generate a research outline.'
              : 'Select a topic in the Discover stage first.'}
          </p>
        </div>
      )}
    </div>
  );
}
