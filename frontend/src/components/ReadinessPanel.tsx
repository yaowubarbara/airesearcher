'use client';

import { useState } from 'react';
import type { ReadinessReport } from '@/lib/types';
import UploadZone from '@/components/UploadZone';
import ManualAddForm from '@/components/ManualAddForm';

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
  not_ready: { label: 'Not Ready', color: 'text-error', bg: 'bg-red-400/10 border-red-400/30' },
};

export default function ReadinessPanel({ report, loading, onUpload, onRecheck }: Props) {
  const [expandedItem, setExpandedItem] = useState<string | null>(null);
  const [resolvedItems, setResolvedItems] = useState<Set<string>>(new Set());

  if (loading) {
    return (
      <div className="bg-bg-card rounded-lg p-4 border border-border">
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
          <div className="mt-1 space-y-1.5">
            {primary.map((item, i) => {
              const itemKey = `primary-${i}`;
              const isResolved = resolvedItems.has(itemKey);
              const isExpanded = expandedItem === itemKey;
              const isAvailable = item.available || isResolved;

              return (
                <div key={i}>
                  <div className="flex items-start gap-2 text-xs">
                    <span className={`flex-shrink-0 mt-0.5 ${isAvailable ? 'text-success' : 'text-error'}`}>
                      {isAvailable ? '\u2713' : '\u2717'}
                    </span>
                    <div className="min-w-0 flex-1">
                      <span className={`text-text-primary ${isResolved ? 'line-through text-success' : ''}`}>
                        {item.author ? `${item.author}, ` : ''}{item.title}
                      </span>
                      {item.reason && !isAvailable && (
                        <p className="text-text-muted mt-0.5">{item.reason}</p>
                      )}
                    </div>
                    {!isAvailable && (
                      <button
                        onClick={() => setExpandedItem(isExpanded ? null : itemKey)}
                        className="flex-shrink-0 text-[10px] px-1.5 py-0.5 border border-border text-text-secondary rounded hover:bg-bg-hover transition-colors"
                      >
                        {isExpanded ? 'Cancel' : '+ Add'}
                      </button>
                    )}
                  </div>
                  {isExpanded && !isAvailable && (
                    <div className="ml-6 mt-1">
                      <ManualAddForm
                        compact
                        prefillTitle={item.title}
                        prefillAuthors={item.author}
                        defaultRefType="primary_literary"
                        onAdded={() => {
                          setResolvedItems((prev) => new Set(prev).add(itemKey));
                          setExpandedItem(null);
                          onRecheck?.();
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {criticism.length > 0 && (
        <div>
          <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">
            Key Criticism/Theory ({criticism.filter((i) => i.available).length}/{criticism.length})
          </span>
          <div className="mt-1 space-y-1.5">
            {criticism.map((item, i) => {
              const itemKey = `criticism-${i}`;
              const isResolved = resolvedItems.has(itemKey);
              const isExpanded = expandedItem === itemKey;
              const isAvailable = item.available || isResolved;

              return (
                <div key={i}>
                  <div className="flex items-start gap-2 text-xs">
                    <span className={`flex-shrink-0 mt-0.5 ${isAvailable ? 'text-success' : 'text-text-muted'}`}>
                      {isAvailable ? '\u2713' : '\u2717'}
                    </span>
                    <span className={`text-text-secondary flex-1 ${isResolved ? 'line-through text-success' : ''}`}>
                      {item.author ? `${item.author}, ` : ''}<span className="italic">{item.title}</span>
                    </span>
                    {!isAvailable && (
                      <button
                        onClick={() => setExpandedItem(isExpanded ? null : itemKey)}
                        className="flex-shrink-0 text-[10px] px-1.5 py-0.5 border border-border text-text-secondary rounded hover:bg-bg-hover transition-colors"
                      >
                        {isExpanded ? 'Cancel' : '+ Add'}
                      </button>
                    )}
                  </div>
                  {isExpanded && !isAvailable && (
                    <div className="ml-6 mt-1">
                      <ManualAddForm
                        compact
                        prefillTitle={item.title}
                        prefillAuthors={item.author}
                        defaultRefType="secondary_criticism"
                        onAdded={() => {
                          setResolvedItems((prev) => new Set(prev).add(itemKey));
                          setExpandedItem(null);
                          onRecheck?.();
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {report.status !== 'ready' && (onUpload || onRecheck) && (
        <div className="mt-4 pt-3 border-t border-border space-y-3">
          {onUpload && (
            <div>
              <p className="text-xs text-text-muted mb-2">
                Upload missing texts as PDFs to improve readiness:
              </p>
              <UploadZone onUpload={onUpload} />
            </div>
          )}
          {onRecheck && !onUpload && (
            <button
              onClick={onRecheck}
              className="px-4 py-2 bg-accent text-text-inverse text-xs font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
              Re-check Readiness
            </button>
          )}
        </div>
      )}
    </div>
  );
}
