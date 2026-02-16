'use client';

import { useState } from 'react';
import type { SynthesizedTopic } from '@/lib/types';

interface TopicEditorProps {
  initialTopic: SynthesizedTopic;
  onConfirm: (edited: SynthesizedTopic) => void;
  onBack: () => void;
  loading?: boolean;
}

export default function TopicEditor({ initialTopic, onConfirm, onBack, loading }: TopicEditorProps) {
  const [title, setTitle] = useState(initialTopic.title);
  const [researchQuestion, setResearchQuestion] = useState(initialTopic.research_question);
  const [gapDescription, setGapDescription] = useState(initialTopic.gap_description);

  const isEdited =
    title !== initialTopic.title ||
    researchQuestion !== initialTopic.research_question ||
    gapDescription !== initialTopic.gap_description;

  const canConfirm = title.trim().length > 0 && researchQuestion.trim().length > 0;

  const handleConfirm = () => {
    onConfirm({
      title: title.trim(),
      research_question: researchQuestion.trim(),
      gap_description: gapDescription.trim(),
      source_paper_ids: initialTopic.source_paper_ids,
    });
  };

  return (
    <div className="bg-bg-card rounded-lg border border-slate-700">
      <div className="px-5 py-4 border-b border-slate-700 flex items-center gap-3">
        <h3 className="text-sm font-semibold text-text-primary">Review &amp; Edit Topic</h3>
        {isEdited && (
          <span className="text-[10px] bg-accent/15 text-accent px-1.5 py-0.5 rounded font-medium">
            edited
          </span>
        )}
      </div>

      <div className="p-5 space-y-4">
        <div>
          <label className="block text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">
            Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={loading}
            className="w-full px-3 py-2 bg-bg-primary border border-slate-600 rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent disabled:opacity-50"
            placeholder="Research topic title"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">
            Research Question
          </label>
          <textarea
            value={researchQuestion}
            onChange={(e) => setResearchQuestion(e.target.value)}
            disabled={loading}
            rows={3}
            className="w-full px-3 py-2 bg-bg-primary border border-slate-600 rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent disabled:opacity-50 resize-y"
            placeholder="What is the central research question?"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">
            Gap Description
          </label>
          <textarea
            value={gapDescription}
            onChange={(e) => setGapDescription(e.target.value)}
            disabled={loading}
            rows={3}
            className="w-full px-3 py-2 bg-bg-primary border border-slate-600 rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent disabled:opacity-50 resize-y"
            placeholder="What gap in the literature does this address?"
          />
        </div>
      </div>

      <div className="px-5 py-4 border-t border-slate-700 flex items-center justify-between">
        <button
          onClick={onBack}
          disabled={loading}
          className="px-4 py-2 border border-slate-600 text-text-secondary text-sm rounded-lg hover:bg-bg-hover transition-colors disabled:opacity-50"
        >
          Back
        </button>
        <button
          onClick={handleConfirm}
          disabled={loading || !canConfirm}
          className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {loading && (
            <span className="w-3.5 h-3.5 border-2 border-bg-primary border-t-transparent rounded-full animate-spin" />
          )}
          Confirm &amp; Generate Plan
        </button>
      </div>
    </div>
  );
}
