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
import type { WishlistGroup, DownloadedGroup, SearchSession, SmartSearchRef, SmartSearchResult } from '@/lib/types';

const TIER_LABELS: Record<number, { label: string; color: string }> = {
  1: { label: 'Core', color: 'text-rose-400 bg-rose-500/15' },
  2: { label: 'Important', color: 'text-amber-400 bg-amber-500/15' },
  3: { label: 'Supporting', color: 'text-sky-400 bg-sky-500/15' },
};

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

  // Smart search state
  const [smartTaskId, setSmartTaskId] = useState<string | null>(null);
  const [smartResult, setSmartResult] = useState<SmartSearchResult | null>(null);
  const [smartTitle, setSmartTitle] = useState('');
  const [smartRQ, setSmartRQ] = useState('');
  const [smartGap, setSmartGap] = useState('');
  const [showSmartForm, setShowSmartForm] = useState(false);

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

  // Smart search handlers
  const startSmartSearch = async () => {
    if (!smartTitle.trim() || !smartRQ.trim()) return;
    try {
      const { task_id } = await api.smartSearchReferences(
        smartTitle.trim(), smartRQ.trim(), smartGap.trim(),
      );
      setSmartTaskId(task_id);
      setSmartResult(null);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleSmartComplete = useCallback((result: any) => {
    setSmartTaskId(null);
    if (result) {
      setSmartResult(result as SmartSearchResult);
    }
    loadWishlist();
    loadDownloaded();
    loadSessions();
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

      {/* Keyword Search */}
      <div className="bg-bg-card rounded-lg p-5 border border-border">
        <h3 className="text-sm font-medium text-text-primary mb-3">Keyword Search</h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && startSearch()}
            placeholder="Enter search topic..."
            className="flex-1 bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          />
          <button
            onClick={startSearch}
            disabled={!!activeTaskId || !searchQuery.trim()}
            className="px-4 py-2 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 transition-colors"
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

      {/* Smart Search */}
      <div className="bg-bg-card rounded-lg p-5 border border-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-text-primary">Smart Search</h3>
          <button
            onClick={() => setShowSmartForm(!showSmartForm)}
            className="text-xs text-accent hover:underline"
          >
            {showSmartForm ? 'Hide' : 'Show'}
          </button>
        </div>
        <p className="text-xs text-text-muted mb-3">
          LLM-guided reference discovery: generates a bibliography blueprint, verifies via APIs, expands through citation chains, and curates the final list.
        </p>
        {showSmartForm && (
          <div className="space-y-3">
            <input
              type="text"
              value={smartTitle}
              onChange={(e) => setSmartTitle(e.target.value)}
              placeholder="Research topic title..."
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
            <textarea
              value={smartRQ}
              onChange={(e) => setSmartRQ(e.target.value)}
              placeholder="Research question..."
              rows={2}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent resize-none"
            />
            <textarea
              value={smartGap}
              onChange={(e) => setSmartGap(e.target.value)}
              placeholder="Gap description (what is missing in existing scholarship)..."
              rows={2}
              className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent resize-none"
            />
            <div className="flex justify-end">
              <button
                onClick={startSmartSearch}
                disabled={!!smartTaskId || !smartTitle.trim() || !smartRQ.trim()}
                className="px-4 py-2 bg-violet-600 text-white text-sm font-medium rounded-lg hover:bg-violet-700 disabled:opacity-50 transition-colors"
              >
                Run Smart Search
              </button>
            </div>
          </div>
        )}
      </div>

      {smartTaskId && (
        <TaskProgress
          taskId={smartTaskId}
          onComplete={handleSmartComplete}
          label="Smart search: blueprint → verify → expand → curate..."
        />
      )}

      {/* Smart Search Results */}
      {smartResult && (
        <div className="bg-bg-card rounded-lg p-5 border border-border">
          <h3 className="text-sm font-medium text-text-primary mb-3">Smart Search Results</h3>

          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
            {[
              { label: 'Blueprint', value: smartResult.blueprint_suggested },
              { label: 'Verified', value: smartResult.verified },
              { label: 'Hallucinated', value: smartResult.hallucinated },
              { label: 'Expanded', value: smartResult.expanded_pool },
              { label: 'Selected', value: smartResult.final_selected },
            ].map((s) => (
              <div key={s.label} className="bg-bg-primary rounded-md p-2 text-center">
                <div className="text-lg font-bold text-text-primary">{s.value}</div>
                <div className="text-xs text-text-muted">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Gaps */}
          {smartResult.gaps.length > 0 && (
            <div className="mb-4 p-3 bg-amber-500/10 rounded-md border border-amber-500/20">
              <div className="text-xs font-medium text-amber-400 mb-1">Gaps Identified</div>
              {smartResult.gaps.map((gap, i) => (
                <div key={i} className="text-xs text-text-secondary">{gap}</div>
              ))}
            </div>
          )}

          {/* Category breakdown */}
          {Object.keys(smartResult.categories).length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              {Object.entries(smartResult.categories).map(([cat, count]) => (
                <span key={cat} className="text-xs px-2 py-1 bg-bg-primary rounded-full text-text-secondary">
                  {cat}: {count}
                </span>
              ))}
            </div>
          )}

          {/* Reference table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-2 text-text-muted font-medium">Tier</th>
                  <th className="text-left py-2 px-2 text-text-muted font-medium">Category</th>
                  <th className="text-left py-2 px-2 text-text-muted font-medium">Reference</th>
                  <th className="text-left py-2 px-2 text-text-muted font-medium">Usage</th>
                </tr>
              </thead>
              <tbody>
                {smartResult.references.map((ref, i) => {
                  const tier = TIER_LABELS[ref.tier] || TIER_LABELS[3];
                  return (
                    <tr key={i} className="border-b border-border/50 hover:bg-bg-primary/50">
                      <td className="py-2 px-2">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${tier.color}`}>
                          {tier.label}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-text-muted">{ref.category}</td>
                      <td className="py-2 px-2">
                        <div className="text-text-primary font-medium">{ref.title}</div>
                        <div className="text-text-muted">
                          {ref.authors.slice(0, 2).join(', ')}
                          {ref.authors.length > 2 ? ' et al.' : ''}
                          {ref.year ? ` (${ref.year})` : ''}
                          {ref.journal ? ` — ${ref.journal}` : ''}
                        </div>
                      </td>
                      <td className="py-2 px-2 text-text-muted max-w-[200px]">{ref.usage_note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Upload */}
      <div className="bg-bg-card rounded-lg p-5 border border-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-text-primary">Upload PDFs</h3>
          {sessions.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-muted">Link to session:</label>
              <select
                value={uploadSessionId}
                onChange={(e) => setUploadSessionId(e.target.value)}
                className="bg-bg-primary border border-border rounded px-2 py-1 text-xs text-text-primary focus:outline-none focus:border-accent"
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
      <div className="bg-bg-card rounded-lg p-5 border border-border">
        <h3 className="text-sm font-medium text-text-primary mb-3">Add Reference Manually</h3>
        <ManualAddForm
          sessionId={uploadSessionId || undefined}
          onAdded={() => { loadWishlist(); loadDownloaded(); }}
        />
      </div>

      {/* Downloaded Papers */}
      <div className="bg-bg-card rounded-lg p-5 border border-border">
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
      <div className="bg-bg-card rounded-lg p-5 border border-border">
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

      <div className="flex justify-end pt-4 border-t border-border">
        <button
          onClick={handleProceed}
          className="px-6 py-2.5 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
        >
          Continue to Plan
        </button>
      </div>
    </div>
  );
}
