'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import UploadZone from '@/components/UploadZone';
import ManualAddForm from '@/components/ManualAddForm';
import type { SessionPaper } from '@/lib/types';

interface Props {
  sessionId: string;
  journal: string;
  onConfirm: (selectedIds: string[]) => void;
  onCancel: () => void;
}

export default function ReferencePicker({ sessionId, journal, onConfirm, onCancel }: Props) {
  const [papers, setPapers] = useState<SessionPaper[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  const loadPapers = useCallback(async () => {
    try {
      const data = await api.getSessionPapers(sessionId);
      setPapers(data.papers);
    } catch {
      setPapers([]);
    }
    setLoading(false);
  }, [sessionId]);

  useEffect(() => {
    loadPapers();
  }, [loadPapers]);

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectRecommended = () => {
    const ids = papers.filter(p => p.recommended).map(p => p.id);
    setSelected(new Set(ids));
  };

  const selectAllIndexed = () => {
    const ids = papers.filter(p => p.status === 'indexed' || p.status === 'analyzed').map(p => p.id);
    setSelected(new Set(ids));
  };

  const selectAll = () => {
    setSelected(new Set(papers.map(p => p.id)));
  };

  const deselectAll = () => {
    setSelected(new Set());
  };

  const statusIcon = (status: string) => {
    if (status === 'indexed' || status === 'analyzed') return { color: 'text-success', label: 'indexed' };
    if (status === 'pdf_downloaded') return { color: 'text-blue-600', label: 'PDF' };
    return { color: 'text-text-muted', label: 'metadata' };
  };

  const handleUpload = useCallback(() => {
    // Refresh paper list after upload
    loadPapers();
  }, [loadPapers]);

  const handleAdded = useCallback(() => {
    loadPapers();
  }, [loadPapers]);

  return (
    <div className="bg-bg-card rounded-lg border border-border overflow-hidden">
      <div className="px-5 py-4 border-b border-border">
        <h3 className="text-sm font-semibold text-text-primary">Select References for Plan</h3>
        <p className="text-xs text-text-secondary mt-1">
          Choose which papers to include. Only selected papers will be used by the planner.
        </p>
      </div>

      {/* Quick-select buttons */}
      <div className="px-5 py-3 border-b border-border flex items-center gap-2 flex-wrap">
        <button
          onClick={selectRecommended}
          className="text-xs px-3 py-1.5 bg-accent-light text-accent rounded-md hover:bg-accent-light transition-colors"
        >
          Select Recommended
        </button>
        <button
          onClick={selectAllIndexed}
          className="text-xs px-3 py-1.5 bg-success/10 text-success rounded-md hover:bg-success/20 transition-colors"
        >
          Select All Indexed
        </button>
        <button
          onClick={selectAll}
          className="text-xs px-3 py-1.5 bg-gray-100 text-text-secondary rounded-md hover:bg-gray-200 transition-colors"
        >
          Select All
        </button>
        <button
          onClick={deselectAll}
          className="text-xs px-3 py-1.5 bg-gray-100 text-text-secondary rounded-md hover:bg-gray-200 transition-colors"
        >
          Deselect All
        </button>
        <span className="ml-auto text-xs text-text-muted">
          {selected.size} of {papers.length} selected
        </span>
      </div>

      {/* Paper list */}
      <div className="max-h-[400px] overflow-y-auto">
        {loading ? (
          <div className="flex justify-center py-8">
            <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          </div>
        ) : papers.length === 0 ? (
          <div className="px-5 py-8 text-center text-sm text-text-muted">
            No papers in this session. Upload PDFs or add references below.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {papers.map((p) => {
              const si = statusIcon(p.status);
              const isSelected = selected.has(p.id);
              return (
                <label
                  key={p.id}
                  className={`flex items-start gap-3 px-5 py-3 cursor-pointer transition-colors ${
                    isSelected ? 'bg-accent-light' : 'hover:bg-bg-hover'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggle(p.id)}
                    className="mt-1 accent-accent"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text-primary truncate">{p.title || '(untitled)'}</span>
                      {p.recommended && (
                        <span className="flex-shrink-0 text-[10px] bg-accent-light text-accent px-1.5 py-0.5 rounded">rec</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-0.5">
                      {p.authors.length > 0 && (
                        <span className="text-xs text-text-secondary truncate">
                          {p.authors.slice(0, 2).join(', ')}{p.authors.length > 2 ? ' et al.' : ''}
                        </span>
                      )}
                      {p.year > 0 && <span className="text-xs text-text-muted">{p.year}</span>}
                      <span className={`text-[10px] ${si.color}`}>{si.label}</span>
                    </div>
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </div>

      {/* Upload zone for last-minute additions */}
      <div className="px-5 py-4 border-t border-border space-y-3">
        <p className="text-xs text-text-muted">Add more references:</p>
        <UploadZone sessionId={sessionId} onUpload={handleUpload} />
        <ManualAddForm compact sessionId={sessionId} onAdded={handleAdded} />
      </div>

      {/* Action buttons */}
      <div className="px-5 py-4 border-t border-border flex items-center justify-between">
        <button
          onClick={onCancel}
          className="px-4 py-2 border border-border text-text-secondary text-sm rounded-lg hover:bg-bg-hover transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={() => onConfirm(Array.from(selected))}
          disabled={selected.size === 0}
          className="px-5 py-2.5 bg-accent text-text-inverse text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Create Plan with {selected.size} Selected
        </button>
      </div>
    </div>
  );
}
