'use client';

import type { ProblematiqueDirection, Topic } from '@/lib/types';
import TopicCard from './TopicCard';

interface Props {
  direction: ProblematiqueDirection;
  topics: Topic[];
  expanded: boolean;
  onToggle: () => void;
  selectedTopicId: string | null;
  onSelectTopic: (id: string) => void;
}

function Badge({ label, color }: { label: string; color: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}

export default function DirectionCard({
  direction,
  topics,
  expanded,
  onToggle,
  selectedTopicId,
  onSelectTopic,
}: Props) {
  return (
    <div className="rounded-lg border border-border bg-bg-card overflow-hidden">
      {/* Header */}
      <button
        onClick={onToggle}
        className="w-full text-left p-5 hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-text-primary text-base mb-1">
              {direction.title}
            </h3>
            <p className="text-sm text-text-secondary line-clamp-2">
              {direction.description}
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-text-muted shrink-0">
            <span>{direction.paper_ids.length} papers</span>
            {direction.recency_score != null && direction.recency_score > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 font-medium">
                {direction.recency_score.toFixed(2)}
              </span>
            )}
            <span>{topics.length} topics</span>
            <span className="text-lg">{expanded ? '\u25B4' : '\u25BE'}</span>
          </div>
        </div>

        {/* P-ontology badges */}
        <div className="flex flex-wrap gap-1.5 mt-3">
          {direction.dominant_tensions.map((t, i) => (
            <Badge key={`t-${i}`} label={t} color="bg-blue-50 text-blue-700" />
          ))}
          {direction.dominant_mediators.map((m, i) => (
            <Badge key={`m-${i}`} label={m} color="bg-purple-50 text-purple-700" />
          ))}
          {direction.dominant_scale && (
            <Badge label={direction.dominant_scale} color="bg-emerald-50 text-emerald-700" />
          )}
          {direction.dominant_gap && (
            <Badge
              label={direction.dominant_gap.replace(/_/g, ' ')}
              color="bg-amber-50 text-amber-700"
            />
          )}
        </div>
      </button>

      {/* Expanded: topic list */}
      {expanded && (
        <div className="border-t border-border p-4 space-y-2">
          {topics.length === 0 ? (
            <p className="text-sm text-text-muted text-center py-4">
              No topics generated yet.
            </p>
          ) : (
            topics.map((topic) => (
              <TopicCard
                key={topic.id}
                topic={topic}
                onSelect={onSelectTopic}
                selected={topic.id === selectedTopicId}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}
