'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import UploadZone from '@/components/UploadZone';
import WishlistTable from '@/components/WishlistTable';
import TaskProgress from '@/components/TaskProgress';
import type { WishlistGroup, DownloadedPaper } from '@/lib/types';

export default function ReferencesPage() {
  const router = useRouter();
  const {
    selectedTopicId, selectedJournal,
    activeTaskId, setActiveTaskId, setStage, completeStage,
  } = usePipelineStore();

  const [groups, setGroups] = useState<WishlistGroup[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [downloadedPapers, setDownloadedPapers] = useState<DownloadedPaper[]>([]);
  const [downloadedCount, setDownloadedCount] = useState(0);
  const [showDownloaded, setShowDownloaded] = useState(false);
  const [browserTaskId, setBrowserTaskId] = useState<string | null>(null);

  useEffect(() => {
    setStage('references');
    loadWishlist();
    loadDownloaded();
  }, [setStage]);

  const loadWishlist = async () => {
    try {
      const data = await api.getWishlist();
      setGroups(data.groups);
      setTotalCount(data.total_count);
    } catch {}
    setLoading(false);
  };

  const loadDownloaded = async () => {
    try {
      const data = await api.getDownloaded();
      setDownloadedPapers(data.papers);
      setDownloadedCount(data.count);
    } catch {}
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
    loadDownloaded();
  }, [setActiveTaskId]);

  const startBrowserDownload = async (sessionId?: string) => {
    try {
      const { task_id } = await api.browserDownload(sessionId, 20);
      setBrowserTaskId(task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleBrowserComplete = useCallback((result: any) => {
    setBrowserTaskId(null);
    loadWishlist();
    loadDownloaded();
  }, []);

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
        <UploadZone onUpload={() => { loadWishlist(); loadDownloaded(); }} />
      </div>

      {/* Downloaded Papers */}
      <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-text-primary flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-success" />
            Papers Downloaded ({downloadedCount})
          </h3>
          <button
            onClick={() => setShowDownloaded(!showDownloaded)}
            className="text-xs text-accent hover:underline"
          >
            {showDownloaded ? 'Hide' : 'Show'}
          </button>
        </div>
        {showDownloaded && downloadedPapers.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Title</th>
                <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Authors</th>
                <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase w-12">Year</th>
                <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase w-20">Status</th>
              </tr>
            </thead>
            <tbody>
              {downloadedPapers.map((p) => (
                <tr key={p.id} className="border-b border-slate-700/50 hover:bg-bg-hover/30">
                  <td className="py-2 px-3 text-text-primary max-w-xs truncate">{p.title}</td>
                  <td className="py-2 px-3 text-text-secondary max-w-[180px] truncate">
                    {p.authors.join(', ')}
                  </td>
                  <td className="py-2 px-3 text-text-muted">{p.year}</td>
                  <td className="py-2 px-3">
                    <span className={`text-[11px] px-2 py-0.5 rounded ${
                      p.status === 'indexed'
                        ? 'bg-emerald-500/15 text-success'
                        : 'bg-blue-500/15 text-blue-400'
                    }`}>
                      {p.status === 'indexed' ? 'Indexed' : 'Downloaded'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {showDownloaded && downloadedPapers.length === 0 && (
          <p className="text-sm text-text-muted text-center py-4">No papers downloaded yet.</p>
        )}
      </div>

      {/* Browser Download */}
      {browserTaskId && (
        <TaskProgress
          taskId={browserTaskId}
          onComplete={handleBrowserComplete}
          label="Browser downloading PDFs from Sci-Hub/LibGen..."
        />
      )}

      {/* Wishlist — grouped by search session */}
      <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-text-primary">
            Papers Needing PDFs ({totalCount})
          </h3>
          <div className="flex items-center gap-3">
            <button
              onClick={() => startBrowserDownload()}
              disabled={!!browserTaskId || totalCount === 0}
              className="text-xs px-3 py-1.5 bg-emerald-500/15 text-success rounded-md hover:bg-emerald-500/25 disabled:opacity-50 transition-colors"
            >
              Auto-download via browser
            </button>
            <button
              onClick={() => { loadWishlist(); loadDownloaded(); }}
              className="text-xs text-accent hover:underline"
            >
              Refresh
            </button>
          </div>
        </div>
        {loading ? (
          <div className="flex justify-center py-4">
            <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <WishlistTable
            groups={groups}
            totalCount={totalCount}
            onBrowserDownload={startBrowserDownload}
          />
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
