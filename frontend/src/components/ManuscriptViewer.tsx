'use client';

import type { Manuscript } from '@/lib/types';

interface Props {
  manuscript: Manuscript;
}

export default function ManuscriptViewer({ manuscript }: Props) {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-bg-card rounded-lg p-6 border border-border">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-text-primary">{manuscript.title}</h2>
            <p className="text-sm text-text-secondary mt-1">{manuscript.target_journal}</p>
          </div>
          <div className="text-right flex-shrink-0 ml-4">
            <span className="text-sm font-mono text-accent">{manuscript.word_count.toLocaleString()} words</span>
            <p className="text-xs text-text-muted">v{manuscript.version}</p>
          </div>
        </div>

        {manuscript.keywords.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {manuscript.keywords.map((kw, i) => (
              <span key={i} className="text-[10px] bg-gray-100 text-text-secondary px-2 py-0.5 rounded">
                {kw}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Abstract */}
      {manuscript.abstract && (
        <div className="bg-bg-card rounded-lg p-6 border border-border">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3">Abstract</h3>
          <p className="text-sm text-text-secondary leading-relaxed">{manuscript.abstract}</p>
        </div>
      )}

      {/* Sections */}
      <div className="bg-bg-card rounded-lg p-6 border border-border">
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">Manuscript</h3>
        {manuscript.full_text ? (
          <div
            className="prose-manuscript text-sm text-text-primary leading-relaxed whitespace-pre-wrap"
          >
            {manuscript.full_text}
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(manuscript.sections).map(([title, content]) => (
              <div key={title}>
                <h4 className="text-sm font-semibold text-text-primary mb-2">{title}</h4>
                <div className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
                  {content}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
