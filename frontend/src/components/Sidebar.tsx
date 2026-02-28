'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { usePipelineStore } from '@/lib/store';

const NAV_ITEMS = [
  { href: '/', label: 'Domain & Journal', icon: '🏠' },
  { href: '/pipeline/discover', label: 'Discover', icon: '🔍' },
  { href: '/pipeline/plan', label: 'Plan', icon: '📋' },
  { href: '/pipeline/references', label: 'References', icon: '📖' },
  { href: '/pipeline/write', label: 'Write', icon: '✍️' },
  { href: '/pipeline/review', label: 'Review', icon: '📝' },
  { href: '/pipeline/revision', label: 'Revision', icon: '🔄' },
  { href: '/pipeline/submit', label: 'Submit', icon: '📤' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { selectedDomain, selectedJournal } = usePipelineStore();

  return (
    <aside className="w-56 bg-bg-secondary border-r border-border flex flex-col">
      <div className="p-4 border-b border-border">
        <h1 className="text-base font-bold text-accent">AI Researcher</h1>
        <p className="text-xs text-text-tertiary mt-1">Research Pipeline</p>
      </div>

      <nav className="flex-1 p-2">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`
                flex items-center gap-2 px-3 py-2 rounded-md text-sm mb-0.5 transition-colors
                ${isActive
                  ? 'bg-accent/10 text-accent font-medium'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                }
              `}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-border text-xs text-text-tertiary">
        {selectedDomain && (
          <div className="mb-1">
            <span className="text-text-secondary">Domain:</span>{' '}
            {selectedDomain.replace(/_/g, ' ')}
          </div>
        )}
        {selectedJournal && (
          <div>
            <span className="text-text-secondary">Journal:</span>{' '}
            {selectedJournal}
          </div>
        )}
      </div>
    </aside>
  );
}
