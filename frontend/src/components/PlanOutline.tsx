'use client';

import { useMemo, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import type { ResearchPlan, OutlineSection, TheorySupplementResult } from '@/lib/types';
import UploadZone from '@/components/UploadZone';
import TaskProgress from '@/components/TaskProgress';
import TheoryPanel from '@/components/TheoryPanel';

interface Props {
  plan: ResearchPlan;
  onUpload?: (result: any) => void;
}

export default function PlanOutline({ plan, onUpload }: Props) {
  const [theoryTaskId, setTheoryTaskId] = useState<string | null>(null);
  const [theoryResult, setTheoryResult] = useState<TheorySupplementResult | null>(null);

  const outline: OutlineSection[] = useMemo(() => {
    if (Array.isArray(plan.outline)) return plan.outline;
    if (typeof plan.outline === 'string') {
      try {
        return JSON.parse(plan.outline);
      } catch {
        return [];
      }
    }
    return [];
  }, [plan.outline]);

  const startTheorySupplement = async () => {
    if (!plan.id || theoryTaskId) return;
    try {
      const res = await api.theorySupplementPlan(plan.id);
      setTheoryTaskId(res.task_id);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handleTheoryComplete = useCallback((result: any) => {
    setTheoryTaskId(null);
    if (result) {
      setTheoryResult(result);
    }
  }, []);

  return (
    <div className="space-y-6">
      <div className="bg-bg-card rounded-lg p-6 border border-slate-700">
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-2">
          Thesis Statement
        </h3>
        <p className="text-text-primary leading-relaxed">{plan.thesis_statement}</p>
      </div>

      <div className="space-y-3">
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">
          Outline ({outline.length} sections)
        </h3>
        {outline.map((section, i) => {
          const availableCount = section.secondary_sources?.length ?? 0;
          const missingCount = section.missing_references?.length ?? 0;

          return (
            <div
              key={i}
              className="bg-bg-card rounded-lg p-5 border border-slate-700"
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="font-semibold text-text-primary text-sm">
                  {i + 1}. {section.title}
                </h4>
                <span className="text-xs text-text-muted flex-shrink-0 ml-2">
                  ~{section.estimated_words} words
                </span>
              </div>
              <div className="text-xs text-text-secondary mb-3">
                <span className="text-accent font-medium">Probl&eacute;matique:</span>{' '}
                {section.argument}
              </div>

              {section.primary_texts?.length > 0 && (
                <div className="mb-2">
                  <span className="text-[10px] font-medium text-accent uppercase">Primary Texts:</span>
                  <p className="text-xs text-text-muted mt-0.5">
                    {section.primary_texts.join('; ')}
                  </p>
                </div>
              )}
              {availableCount > 0 && (
                <div className="mb-2">
                  <span className="text-[10px] font-medium text-text-muted uppercase">
                    Secondary Sources ({availableCount} available):
                  </span>
                  <p className="text-xs text-text-muted mt-0.5">
                    {section.secondary_sources.join('; ')}
                  </p>
                </div>
              )}
              {missingCount > 0 && (
                <div>
                  <span className="text-[10px] font-medium text-warning uppercase">
                    Missing References ({missingCount}):
                  </span>
                  <div className="mt-0.5 space-y-0.5">
                    {section.missing_references!.map((ref, j) => (
                      <div key={j} className="flex items-start gap-1.5 text-xs text-warning/80">
                        <span className="flex-shrink-0 mt-0.5">{'\u2717'}</span>
                        <span>{ref}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {plan.primary_text_report && plan.primary_text_report.missing.length > 0 && (
        <div className="bg-warning/5 border border-warning/30 rounded-lg p-5">
          <h3 className="text-sm font-medium text-warning mb-3">Missing Primary Texts</h3>
          <div className="space-y-2">
            {plan.primary_text_report.missing.map((m, i) => (
              <div key={i} className="text-xs">
                <span className="text-text-primary font-medium">{m.text_name}</span>
                <span className="text-text-muted ml-2">
                  Needed in: {m.sections_needing.join(', ')}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <p className="text-xs text-text-muted mb-3">
              Upload these texts as PDFs to improve manuscript quality:
            </p>
            <UploadZone onUpload={onUpload} />
          </div>
        </div>
      )}

      {/* Theory supplement section */}
      <div className="space-y-3">
        {theoryResult ? (
          <TheoryPanel result={theoryResult} />
        ) : (
          <>
            <TaskProgress
              taskId={theoryTaskId}
              onComplete={handleTheoryComplete}
              label="Supplementing theoretical framework..."
            />
            {!theoryTaskId && (
              <button
                onClick={startTheorySupplement}
                className="px-4 py-2 border border-slate-600 text-text-secondary text-sm rounded-lg hover:bg-bg-hover hover:text-text-primary transition-colors"
              >
                Supplement Theoretical Framework
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
