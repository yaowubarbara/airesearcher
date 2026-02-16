'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import type { DownloadedGroup, DownloadedPaper } from '@/lib/types';

interface Props {
  groups: DownloadedGroup[];
  totalCount: number;
}

function PaperTable({ papers }: { papers: DownloadedPaper[] }) {
  return (
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
        {papers.map((p) => (
          <tr key={p.id} className="border-b border-slate-700/50 hover:bg-bg-hover/30">
            <td className="py-2 px-3 max-w-xs">
              {p.pdf_path ? (
                <a
                  href={api.getPdfUrl(p.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-accent hover:underline line-clamp-2"
                  title="Open PDF"
                >
                  {p.title}
                </a>
              ) : (
                <span className="text-text-primary line-clamp-2">{p.title}</span>
              )}
            </td>
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
  );
}

export default function DownloadedTable({ groups, totalCount }: Props) {
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
        No papers downloaded yet.
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

        return (
          <div key={group.id} className="border border-slate-700 rounded-lg overflow-hidden">
            <button
              onClick={() => toggle(group.id)}
              className="w-full flex items-center justify-between px-4 py-3 bg-bg-primary hover:bg-bg-hover/30 transition-colors text-left"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-text-muted text-xs flex-shrink-0">
                  {isExpanded ? '\u25BC' : '\u25B6'}
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
                <span className="text-[11px] font-mono px-2 py-0.5 bg-emerald-500/15 rounded text-success">
                  {group.paper_count} papers
                </span>
              </div>
            </button>

            {isExpanded && (
              <div className="border-t border-slate-700">
                <PaperTable papers={group.papers} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
