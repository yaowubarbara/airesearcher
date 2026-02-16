'use client';

import type { TheorySupplementResult, TheoryItem } from '@/lib/types';

interface Props {
  result: TheorySupplementResult;
}

function getStatusBadge(item: TheoryItem) {
  if (item.has_full_text) {
    return { label: 'Indexed', color: 'text-success bg-success/10' };
  }
  if (item.already_in_db) {
    return { label: 'In DB', color: 'text-success bg-success/10' };
  }
  if (item.verified) {
    return { label: 'Verified', color: 'text-amber-400 bg-amber-400/10' };
  }
  return { label: 'LLM only', color: 'text-text-muted bg-slate-700/50' };
}

function getSourceLabel(source: string) {
  switch (source) {
    case 'crossref':
      return 'CrossRef';
    case 'openalex':
      return 'OpenAlex';
    case 'llm_only':
      return 'LLM';
    default:
      return source;
  }
}

export default function TheoryPanel({ result }: Props) {
  if (!result || result.items.length === 0) {
    return null;
  }

  return (
    <div className="bg-bg-card rounded-lg border border-slate-700 overflow-hidden">
      <div className="p-4 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-medium text-text-primary">Theoretical Framework</h4>
          <div className="flex items-center gap-3 text-xs text-text-muted">
            <span>{result.verified} verified</span>
            <span>{result.inserted} added</span>
            {result.already_present > 0 && (
              <span>{result.already_present} already present</span>
            )}
          </div>
        </div>
      </div>

      <div className="divide-y divide-slate-700/50">
        {result.items.map((item, i) => {
          const badge = getStatusBadge(item);
          return (
            <div key={i} className="px-4 py-3 flex items-start gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-text-primary font-medium truncate">
                    {item.author}
                  </span>
                  {item.year && (
                    <span className="text-xs text-text-muted flex-shrink-0">({item.year})</span>
                  )}
                </div>
                <p className="text-xs text-text-secondary italic mt-0.5 truncate">{item.title}</p>
                {item.relevance && (
                  <p className="text-[11px] text-text-muted mt-1">{item.relevance}</p>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-[10px] text-text-muted">{getSourceLabel(item.source)}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${badge.color}`}>
                  {badge.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {result.items.some((i) => i.source === 'llm_only') && (
        <div className="px-4 py-2 bg-slate-800/50 border-t border-slate-700">
          <p className="text-[10px] text-text-muted">
            Works marked "LLM only" could not be verified via CrossRef/OpenAlex.
            Bibliographic details should be confirmed manually.
          </p>
        </div>
      )}
    </div>
  );
}
