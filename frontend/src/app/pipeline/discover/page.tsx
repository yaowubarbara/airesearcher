'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import DirectionCard from '@/components/DirectionCard';
import TaskProgress from '@/components/TaskProgress';
import CorpusStudiedPanel from '@/components/CorpusStudiedPanel';
import type { ProblematiqueDirection, Topic, AnnotationStatus, DirectionWithTopics } from '@/lib/types';

interface DirectionState {
  direction: ProblematiqueDirection;
  topics: Topic[];
}

export default function DiscoverPage() {
  const router = useRouter();
  const {
    selectedJournal, selectedTopicId, selectTopic,
    activeTaskId, setActiveTaskId, setStage, completeStage,
  } = usePipelineStore();

  const [directions, setDirections] = useState<DirectionState[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [annotationStatus, setAnnotationStatus] = useState<AnnotationStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // Load existing directions on mount
  useEffect(() => {
    setStage('discover');

    const loadDirections = async () => {
      try {
        const [dirRes, statusRes] = await Promise.all([
          api.getDirections(20),
          api.getAnnotationStatus(),
        ]);
        setAnnotationStatus(statusRes);

        // Fetch topics for each direction
        const withTopics: DirectionState[] = await Promise.all(
          dirRes.directions.map(async (d) => {
            try {
              const dt = await api.getDirectionWithTopics(d.id);
              return { direction: dt.direction, topics: dt.topics };
            } catch {
              return { direction: d, topics: [] };
            }
          })
        );
        setDirections(withTopics);
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };

    loadDirections();
  }, [setStage]);

  const startDiscovery = async () => {
    if (!selectedJournal) return;
    try {
      const { task_id } = await api.startDiscovery(selectedJournal);
      setActiveTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleDiscoveryComplete = useCallback(async (result: any) => {
    setActiveTaskId(null);
    // Reload directions from API
    try {
      const dirRes = await api.getDirections(20);
      const statusRes = await api.getAnnotationStatus();
      setAnnotationStatus(statusRes);

      const withTopics: DirectionState[] = await Promise.all(
        dirRes.directions.map(async (d) => {
          try {
            const dt = await api.getDirectionWithTopics(d.id);
            return { direction: dt.direction, topics: dt.topics };
          } catch {
            return { direction: d, topics: [] };
          }
        })
      );
      setDirections(withTopics);
    } catch {
      // ignore
    }
  }, [setActiveTaskId]);

  const handleToggleDirection = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const handleTopicSelect = (id: string) => {
    selectTopic(id);
  };

  const handleProceed = () => {
    if (selectedTopicId) {
      completeStage('discover');
      router.push('/pipeline/references');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Topic Discovery</h2>
          <p className="text-sm text-text-secondary mt-1">
            Annotate papers, discover research directions, and select a topic for{' '}
            {selectedJournal || 'your target journal'}.
          </p>
        </div>
        <button
          onClick={startDiscovery}
          disabled={!!activeTaskId || !selectedJournal}
          className="px-4 py-2 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Run Discovery
        </button>
      </div>

      {/* Annotation status bar */}
      {annotationStatus && (
        <div className="flex items-center gap-4 text-xs text-text-muted bg-gray-50 rounded-lg px-4 py-2.5">
          <span>{annotationStatus.annotated} annotated</span>
          <span className="text-border-strong">|</span>
          <span>{annotationStatus.papers_with_abstract} with abstracts</span>
          <span className="text-border-strong">|</span>
          <span>{annotationStatus.directions} directions</span>
          <span className="text-border-strong">|</span>
          <span>{annotationStatus.topics} topics</span>
        </div>
      )}

      <CorpusStudiedPanel />

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handleDiscoveryComplete}
        label="Running P-ontology discovery..."
      />

      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : directions.length === 0 ? (
        <div className="text-center py-10">
          <p className="text-text-secondary">
            No directions yet. Click &quot;Run Discovery&quot; to annotate papers and find research directions.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {directions.map(({ direction, topics }) => (
            <DirectionCard
              key={direction.id}
              direction={direction}
              topics={topics}
              expanded={expandedId === direction.id}
              onToggle={() => handleToggleDirection(direction.id)}
              selectedTopicId={selectedTopicId}
              onSelectTopic={handleTopicSelect}
            />
          ))}
        </div>
      )}

      {selectedTopicId && (
        <div className="flex justify-end pt-4 border-t border-border">
          <button
            onClick={handleProceed}
            className="px-6 py-2.5 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
          >
            Continue to References
          </button>
        </div>
      )}
    </div>
  );
}
