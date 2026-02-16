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
      className={`text-left w-full p-4 rounded-lg border transition-all ${
        selected
          ? 'bg-accent/10 border-accent'
          : 'bg-bg-card border-slate-700 hover:border-slate-600'
      }`}
    >
      <h3 className="font-semibold text-text-primary text-sm mb-1">{topic.title}</h3>
      <p className="text-xs text-text-secondary mb-2 line-clamp-2">
        {topic.research_question}
      </p>
      <p className="text-xs text-text-muted line-clamp-2">{topic.gap_description}</p>
    </button>
  );
}
