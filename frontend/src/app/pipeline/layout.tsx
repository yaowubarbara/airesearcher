'use client';

import StageIndicator from '@/components/StageIndicator';

export default function PipelineLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-screen">
      <div className="px-6 py-3 border-b border-slate-700 bg-bg-card/50">
        <StageIndicator />
      </div>
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto">{children}</div>
      </div>
    </div>
  );
}
