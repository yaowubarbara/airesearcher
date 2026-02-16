'use client';

import type { ReadinessReport } from '@/lib/types';
import UploadZone from '@/components/UploadZone';

interface Props {
  report: ReadinessReport;
  loading?: boolean;
  onUpload?: (result: any) => void;
  onRecheck?: () => void;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  ready: { label: 'Ready', color: 'text-success', bg: 'bg-success/10 border-success/30' },
  missing_primary: { label: 'Missing Primary Texts', color: 'text-warning', bg: 'bg-warning/10 border-warning/30' },
  insufficient_criticism: { label: 'Insufficient Criticism', color: 'text-warning', bg: 'bg-warning/10 border-warning/30' },
  not_ready: { label: 'Not Ready', color: 'text-red-400', bg: 'bg-red-400/10 border-red-400/30' },
};

export default function ReadinessPanel({ report, loading, onUpload, onRecheck }: Props) {
  if (loading) {
    return (
      <div className="bg-bg-card rounded-lg p-4 border border-slate-700">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-text-secondary">Checking readiness...</span>
        </div>
      </div>
    );
  }

  if (!report || !report.items || report.items.length === 0) {
    return null;
  }

  const config = STATUS_CONFIG[report.status] || STATUS_CONFIG.ready;
  const primary = report.items.filter((i) => i.category === 'primary');
  const criticism = report.items.filter((i) => i.category === 'criticism');

  return (
    <div className={`rounded-lg p-4 border ${config.bg}`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-medium text-text-primary">Readiness Check</h4>
        <span className={`text-xs font-medium ${config.color}`}>{config.label}</span>
      </div>

      {primary.length > 0 && (
        <div className="mb-3">
          <span className="text-[10px] font-medium text-accent uppercase tracking-wider">
            Primary Texts ({primary.filter((i) => i.available).length}/{primary.length})
          </span>
          <div className="mt-1 space-y-1">
            {primary.map((item, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className={`flex-shrink-0 mt-0.5 ${item.available ? 'text-success' : 'text-red-400'}`}>
                  {item.available ? '\u2713' : '\u2717'}
                </span>
                <div className="min-w-0">
                  <span className="text-text-primary">
                    {item.author ? `${item.author}, ` : ''}{item.title}
                  </span>
                  {item.reason && !item.available && (
                    <p className="text-text-muted mt-0.5">{item.reason}</p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {criticism.length > 0 && (
        <div>
          <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">
            Key Criticism/Theory ({criticism.filter((i) => i.available).length}/{criticism.length})
          </span>
          <div className="mt-1 space-y-1">
            {criticism.map((item, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <span className={`flex-shrink-0 mt-0.5 ${item.available ? 'text-success' : 'text-text-muted'}`}>
                  {item.available ? '\u2713' : '\u2717'}
                </span>
                <span className="text-text-secondary">
                  {item.author ? `${item.author}, ` : ''}<span className="italic">{item.title}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {report.status !== 'ready' && (onUpload || onRecheck) && (
        <div className="mt-4 pt-3 border-t border-slate-600/50 space-y-3">
          {onUpload && (
            <div>
              <p className="text-xs text-text-muted mb-2">
                Upload missing texts as PDFs to improve readiness:
              </p>
              <UploadZone onUpload={onUpload} />
            </div>
          )}
          {onRecheck && (
            <button
              onClick={onRecheck}
              className="px-4 py-2 bg-accent text-bg-primary text-xs font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
              Re-check Readiness
            </button>
          )}
        </div>
      )}
    </div>
  );
}
