'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { usePipelineStore, STAGE_ORDER, getStageName, type PipelineStage } from '@/lib/store';

const stageIcons: Record<PipelineStage, string> = {
  journal: '1',
  discover: '2',
  references: '3',
  plan: '4',
  write: '5',
  review: '6',
  revision: '7',
  submit: '8',
};

const stageRoutes: Record<PipelineStage, string> = {
  journal: '/',
  discover: '/pipeline/discover',
  references: '/pipeline/references',
  plan: '/pipeline/plan',
  write: '/pipeline/write',
  review: '/pipeline/review',
  revision: '/pipeline/revision',
  submit: '/pipeline/submit',
};

export default function Sidebar() {
  const pathname = usePathname();
  const { completedStages, isStageUnlocked, selectedJournal } = usePipelineStore();

  return (
    <aside className="w-64 bg-sidebar-bg border-r border-sidebar-border h-screen sticky top-0 flex flex-col">
      <div className="p-5 border-b border-sidebar-border">
        <Link href="/" className="block">
          <h1 className="text-lg font-bold text-accent">AI Researcher</h1>
          <p className="text-xs text-sidebar-muted mt-1">Academic Paper Pipeline</p>
        </Link>
      </div>

      {selectedJournal && (
        <div className="px-5 py-3 border-b border-sidebar-border">
          <p className="text-xs text-sidebar-muted uppercase tracking-wider">Target Journal</p>
          <p className="text-sm text-sidebar-text font-medium mt-1 truncate">{selectedJournal}</p>
        </div>
      )}

      <nav className="flex-1 py-4 overflow-y-auto">
        {STAGE_ORDER.map((stage) => {
          const unlocked = isStageUnlocked(stage);
          const completed = completedStages.includes(stage);
          const route = stageRoutes[stage];
          const isActive = pathname === route;

          return (
            <Link
              key={stage}
              href={unlocked ? route : '#'}
              className={`flex items-center gap-3 px-5 py-2.5 text-sm transition-colors ${
                isActive
                  ? 'bg-accent/10 text-accent border-r-2 border-accent'
                  : unlocked
                  ? 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-text'
                  : 'text-sidebar-muted cursor-not-allowed opacity-40'
              }`}
              onClick={(e) => !unlocked && e.preventDefault()}
            >
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                  completed
                    ? 'bg-emerald-400/20 text-emerald-300'
                    : isActive
                    ? 'bg-accent/20 text-accent'
                    : 'bg-sidebar-border text-sidebar-muted'
                }`}
              >
                {completed ? '\u2713' : stageIcons[stage]}
              </span>
              <span>{getStageName(stage)}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-sidebar-border">
        <Link
          href="/stats"
          className={`flex items-center gap-2 text-sm px-2 py-1.5 rounded transition-colors ${
            pathname === '/stats'
              ? 'text-accent'
              : 'text-sidebar-muted hover:text-sidebar-text'
          }`}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Usage Stats
        </Link>
      </div>
    </aside>
  );
}
