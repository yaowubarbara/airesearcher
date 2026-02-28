'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import DomainCard from '@/components/DomainCard';
import JournalCard from '@/components/JournalCard';
import type { Domain, Journal } from '@/lib/types';

export default function HomePage() {
  const [domains, setDomains] = useState<Domain[]>([]);
  const [journals, setJournals] = useState<Journal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { selectedDomain, selectDomain, selectJournal, resetPipeline } = usePipelineStore();

  // Load domains on mount
  useEffect(() => {
    api.getDomains()
      .then((data) => setDomains(data.domains))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // Load journals when domain changes
  useEffect(() => {
    if (!selectedDomain) return;
    setJournals([]);
    api.getJournals(selectedDomain)
      .then((data) => {
        const sorted = data.journals.sort((a, b) => {
          if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
          return a.name.localeCompare(b.name);
        });
        setJournals(sorted);
      })
      .catch(() => {});
  }, [selectedDomain]);

  const handleSelectJournal = (name: string) => {
    resetPipeline();
    selectJournal(name);
    router.push('/pipeline/discover');
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      {/* Step 1: Domain Selection */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold text-text-primary mb-2">Select Research Domain</h1>
        <p className="text-text-secondary text-sm mb-6">
          Choose a research domain to configure the analysis pipeline, annotation schema,
          and review criteria for your field.
        </p>

        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="bg-error/10 border border-error/30 rounded-lg p-4 text-sm text-error">
            Failed to load domains: {error}
          </div>
        )}

        {!loading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {domains.map((d) => (
              <DomainCard
                key={d.domain_id}
                domain={d}
                selected={selectedDomain === d.domain_id}
                onSelect={selectDomain}
              />
            ))}
          </div>
        )}
      </div>

      {/* Step 2: Journal Selection */}
      {selectedDomain && journals.length > 0 && (
        <div>
          <h2 className="text-xl font-bold text-text-primary mb-2">Select Target Journal</h2>
          <p className="text-text-secondary text-sm mb-4">
            Choose a journal to begin the research pipeline. Active journals have full support.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {journals.map((j) => (
              <JournalCard key={j.name} journal={j} onSelect={handleSelectJournal} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
