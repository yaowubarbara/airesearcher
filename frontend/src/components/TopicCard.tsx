'use client';

import type { Topic } from '@/lib/types';

interface Props {
  topic: Topic;
  onSelect: (id: string) => void;
  selected?: boolean;
}

export default function TopicCard({ topic, onSelect, selected }: Props) {
  return (
    <button
      onClick={() => onSelect(topic.id)}
      className={`text-left w-full p-5 rounded-lg border transition-all ${
        selected
          ? 'bg-accent/10 border-accent'
          : 'bg-bg-card border-slate-700 hover:border-slate-600'
      }`}
    >
      <h3 className="font-semibold text-text-primary text-sm mb-2">{topic.title}</h3>
      <p className="text-xs text-text-secondary mb-3 line-clamp-2">
        {topic.research_question}
      </p>
      <p className="text-xs text-text-muted mb-3 line-clamp-2">{topic.gap_description}</p>

      <div className="flex items-center gap-3 text-xs">
        <ScoreBadge label="Overall" value={topic.overall_score} />
        <ScoreBadge label="Novelty" value={topic.novelty_score} />
        <ScoreBadge label="Feasibility" value={topic.feasibility_score} />
        <ScoreBadge label="Fit" value={topic.journal_fit_score} />
      </div>
    </button>
  );
}

function ScoreBadge({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? 'text-success' : pct >= 40 ? 'text-warning' : 'text-error';
  return (
    <span className="flex items-center gap-1">
      <span className="text-text-muted">{label}</span>
      <span className={`font-mono font-bold ${color}`}>{pct}</span>
    </span>
  );
}
