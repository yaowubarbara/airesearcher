'use client';

import type { Domain } from '@/lib/types';

const ICONS: Record<string, string> = {
  'book-open': '📚',
  'cpu': '💻',
  'heart-pulse': '🔬',
};

interface DomainCardProps {
  domain: Domain;
  selected: boolean;
  onSelect: (domainId: string) => void;
}

export default function DomainCard({ domain, selected, onSelect }: DomainCardProps) {
  return (
    <button
      onClick={() => onSelect(domain.domain_id)}
      className={`
        group relative p-6 rounded-xl border-2 text-left transition-all duration-200
        hover:shadow-lg hover:-translate-y-0.5
        ${selected
          ? 'border-accent bg-accent/5 shadow-md'
          : 'border-border bg-bg-secondary hover:border-accent/50'
        }
      `}
    >
      <div className="flex items-start gap-4">
        <div
          className="w-12 h-12 rounded-lg flex items-center justify-center text-2xl"
          style={{ backgroundColor: `${domain.color}15` }}
        >
          {ICONS[domain.icon] || '🔍'}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-text-primary text-lg mb-1">
            {domain.name}
          </h3>
          <p className="text-text-secondary text-sm leading-relaxed line-clamp-2">
            {domain.description}
          </p>
          <div className="mt-3 flex items-center gap-2 text-xs text-text-tertiary">
            <span className="px-2 py-0.5 rounded-full bg-bg-tertiary">
              {domain.journal_count} journals
            </span>
          </div>
        </div>
      </div>
      {selected && (
        <div
          className="absolute top-3 right-3 w-5 h-5 rounded-full flex items-center justify-center"
          style={{ backgroundColor: domain.color }}
        >
          <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
          </svg>
        </div>
      )}
    </button>
  );
}
