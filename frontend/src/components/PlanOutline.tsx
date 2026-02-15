'use client';

import type { ResearchPlan } from '@/lib/types';

interface Props {
  plan: ResearchPlan;
}

export default function PlanOutline({ plan }: Props) {
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
          Outline ({plan.outline.length} sections)
        </h3>
        {plan.outline.map((section, i) => (
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
            <p className="text-xs text-text-secondary mb-3">{section.argument}</p>

            {section.primary_texts.length > 0 && (
              <div className="mb-2">
                <span className="text-[10px] font-medium text-accent uppercase">Primary Texts:</span>
                <p className="text-xs text-text-muted mt-0.5">
                  {section.primary_texts.join('; ')}
                </p>
              </div>
            )}
            {section.secondary_sources.length > 0 && (
              <div>
                <span className="text-[10px] font-medium text-text-muted uppercase">Secondary Sources:</span>
                <p className="text-xs text-text-muted mt-0.5">
                  {section.secondary_sources.join('; ')}
                </p>
              </div>
            )}
          </div>
        ))}
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
          <p className="text-xs text-text-muted mt-3">
            Upload these texts in the References stage to improve manuscript quality.
          </p>
        </div>
      )}
    </div>
  );
}
