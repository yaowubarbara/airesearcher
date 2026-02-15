'use client';

import type { WishlistPaper } from '@/lib/types';

interface Props {
  papers: WishlistPaper[];
}

export default function WishlistTable({ papers }: Props) {
  if (papers.length === 0) {
    return (
      <p className="text-sm text-text-muted text-center py-4">
        No papers waiting for PDFs.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-700">
            <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Title</th>
            <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Authors</th>
            <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">Year</th>
            <th className="text-left py-2 px-3 text-xs text-text-muted font-medium uppercase">DOI</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((p) => (
            <tr key={p.id} className="border-b border-slate-700/50 hover:bg-bg-hover/30">
              <td className="py-2 px-3 text-text-primary max-w-xs truncate">{p.title}</td>
              <td className="py-2 px-3 text-text-secondary max-w-[200px] truncate">
                {p.authors.join(', ')}
              </td>
              <td className="py-2 px-3 text-text-muted">{p.year}</td>
              <td className="py-2 px-3 text-text-muted text-xs font-mono">
                {p.doi ? (
                  <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noopener noreferrer"
                     className="text-accent hover:underline">
                    {p.doi}
                  </a>
                ) : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
