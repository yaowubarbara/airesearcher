'use client';

import type { Journal } from '@/lib/types';

interface JournalCardProps {
  journal: Journal;
  onSelect: (name: string) => void;
}

const LANG_FLAGS: Record<string, string> = {
  en: '🇬🇧',
  zh: '🇨🇳',
  fr: '🇫🇷',
};

export default function JournalCard({ journal, onSelect }: JournalCardProps) {
  return (
    <button
      onClick={() => journal.is_active && onSelect(journal.name)}
      disabled={!journal.is_active}
      className={`
        p-4 rounded-lg border text-left transition-all duration-150
        ${journal.is_active
          ? 'border-border hover:border-accent hover:shadow-md cursor-pointer bg-bg-secondary'
          : 'border-border/50 opacity-50 cursor-not-allowed bg-bg-tertiary'
        }
      `}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-base">{LANG_FLAGS[journal.language] || '🌐'}</span>
        <h3 className="font-medium text-text-primary text-sm truncate">{journal.name}</h3>
      </div>
      <p className="text-text-tertiary text-xs truncate">{journal.publisher}</p>
      <p className="text-text-tertiary text-xs mt-1 line-clamp-2">{journal.scope}</p>
      {journal.is_active ? (
        <span className="inline-block mt-2 px-2 py-0.5 text-xs rounded-full bg-accent/10 text-accent">
          Active
        </span>
      ) : (
        <span className="inline-block mt-2 px-2 py-0.5 text-xs rounded-full bg-bg-tertiary text-text-tertiary">
          Coming Soon
        </span>
      )}
    </button>
  );
}
