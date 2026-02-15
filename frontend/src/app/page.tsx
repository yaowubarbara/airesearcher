'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import JournalCard from '@/components/JournalCard';
import type { Journal } from '@/lib/types';

export default function HomePage() {
  const [journals, setJournals] = useState<Journal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { selectJournal, resetPipeline } = usePipelineStore();

  useEffect(() => {
    api.getJournals()
      .then((data) => {
        // Sort: active first, then alphabetical
        const sorted = data.journals.sort((a, b) => {
          if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
          return a.name.localeCompare(b.name);
        });
        setJournals(sorted);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = (name: string) => {
    resetPipeline();
    selectJournal(name);
    router.push('/pipeline/discover');
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-text-primary mb-2">Select Target Journal</h1>
        <p className="text-text-secondary text-sm">
          Choose a journal to begin the research pipeline. Active journals have full support;
          others will be added in future releases.
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {error && (
        <div className="bg-error/10 border border-error/30 rounded-lg p-4 text-sm text-error">
          Failed to load journals: {error}
        </div>
      )}

      {!loading && !error && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {journals.map((j) => (
            <JournalCard key={j.name} journal={j} onSelect={handleSelect} />
          ))}
        </div>
      )}
    </div>
  );
}
