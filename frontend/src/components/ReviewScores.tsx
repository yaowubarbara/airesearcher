'use client';

import type { ReviewResult } from '@/lib/types';

interface Props {
  review: ReviewResult;
}

const scoreLabels: Record<string, string> = {
  originality: 'Originality',
  close_reading_depth: 'Close Reading',
  argument_coherence: 'Argument',
  citation_quality: 'Citations',
  style_match: 'Style Match',
  citation_sophistication: 'Citation Sophistication',
  quote_paraphrase_ratio: 'Quote/Paraphrase',
};

const recommendationColors: Record<string, string> = {
  accept: 'text-success bg-success/10 border-success/30',
  minor_revision: 'text-accent bg-accent/10 border-accent/30',
  major_revision: 'text-warning bg-warning/10 border-warning/30',
  reject: 'text-error bg-error/10 border-error/30',
};

export default function ReviewScores({ review }: Props) {
  const recLabel = review.overall_recommendation.replace('_', ' ').toUpperCase();
  const recClass = recommendationColors[review.overall_recommendation] || recommendationColors.major_revision;

  return (
    <div className="space-y-6">
      {/* Recommendation badge */}
      <div className={`inline-block px-4 py-2 rounded-lg border text-sm font-bold ${recClass}`}>
        {recLabel}
      </div>

      {/* Score bars */}
      <div className="bg-bg-card rounded-lg p-6 border border-slate-700 space-y-4">
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-2">Scores</h3>
        {Object.entries(review.scores).map(([key, val]) => (
          <div key={key}>
            <div className="flex justify-between mb-1">
              <span className="text-xs text-text-secondary">{scoreLabels[key] || key}</span>
              <span className="text-xs font-mono text-text-primary">{val}/5</span>
            </div>
            <div className="w-full bg-slate-700 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full ${val >= 4 ? 'bg-success' : val >= 3 ? 'bg-accent' : val >= 2 ? 'bg-warning' : 'bg-error'}`}
                style={{ width: `${(val / 5) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Comments */}
      {review.comments.length > 0 && (
        <div className="bg-bg-card rounded-lg p-6 border border-slate-700">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3">Comments</h3>
          <ul className="space-y-2">
            {review.comments.map((c, i) => (
              <li key={i} className="text-sm text-text-secondary flex gap-2">
                <span className="text-text-muted flex-shrink-0">&bull;</span>
                {c}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Revision instructions */}
      {review.revision_instructions.length > 0 && (
        <div className="bg-bg-card rounded-lg p-6 border border-slate-700">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3">
            Revision Instructions
          </h3>
          <ol className="space-y-2">
            {review.revision_instructions.map((r, i) => (
              <li key={i} className="text-sm text-text-secondary flex gap-2">
                <span className="text-accent font-mono flex-shrink-0">{i + 1}.</span>
                {r}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
