'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { usePipelineStore } from '@/lib/store';
import PlanOutline from '@/components/PlanOutline';
import PlanChat from '@/components/PlanChat';
import TaskProgress from '@/components/TaskProgress';
import ReadinessPanel from '@/components/ReadinessPanel';
import ReferencePicker from '@/components/ReferencePicker';
import UploadZone from '@/components/UploadZone';
import ManualAddForm from '@/components/ManualAddForm';
import type { ResearchPlan, Topic, SearchSession, ReadinessReport } from '@/lib/types';

export default function PlanPage() {
  const router = useRouter();
  const {
    selectedTopicId, selectedJournal, currentPlanId, selectedSessionId,
    setPlanId, selectSession, activeTaskId, setActiveTaskId, setStage,
  } = usePipelineStore();

  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<SearchSession[]>([]);
  const [topic, setTopic] = useState<Topic | null>(null);
  const [readiness, setReadiness] = useState<ReadinessReport | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [chatKey, setChatKey] = useState(0);
  const [showPicker, setShowPicker] = useState(false);

  const triggerReadinessCheck = useCallback(() => {
    const sessionId = selectedSessionId || undefined;
    const topicId = (!selectedSessionId && selectedTopicId) ? selectedTopicId : undefined;
    if (!sessionId && !topicId) {
      setReadiness(null);
      return;
    }
    setReadinessLoading(true);
    setReadiness(null);
    api.checkPlanReadiness({ sessionId, topicId })
      .then((data) => setReadiness(data))
      .catch(() => setReadiness(null))
      .finally(() => setReadinessLoading(false));
  }, [selectedSessionId, selectedTopicId]);

  useEffect(() => {
    setStage('plan');

    // Load existing plan if we have an ID
    if (currentPlanId) {
      setLoading(true);
      api.getPlan(currentPlanId)
        .then((data) => setPlan(data))
        .catch(() => {})
        .finally(() => setLoading(false));
    }

    // Load search sessions for context
    api.getSearchSessions()
      .then((data) => setSessions(data.sessions))
      .catch(() => {});

    // Load selected topic details
    if (selectedTopicId) {
      api.getTopics(undefined, 100)
        .then((data) => {
          const found = data.topics.find((t) => t.id === selectedTopicId);
          if (found) setTopic(found);
        })
        .catch(() => {});
    }
  }, [setStage, currentPlanId, selectedTopicId]);

  // Fire readiness check when session or topic changes
  useEffect(() => {
    if (plan) return; // Don't check if plan already exists
    triggerReadinessCheck();
  }, [selectedSessionId, selectedTopicId, plan, triggerReadinessCheck]);

  const createPlan = async (selectedReferenceIds?: string[]) => {
    if (!selectedJournal) return;

    // For session-based plans, show the reference picker first (unless called with ids)
    if (selectedSessionId && !selectedReferenceIds) {
      setShowPicker(true);
      return;
    }

    try {
      let taskId: string;
      if (selectedSessionId) {
        const res = await api.createPlanFromSession(
          selectedSessionId, selectedJournal, 'en', selectedReferenceIds
        );
        taskId = res.task_id;
      } else if (selectedTopicId) {
        const res = await api.createPlan(selectedTopicId, selectedJournal);
        taskId = res.task_id;
      } else {
        return;
      }
      setShowPicker(false);
      setActiveTaskId(taskId);
    } catch (e: any) {
      alert(e.message);
    }
  };

  const handlePlanComplete = useCallback((result: any) => {
    setActiveTaskId(null);
    if (result?.id) {
      setPlanId(result.id);
      setPlan(result);
    }
  }, [setActiveTaskId, setPlanId]);

  const handlePlanRefined = useCallback((updatedPlan: any) => {
    if (updatedPlan) {
      setPlan(updatedPlan);
    }
  }, []);

  const handleProceed = () => {
    if (currentPlanId) {
      router.push('/pipeline/write');
    }
  };

  const canCreate = !!selectedJournal && (!!selectedTopicId || !!selectedSessionId);
  const selectedSession = sessions.find((s) => s.id === selectedSessionId);

  // Determine the basis label
  let basisLabel = '';
  if (selectedSessionId && selectedSession) {
    basisLabel = `Search: "${selectedSession.query}"`;
  } else if (topic) {
    basisLabel = `Topic: ${topic.title}`;
  }

  const isNotReady = readiness && readiness.status !== 'ready';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Research Plan</h2>
          <p className="text-sm text-text-secondary mt-1">
            Generate a detailed outline with thesis statement and section structure.
          </p>
        </div>
      </div>

      <TaskProgress
        taskId={activeTaskId}
        onComplete={handlePlanComplete}
        label="Creating research plan..."
      />

      {loading ? (
        <div className="flex justify-center py-10">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      ) : plan ? (
        <>
          <PlanOutline plan={plan} onUpload={() => {
            // Refresh plan after upload to re-check primary texts
            if (currentPlanId) {
              api.getPlan(currentPlanId).then(setPlan).catch(() => {});
            }
          }} />
          {plan.id && (
            <PlanChat key={chatKey} planId={plan.id} onPlanUpdated={handlePlanRefined} />
          )}
          <div className="flex justify-between pt-4 border-t border-slate-700">
            <button
              onClick={() => { setPlan(null); setChatKey((k) => k + 1); }}
              disabled={!!activeTaskId}
              className="px-4 py-2 border border-slate-600 text-text-secondary text-sm rounded-lg hover:bg-bg-hover transition-colors"
            >
              New Plan
            </button>
            <button
              onClick={handleProceed}
              className="px-6 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim transition-colors"
            >
              Approve &amp; Write
            </button>
          </div>
        </>
      ) : (
        <div className="space-y-6">
          {/* Context: selected topic */}
          {topic && (
            <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] font-medium text-accent uppercase tracking-wider">Selected Topic</span>
                {!selectedSessionId && (
                  <span className="text-[10px] bg-accent/15 text-accent px-1.5 py-0.5 rounded">active</span>
                )}
              </div>
              <h4 className="text-sm font-semibold text-text-primary">{topic.title}</h4>
              <p className="text-xs text-text-secondary mt-1">{topic.research_question}</p>
              {selectedSessionId && (
                <button
                  onClick={() => selectSession(null)}
                  className="text-xs text-accent hover:underline mt-2"
                >
                  Use this topic instead
                </button>
              )}
            </div>
          )}

          {/* Search sessions */}
          {sessions.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-3">
                Search Sessions
              </h3>
              <div className="space-y-2">
                {sessions.map((s) => {
                  const isSelected = selectedSessionId === s.id;
                  return (
                    <button
                      key={s.id}
                      onClick={() => selectSession(isSelected ? null : s.id)}
                      className={`w-full text-left rounded-lg p-4 border transition-colors ${
                        isSelected
                          ? 'border-accent bg-accent/5'
                          : 'border-slate-700 bg-bg-card hover:border-slate-500'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-text-primary truncate">
                            {s.query}
                          </p>
                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-xs text-text-muted">
                              {s.total_papers} papers found
                            </span>
                            <span className={`text-xs ${s.indexed_count > 0 ? 'text-success' : 'text-warning'}`}>
                              {s.indexed_count} indexed
                            </span>
                            <span className="text-xs text-text-muted">
                              {new Date(s.created_at).toLocaleDateString()}
                            </span>
                          </div>
                          {s.indexed_count === 0 && (
                            <p className="text-[11px] text-warning mt-1">
                              No papers indexed — plan quality may be limited
                            </p>
                          )}
                        </div>
                        {isSelected && (
                          <span className="text-xs bg-accent/15 text-accent px-1.5 py-0.5 rounded flex-shrink-0">
                            selected
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Upload & Add References — always visible */}
          <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
            <h3 className="text-sm font-medium text-text-primary mb-3">Upload &amp; Add References</h3>
            <div className="space-y-4">
              <UploadZone onUpload={() => triggerReadinessCheck()} />
              <div className="flex items-center gap-3">
                <div className="flex-1 border-t border-slate-700" />
                <span className="text-xs text-text-muted">or add by metadata</span>
                <div className="flex-1 border-t border-slate-700" />
              </div>
              <ManualAddForm compact onAdded={() => triggerReadinessCheck()} />
            </div>
          </div>

          {/* Readiness check */}
          <ReadinessPanel
            report={readiness!}
            loading={readinessLoading}
            onRecheck={triggerReadinessCheck}
          />

          {/* Reference Picker — shown when user clicks Create Plan with a session */}
          {showPicker && selectedSessionId && selectedJournal && (
            <ReferencePicker
              sessionId={selectedSessionId}
              journal={selectedJournal}
              onConfirm={(ids) => createPlan(ids)}
              onCancel={() => setShowPicker(false)}
            />
          )}

          {/* Status + Create button — sufficiency gate */}
          <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
            {basisLabel ? (
              <p className="text-sm text-text-secondary mb-4">
                Plan will be based on: <span className="text-text-primary font-medium">{basisLabel}</span>
              </p>
            ) : (
              <p className="text-sm text-text-secondary mb-4">
                Select a search session above, or discover a topic first.
              </p>
            )}

            {isNotReady ? (
              <div className="space-y-3">
                <div className="bg-warning/10 border border-warning/30 rounded-lg px-4 py-3">
                  <p className="text-xs text-warning">
                    Key references are missing. Upload texts above and re-check, or proceed with reduced source coverage.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={triggerReadinessCheck}
                    disabled={!!activeTaskId || readinessLoading}
                    className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Re-check Readiness
                  </button>
                  <button
                    onClick={() => createPlan()}
                    disabled={!!activeTaskId || !canCreate}
                    className="px-5 py-2.5 border border-warning/50 text-warning text-sm font-medium rounded-lg hover:bg-warning/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Create Plan Anyway
                  </button>
                </div>
              </div>
            ) : (
              <>
                <button
                  onClick={() => createPlan()}
                  disabled={!!activeTaskId || !canCreate}
                  className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Create Plan
                </button>
              </>
            )}
            {!selectedJournal && (
              <p className="text-xs text-warning mt-2">Select a journal first (Journal stage).</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
