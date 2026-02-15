'use client';

import type { Journal } from '@/lib/types';

interface Props {
  journal: Journal;
  onSelect: (name: string) => void;
}

const langFlags: Record<string, string> = {
  en: 'EN',
  zh: 'ZH',
  fr: 'FR',
};

export default function JournalCard({ journal, onSelect }: Props) {
  return (
    <button
      onClick={() => journal.is_active && onSelect(journal.name)}
      className={`relative text-left p-5 rounded-lg border transition-all ${
        journal.is_active
          ? 'bg-bg-card border-slate-700 hover:border-accent hover:shadow-lg hover:shadow-accent/5 cursor-pointer'
          : 'bg-bg-card/50 border-slate-700/50 cursor-not-allowed'
      }`}
      disabled={!journal.is_active}
    >
      {!journal.is_active && (
        <div className="absolute inset-0 bg-bg-primary/60 backdrop-blur-[1px] rounded-lg flex items-center justify-center z-10">
          <span className="bg-slate-700 text-text-secondary text-xs font-medium px-3 py-1 rounded-full">
            Coming Soon
          </span>
        </div>
      )}

      <div className="flex items-start justify-between mb-3">
        <h3 className="font-semibold text-text-primary text-sm leading-tight pr-2">
          {journal.name}
        </h3>
        <span className="text-[10px] font-mono bg-slate-700 text-text-secondary px-1.5 py-0.5 rounded flex-shrink-0">
          {langFlags[journal.language] || journal.language.toUpperCase()}
        </span>
      </div>

      <p className="text-xs text-text-muted mb-3">{journal.publisher}</p>
      <p className="text-xs text-text-secondary line-clamp-2">{journal.scope}</p>

      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-slate-700/50">
        <span className="text-[10px] bg-slate-700/50 text-text-muted px-2 py-0.5 rounded">
          {journal.citation_style}
        </span>
        {journal.issn && (
          <span className="text-[10px] text-text-muted">
            {journal.issn}
          </span>
        )}
      </div>
    </button>
  );
}
