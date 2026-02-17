'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { CorpusStudiedItem } from '@/lib/types';

export default function CorpusStudiedPanel() {
  const [items, setItems] = useState<CorpusStudiedItem[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getCorpusStudied()
      .then((res) => setItems(res.items))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading || items.length === 0) return null;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-4 py-3 bg-amber-50 hover:bg-amber-100 transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-amber-600 text-sm font-medium">
            Already Studied in Corpus
          </span>
          <span className="text-xs text-amber-500 bg-amber-100 px-2 py-0.5 rounded-full">
            {items.length} authors/works
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-amber-500 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="max-h-80 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 sticky top-0">
              <tr>
                <th className="text-left px-4 py-2 text-text-secondary font-medium">Author</th>
                <th className="text-left px-4 py-2 text-text-secondary font-medium">Works / Topics</th>
                <th className="text-left px-4 py-2 text-text-secondary font-medium">Studied By</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((item, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-4 py-2 text-text-primary font-medium whitespace-nowrap">
                    {item.author}
                  </td>
                  <td className="px-4 py-2 text-text-secondary">
                    {item.works.map((w, j) => (
                      <span key={j}>
                        {j > 0 && <span className="text-text-muted"> · </span>}
                        <span className="italic">{w}</span>
                      </span>
                    ))}
                  </td>
                  <td className="px-4 py-2 text-text-muted whitespace-nowrap">{item.studied_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
