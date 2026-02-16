'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import UploadZone from '@/components/UploadZone';
import ManualAddForm from '@/components/ManualAddForm';
import WishlistTable from '@/components/WishlistTable';
import DownloadedTable from '@/components/DownloadedTable';
import TaskProgress from '@/components/TaskProgress';
import type { WishlistGroup, DownloadedGroup, SearchSession } from '@/lib/types';

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
  const [downloadedGroups, setDownloadedGroups] = useState<DownloadedGroup[]>([]);
  const [downloadedCount, setDownloadedCount] = useState(0);
  const [showDownloaded, setShowDownloaded] = useState(false);
  const [browserTaskId, setBrowserTaskId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SearchSession[]>([]);
  const [uploadSessionId, setUploadSessionId] = useState<string>('');

  useEffect(() => {
    setStage('references');
    loadWishlist();
    loadDownloaded();
    loadSessions();
  }, [setStage]);

  const loadSessions = async () => {
    try {
      const data = await api.getSearchSessions();
      setSessions(data.sessions);
    } catch {}
  };

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
      setDownloadedGroups(data.groups);
      setDownloadedCount(data.total_count);
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
    loadSessions();
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
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-text-primary">Upload PDFs</h3>
          {sessions.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-muted">Link to session:</label>
              <select
                value={uploadSessionId}
                onChange={(e) => setUploadSessionId(e.target.value)}
                className="bg-bg-primary border border-slate-600 rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent"
              >
                <option value="">No session (general)</option>
                {sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.query} ({s.total_papers} papers)
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        <UploadZone
          sessionId={uploadSessionId || undefined}
          onUpload={() => { loadWishlist(); loadDownloaded(); }}
        />
      </div>

      {/* Manual Add */}
      <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
        <h3 className="text-sm font-medium text-text-primary mb-3">Add Reference Manually</h3>
        <ManualAddForm
          sessionId={uploadSessionId || undefined}
          onAdded={() => { loadWishlist(); loadDownloaded(); }}
        />
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
        {showDownloaded && (
          <DownloadedTable groups={downloadedGroups} totalCount={downloadedCount} />
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
