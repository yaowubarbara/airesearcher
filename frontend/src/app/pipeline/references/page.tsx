'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import UploadZone from '@/components/UploadZone';
import WishlistTable from '@/components/WishlistTable';
import TaskProgress from '@/components/TaskProgress';
import type { WishlistPaper } from '@/lib/types';

export default function ReferencesPage() {
  const router = useRouter();
  const {
    selectedTopicId, selectedJournal,
    activeTaskId, setActiveTaskId, setStage, completeStage,
  } = usePipelineStore();

  const [wishlist, setWishlist] = useState<WishlistPaper[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setStage('references');
    loadWishlist();
  }, [setStage]);

  const loadWishlist = async () => {
    try {
      const data = await api.getWishlist();
      setWishlist(data.papers);
    } catch {}
    setLoading(false);
  };

  const startSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const { task_id } = await api.searchReferences(searchQuery.trim());
      setActiveTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleSearchComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    loadWishlist();
  }, [setActiveTaskId]);

  const handleProceed = () => {
    completeStage('references');
    router.push('/pipeline/plan');
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-text-primary">Reference Acquisition</h2>
        <p className="text-sm text-text-secondary mt-1">
          Search for references and upload PDFs for your research.
        </p>
      </div>

      {/* Search */}
      <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
        <h3 className="text-sm font-medium text-text-primary mb-3">Search References</h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && startSearch()}
            placeholder="Enter search topic..."
            className="flex-1 bg-bg-primary border border-slate-600 rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <button
            onClick={startSearch}
            disabled={!!activeTaskId || !searchQuery.trim()}
            className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 transition-colors"
          >
            Search
          </button>
        </div>
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handleSearchComplete}
        label="Searching and downloading references..."
      />

      {/* Upload */}
      <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
        <h3 className="text-sm font-medium text-text-primary mb-3">Upload PDFs</h3>
        <UploadZone onUpload={() => loadWishlist()} />
      </div>

      {/* Wishlist */}
      <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-text-primary">
            Papers Needing PDFs ({wishlist.length})
          </h3>
          <button
            onClick={loadWishlist}
            className="text-xs text-accent hover:underline"
          >
            Refresh
          </button>
        </div>
        {loading ? (
          <div className="flex justify-center py-4">
            <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <WishlistTable papers={wishlist} />
        )}
      </div>

      <div className="flex justify-end pt-4 border-t border-slate-700">
        <button
          onClick={handleProceed}
          className="px-6 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
        >
          Continue to Plan
        </button>
      </div>
    </div>
  );
}
