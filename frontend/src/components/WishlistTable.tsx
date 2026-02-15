'use client';

import { useState } from 'react';
import type { WishlistGroup, WishlistPaper } from '@/lib/types';

interface Props {
  groups: WishlistGroup[];
  totalCount: number;
  onBrowserDownload?: (sessionId: string) => void;
}

function scholarUrl(title: string): string {
  return `https://scholar.google.com/scholar?q=${encodeURIComponent(title)}`;
}

function scihubUrl(doi: string): string {
  return `https://sci-hub.se/${doi}`;
}

function libgenUrl(doi: string): string {
  return `https://libgen.rs/scimag/?q=${encodeURIComponent(doi)}`;
}

function PaperRows({ papers }: { papers: WishlistPaper[] }) {
  const recommended = papers.filter((p) => p.recommended);
  const metadataOnly = papers.filter((p) => !p.recommended);

  return (
    <div>
      {recommended.length > 0 && (
        <div>
          <div className="px-4 py-2 bg-accent/5 border-b border-slate-700">
            <span className="text-xs font-medium text-accent">
              Recommended ({recommended.length})
            </span>
            <span className="text-xs text-text-muted ml-2">
              — LLM-filtered most relevant papers
            </span>
          </div>
          <PaperTable papers={recommended} />
        </div>
      )}
      {metadataOnly.length > 0 && (
        <div>
          <div className="px-4 py-2 bg-slate-800/30 border-b border-t border-slate-700">
            <span className="text-xs font-medium text-text-muted">
              Metadata only ({metadataOnly.length})
            </span>
            <span className="text-xs text-text-muted ml-2">
              — stored for reference planner, not prioritized
            </span>
          </div>
          <PaperTable papers={metadataOnly} dimmed />
        </div>
      )}
      {recommended.length === 0 && metadataOnly.length === 0 && (
        <PaperTable papers={papers} />
      )}
    </div>
  );
}

function PaperTable({ papers, dimmed }: { papers: WishlistPaper[]; dimmed?: boolean }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-700">
          <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Title</th>
          <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Authors</th>
          <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase w-12">Year</th>
          <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Links</th>
        </tr>
      </thead>
      <tbody>
        {papers.map((p) => (
          <tr key={p.id} className={`border-b border-slate-700/50 hover:bg-bg-hover/30 ${dimmed ? 'opacity-50' : ''}`}>
            <td className="py-2 px-3 text-text-primary max-w-xs">
              <span className="line-clamp-2">{p.title}</span>
            </td>
            <td className="py-2 px-3 text-text-secondary max-w-[180px] truncate">
              {p.authors.join(', ')}
            </td>
            <td className="py-2 px-3 text-text-muted">{p.year}</td>
            <td className="py-2 px-3">
              <div className="flex items-center gap-2 flex-wrap">
                <a
                  href={scholarUrl(p.title)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 transition-colors"
                  title="Search on Google Scholar"
                >
                  Scholar
                </a>
                {p.doi && (
                  <>
                    <a
                      href={scihubUrl(p.doi)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition-colors"
                      title="Find on Sci-Hub"
                    >
                      Sci-Hub
                    </a>
                    <a
                      href={libgenUrl(p.doi)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 transition-colors"
                      title="Find on Library Genesis"
                    >
                      LibGen
                    </a>
                    <a
                      href={`https://doi.org/${p.doi}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-slate-600/30 text-text-muted hover:text-text-secondary transition-colors"
                      title="Publisher page"
                    >
                      DOI
                    </a>
                  </>
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function WishlistTable({ groups, totalCount, onBrowserDownload }: Props) {
  // First group (newest search) is expanded by default, rest collapsed
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => {
    const initial = new Set<string>();
    if (groups.length > 0 && groups[0].id !== 'other') {
      initial.add(groups[0].id);
    }
    return initial;
  });

  if (groups.length === 0) {
    return (
      <p className="text-sm text-text-muted text-center py-4">
        No papers waiting for PDFs.
      </p>
    );
  }

  const toggle = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className="space-y-2">
      {groups.map((group) => {
        const isExpanded = expandedIds.has(group.id);
        const isLatest = groups.indexOf(group) === 0 && group.id !== 'other';
        const recCount = group.recommended_count ?? 0;

        return (
          <div key={group.id} className="border border-slate-700 rounded-lg overflow-hidden">
            {/* Group header — clickable to expand/collapse */}
            <button
              onClick={() => toggle(group.id)}
              className="w-full flex items-center justify-between px-4 py-3 bg-bg-primary hover:bg-bg-hover/30 transition-colors text-left"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-text-muted text-xs flex-shrink-0">
                  {isExpanded ? '▼' : '▶'}
                </span>
                <span className="text-sm font-medium text-text-primary truncate">
                  {group.query}
                </span>
                {isLatest && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-accent/20 text-accent rounded flex-shrink-0">
                    Latest
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                {group.downloaded > 0 && (
                  <span className="text-[11px] px-2 py-0.5 bg-emerald-500/15 rounded text-success">
                    {group.downloaded} downloaded
                  </span>
                )}
                {recCount > 0 && (
                  <span className="text-[11px] px-2 py-0.5 bg-accent/15 rounded text-accent">
                    {recCount} recommended
                  </span>
                )}
                <span className="text-[11px] font-mono px-2 py-0.5 bg-slate-700 rounded text-text-secondary">
                  {group.needing_pdf} total
                </span>
              </div>
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div className="border-t border-slate-700">
                {/* Download effort summary */}
                {(group.total_found > 0 || group.downloaded > 0) && (
                  <div className="px-4 py-2 bg-slate-800/50 border-b border-slate-700 text-xs text-text-muted flex items-center justify-between">
                    <div className="flex gap-4">
                      <span>Found: <span className="text-text-secondary">{group.total_found}</span></span>
                      <span>Auto-downloaded: <span className="text-success">{group.downloaded}</span></span>
                      <span>Still need PDF: <span className="text-amber-400">{group.needing_pdf}</span></span>
                    </div>
                    {onBrowserDownload && group.id !== 'other' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onBrowserDownload(group.id); }}
                        className="px-2 py-1 bg-emerald-500/15 text-success rounded hover:bg-emerald-500/25 transition-colors"
                      >
                        Browser download this group
                      </button>
                    )}
                  </div>
                )}
                <PaperRows papers={group.papers} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
