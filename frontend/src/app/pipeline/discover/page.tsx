'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import TopicCard from '@/components/TopicCard';
import TaskProgress from '@/components/TaskProgress';
import type { Topic } from '@/lib/types';

export default function DiscoverPage() {
  const router = useRouter();
  const {
    selectedJournal, selectedTopicId, selectTopic,
    activeTaskId, setActiveTaskId, setStage, completeStage,
  } = usePipelineStore();

  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setStage('discover');
    api.getTopics(undefined, 50)
      .then((data) => setTopics(data.topics))
      .catch(() => {})
      .finally(() => setLoading(false));
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

  const handleDiscoveryComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    if (Array.isArray(result)) {
      setTopics(prev => {
        const existingIds = new Set(prev.map(t => t.id));
        const newTopics = result.filter((t: Topic) => !existingIds.has(t.id));
        return [...newTopics, ...prev];
      });
    }
  }, [setActiveTaskId]);

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
            Discover research gaps and select a topic for {selectedJournal || 'your target journal'}.
          </p>
        </div>
        <button
          onClick={startDiscovery}
          disabled={!!activeTaskId || !selectedJournal}
          className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Run Discovery
        </button>
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handleDiscoveryComplete}
        label="Discovering research gaps..."
      />

      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : topics.length === 0 ? (
        <div className="text-center py-10">
          <p className="text-text-secondary">No topics yet. Click "Run Discovery" to find research gaps.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {topics.map((topic) => (
            <TopicCard
              key={topic.id}
              topic={topic}
              onSelect={handleTopicSelect}
              selected={topic.id === selectedTopicId}
            />
          ))}
        </div>
      )}

      {selectedTopicId && (
        <div className="flex justify-end pt-4 border-t border-slate-700">
          <button
            onClick={handleProceed}
            className="px-6 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
          >
            Continue to References
          </button>
        </div>
      )}
    </div>
  );
}
