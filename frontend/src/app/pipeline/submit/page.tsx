'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import TaskProgress from '@/components/TaskProgress';

export default function SubmitPage() {
  const {
    currentManuscriptId, activeTaskId, setActiveTaskId,
    setStage, completeStage,
  } = usePipelineStore();

  const [submission, setSubmission] = useState<{ formatted_manuscript: string; cover_letter: string } | null>(null);

  useEffect(() => {
    setStage('submit');
  }, [setStage]);

  const formatSubmission = async () => {
    if (!currentManuscriptId) return;
    try {
      const { task_id } = await api.formatSubmission(currentManuscriptId);
      setActiveTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    setSubmission(result);
    completeStage('submit');
  }, [setActiveTaskId, completeStage]);

  const downloadText = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Submission</h2>
          <p className="text-sm text-text-secondary mt-1">
            Format the manuscript and generate a cover letter.
          </p>
        </div>
        {!submission && (
          <button
            onClick={formatSubmission}
            disabled={!!activeTaskId || !currentManuscriptId}
            className="px-4 py-2 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Format for Submission
          </button>
        )}
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handleComplete}
        label="Formatting submission package..."
      />

      {submission && (
        <>
          {/* Cover Letter */}
          <div className="bg-bg-card rounded-lg p-6 border border-border">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">Cover Letter</h3>
              <button
                onClick={() => downloadText(submission.cover_letter, 'cover_letter.txt')}
                className="text-xs text-accent hover:underline"
              >
                Download
              </button>
            </div>
            <div className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto">
              {submission.cover_letter}
            </div>
          </div>

          {/* Formatted Manuscript */}
          <div className="bg-bg-card rounded-lg p-6 border border-border">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">Formatted Manuscript</h3>
              <button
                onClick={() => downloadText(submission.formatted_manuscript, 'manuscript.md')}
                className="text-xs text-accent hover:underline"
              >
                Download
              </button>
            </div>
            <div className="text-sm text-text-secondary whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
              {submission.formatted_manuscript}
            </div>
          </div>

          <div className="bg-success/10 border border-success/30 rounded-lg p-5 text-center">
            <p className="text-success font-medium">Submission package ready!</p>
            <p className="text-sm text-text-secondary mt-1">
              Download the formatted manuscript and cover letter for submission.
            </p>
          </div>
        </>
      )}

      {!submission && !activeTaskId && (
        <div className="text-center py-10">
          <p className="text-text-secondary">
            {currentManuscriptId
              ? 'Click "Format for Submission" to prepare the final package.'
              : 'Complete the writing and review stages first.'}
          </p>
        </div>
      )}
    </div>
  );
}
