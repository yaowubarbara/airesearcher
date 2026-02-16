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
import TopicEditor from '@/components/TopicEditor';
import type { ResearchPlan, Topic, SearchSession, ReadinessReport, SynthesizedTopic } from '@/lib/types';

type PlanMode = 'topic' | 'session' | 'corpus' | 'custom';

export default function PlanPage() {
  const router = useRouter();
  const {
    selectedTopicId, selectedJournal, currentPlanId, selectedSessionId,
    setPlanId, selectSession, activeTaskId, setActiveTaskId, setStage,
    uploadedPaperIds, addUploadedPaperId, clearUploadedPaperIds,
  } = usePipelineStore();

  const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<SearchSession[]>([]);
  const [topic, setTopic] = useState<Topic | null>(null);
  const [readiness, setReadiness] = useState<ReadinessReport | null>(null);
  const [readinessLoading, setReadinessLoading] = useState(false);
  const [chatKey, setChatKey] = useState(0);
  const [showPicker, setShowPicker] = useState(false);
  const [mode, setMode] = useState<PlanMode>('topic');

  // Intermediate topic review state
  const [synthesizedTopic, setSynthesizedTopic] = useState<SynthesizedTopic | null>(null);
  const [synthesizeTaskId, setSynthesizeTaskId] = useState<string | null>(null);
  const [selectedReferenceIds, setSelectedReferenceIds] = useState<string[] | null>(null);
  const [planGenerating, setPlanGenerating] = useState(false);
  const [customSessionId, setCustomSessionId] = useState<string | null>(null);

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

  // Auto-select best mode based on available state
  useEffect(() => {
    if (plan) return;
    if (selectedSessionId) {
      setMode('session');
    } else if (selectedTopicId) {
      setMode('topic');
    }
  }, [selectedSessionId, selectedTopicId, plan]);

  // Fire readiness check when session or topic changes (for topic/session modes)
  useEffect(() => {
    if (plan) return;
    if (mode === 'corpus' || mode === 'custom') return;
    triggerReadinessCheck();
  }, [selectedSessionId, selectedTopicId, plan, triggerReadinessCheck, mode]);

  // --- Topic review flow ---

  // "From Topic" mode: clicking "Review Topic" loads topic into editor directly
  const handleReviewTopic = () => {
    if (!topic) return;
    setSynthesizedTopic({
      title: topic.title,
      research_question: topic.research_question,
      gap_description: topic.gap_description,
    });
  };

  // "From Session" mode: clicking "Synthesize Topic" shows picker first
  const handleSynthesizeFromSession = () => {
    if (!selectedSessionId) return;
    setShowPicker(true);
  };

  // After reference picker confirms in session mode
  const handlePickerConfirm = (ids: string[]) => {
    setSelectedReferenceIds(ids);
    setShowPicker(false);
    // Start synthesis task
    api.synthesizeTopic({ session_id: selectedSessionId!, paper_ids: ids })
      .then((res) => setSynthesizeTaskId(res.task_id))
      .catch((e: any) => alert(e.message));
  };

  // "From Corpus" mode: clicking "Synthesize Topic" starts synthesis directly
  const handleSynthesizeFromCorpus = () => {
    if (uploadedPaperIds.length === 0) return;
    api.synthesizeTopic({ paper_ids: uploadedPaperIds })
      .then((res) => setSynthesizeTaskId(res.task_id))
      .catch((e: any) => alert(e.message));
  };

  // When synthesis task completes, show the topic editor
  const handleSynthesisComplete = useCallback((result: any) => {
    setSynthesizeTaskId(null);
    if (result) {
      setSynthesizedTopic({
        title: result.title || '',
        research_question: result.research_question || '',
        gap_description: result.gap_description || '',
        source_paper_ids: result.source_paper_ids,
      });
    }
  }, []);

  // When user confirms the topic editor, generate the plan
  const handleTopicConfirm = async (edited: SynthesizedTopic) => {
    if (!selectedJournal) return;
    setPlanGenerating(true);
    try {
      const editedTopic = {
        title: edited.title,
        research_question: edited.research_question,
        gap_description: edited.gap_description,
      };
      let taskId: string;
      if (mode === 'topic' && selectedTopicId) {
        const res = await api.createPlan(selectedTopicId, selectedJournal, 'en', editedTopic);
        taskId = res.task_id;
      } else if (mode === 'session' && selectedSessionId) {
        const res = await api.createPlanFromSession(
          selectedSessionId, selectedJournal, 'en', selectedReferenceIds ?? undefined, editedTopic
        );
        taskId = res.task_id;
      } else if (mode === 'corpus') {
        const res = await api.createPlanFromUploads(selectedJournal, uploadedPaperIds, 'en', editedTopic);
        taskId = res.task_id;
      } else if (mode === 'custom') {
        const res = await api.createPlanFromCustom({
          title: edited.title,
          research_question: edited.research_question,
          gap_description: edited.gap_description,
          journal: selectedJournal,
          session_id: customSessionId ?? undefined,
        });
        taskId = res.task_id;
      } else {
        return;
      }
      setSynthesizedTopic(null);
      setActiveTaskId(taskId);
    } catch (e: any) {
      alert(e.message);
    } finally {
      setPlanGenerating(false);
    }
  };

  const handleTopicBack = () => {
    setSynthesizedTopic(null);
    setSelectedReferenceIds(null);
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

  const handleCorpusUpload = (result: any) => {
    if (result?.paper_id) {
      addUploadedPaperId(result.paper_id);
    }
  };

  const handleCorpusManualAdd = (result: any) => {
    if (result?.paper_id) {
      addUploadedPaperId(result.paper_id);
    }
  };

  const canCreateTopic = !!selectedJournal && !!selectedTopicId;
  const canCreateSession = !!selectedJournal && !!selectedSessionId;
  const canCreateCorpus = !!selectedJournal && uploadedPaperIds.length > 0;
  const selectedSession = sessions.find((s) => s.id === selectedSessionId);

  const hasTopicMode = !!selectedTopicId;
  const hasSessionMode = sessions.length > 0;

  // Determine the basis label
  let basisLabel = '';
  if (mode === 'session' && selectedSession) {
    basisLabel = `Search: "${selectedSession.query}"`;
  } else if (mode === 'topic' && topic) {
    basisLabel = `Topic: ${topic.title}`;
  } else if (mode === 'corpus' && uploadedPaperIds.length > 0) {
    basisLabel = `Corpus: ${uploadedPaperIds.length} uploaded paper${uploadedPaperIds.length !== 1 ? 's' : ''}`;
  }

  const isNotReady = readiness && readiness.status !== 'ready';

  // Determine visual state:
  // State C: plan exists or plan generation in progress
  // State B: synthesized topic ready for review (no plan yet)
  // State A: pre-synthesis (mode tabs, references, create button)
  const isStateC = !!plan || !!activeTaskId;
  const isSynthesizing = !!synthesizeTaskId;
  const isStateB = !!synthesizedTopic && !isStateC;

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

      {/* Synthesis task progress (separate from plan task) */}
      <TaskProgress
        taskId={synthesizeTaskId}
        onComplete={handleSynthesisComplete}
        label="Synthesizing topic..."
      />

      {/* Plan generation task progress */}
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
        /* ============ State C: Plan display ============ */
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
      ) : isStateB ? (
        /* ============ State B: Topic review/edit ============ */
        <TopicEditor
          initialTopic={synthesizedTopic!}
          onConfirm={handleTopicConfirm}
          onBack={handleTopicBack}
          loading={planGenerating}
        />
      ) : (
        /* ============ State A: Pre-synthesis ============ */
        <div className="space-y-6">
          {/* Mode switcher tabs */}
          <div className="flex border-b border-slate-700">
            <button
              onClick={() => setMode('topic')}
              disabled={!hasTopicMode}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                mode === 'topic'
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text-secondary'
              } ${!hasTopicMode ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              From Topic
            </button>
            <button
              onClick={() => setMode('session')}
              disabled={!hasSessionMode}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                mode === 'session'
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text-secondary'
              } ${!hasSessionMode ? 'opacity-40 cursor-not-allowed' : ''}`}
            >
              From Search
            </button>
            <button
              onClick={() => setMode('corpus')}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                mode === 'corpus'
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text-secondary'
              }`}
            >
              From Corpus
            </button>
            <button
              onClick={() => setMode('custom')}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                mode === 'custom'
                  ? 'border-accent text-accent'
                  : 'border-transparent text-text-muted hover:text-text-secondary'
              }`}
            >
              Custom Topic
            </button>
          </div>

          {/* ============ FROM TOPIC mode ============ */}
          {mode === 'topic' && (
            <>
              {topic && (
                <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-[10px] font-medium text-accent uppercase tracking-wider">Selected Topic</span>
                    <span className="text-[10px] bg-accent/15 text-accent px-1.5 py-0.5 rounded">active</span>
                  </div>
                  <h4 className="text-sm font-semibold text-text-primary">{topic.title}</h4>
                  <p className="text-xs text-text-secondary mt-1">{topic.research_question}</p>
                </div>
              )}

              {/* Upload & Add References */}
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

              <ReadinessPanel
                report={readiness!}
                loading={readinessLoading}
                onRecheck={triggerReadinessCheck}
              />
            </>
          )}

          {/* ============ FROM SESSION mode ============ */}
          {mode === 'session' && (
            <>
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

              {/* Upload & Add References */}
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

              <ReadinessPanel
                report={readiness!}
                loading={readinessLoading}
                onRecheck={triggerReadinessCheck}
              />

              {/* Reference Picker — shown when user clicks Synthesize Topic in session mode */}
              {showPicker && selectedSessionId && selectedJournal && (
                <ReferencePicker
                  sessionId={selectedSessionId}
                  journal={selectedJournal}
                  onConfirm={handlePickerConfirm}
                  onCancel={() => setShowPicker(false)}
                />
              )}
            </>
          )}

          {/* ============ FROM CORPUS mode ============ */}
          {mode === 'corpus' && (
            <div className="space-y-4">
              <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
                <h3 className="text-sm font-medium text-text-primary mb-1">Upload Your Corpus</h3>
                <p className="text-xs text-text-secondary mb-4">
                  Upload PDFs directly. The system will auto-generate a problematique and research plan from your corpus.
                </p>
                <UploadZone onUpload={handleCorpusUpload} />

                <div className="flex items-center gap-3 my-4">
                  <div className="flex-1 border-t border-slate-700" />
                  <span className="text-xs text-text-muted">or add by DOI</span>
                  <div className="flex-1 border-t border-slate-700" />
                </div>
                <ManualAddForm compact onAdded={handleCorpusManualAdd} />
              </div>

              {uploadedPaperIds.length > 0 && (
                <div className="bg-bg-card rounded-lg p-4 border border-slate-700 flex items-center justify-between">
                  <span className="text-sm text-text-primary">
                    <span className="font-medium text-accent">{uploadedPaperIds.length}</span>
                    {' '}paper{uploadedPaperIds.length !== 1 ? 's' : ''} in corpus
                  </span>
                  <button
                    onClick={clearUploadedPaperIds}
                    className="text-xs text-text-muted hover:text-error transition-colors"
                  >
                    Clear all
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ============ CUSTOM TOPIC mode ============ */}
          {mode === 'custom' && (
            <div className="space-y-4">
              <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
                <h3 className="text-sm font-medium text-text-primary mb-1">Define Your Topic</h3>
                <p className="text-xs text-text-secondary mb-4">
                  Enter your research topic directly. Optionally link a search session to ground the plan in collected references.
                </p>

                {sessions.length > 0 && (
                  <div className="mb-4">
                    <label className="block text-xs font-medium text-text-muted uppercase tracking-wider mb-1.5">
                      Link References (optional)
                    </label>
                    <select
                      value={customSessionId || ''}
                      onChange={(e) => setCustomSessionId(e.target.value || null)}
                      className="w-full px-3 py-2 bg-bg-primary border border-slate-600 rounded-lg text-sm text-text-primary focus:outline-none focus:border-accent"
                    >
                      <option value="">No linked session</option>
                      {sessions.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.query} ({s.total_papers} papers, {s.indexed_count} indexed)
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {!selectedJournal ? (
                <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
                  <p className="text-xs text-warning">Select a journal first (Journal stage).</p>
                </div>
              ) : (
                <TopicEditor
                  initialTopic={{ title: '', research_question: '', gap_description: '' }}
                  onConfirm={handleTopicConfirm}
                  onBack={() => setMode(hasSessionMode ? 'session' : 'topic')}
                  loading={planGenerating}
                />
              )}
            </div>
          )}

          {/* Status + Create button — sufficiency gate */}
          {!isSynthesizing && mode !== 'custom' && (
            <div className="bg-bg-card rounded-lg p-5 border border-slate-700">
              {basisLabel ? (
                <p className="text-sm text-text-secondary mb-4">
                  Plan will be based on: <span className="text-text-primary font-medium">{basisLabel}</span>
                </p>
              ) : (
                <p className="text-sm text-text-secondary mb-4">
                  {mode === 'corpus'
                    ? 'Upload PDFs above to build your corpus.'
                    : mode === 'session'
                      ? 'Select a search session above.'
                      : 'Select a topic from the Discover stage.'}
                </p>
              )}

              {mode === 'corpus' ? (
                <button
                  onClick={handleSynthesizeFromCorpus}
                  disabled={!!synthesizeTaskId || !canCreateCorpus}
                  className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  Synthesize Topic
                </button>
              ) : mode === 'session' ? (
                isNotReady ? (
                  <div className="space-y-3">
                    <div className="bg-warning/10 border border-warning/30 rounded-lg px-4 py-3">
                      <p className="text-xs text-warning">
                        Key references are missing. Upload texts above and re-check, or proceed with reduced source coverage.
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={triggerReadinessCheck}
                        disabled={!!synthesizeTaskId || readinessLoading}
                        className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Re-check Readiness
                      </button>
                      <button
                        onClick={handleSynthesizeFromSession}
                        disabled={!!synthesizeTaskId || !canCreateSession}
                        className="px-5 py-2.5 border border-warning/50 text-warning text-sm font-medium rounded-lg hover:bg-warning/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Synthesize Topic Anyway
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={handleSynthesizeFromSession}
                    disabled={!!synthesizeTaskId || !canCreateSession}
                    className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Synthesize Topic
                  </button>
                )
              ) : (
                /* topic mode */
                isNotReady ? (
                  <div className="space-y-3">
                    <div className="bg-warning/10 border border-warning/30 rounded-lg px-4 py-3">
                      <p className="text-xs text-warning">
                        Key references are missing. Upload texts above and re-check, or proceed with reduced source coverage.
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={triggerReadinessCheck}
                        disabled={readinessLoading}
                        className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Re-check Readiness
                      </button>
                      <button
                        onClick={handleReviewTopic}
                        disabled={!canCreateTopic}
                        className="px-5 py-2.5 border border-warning/50 text-warning text-sm font-medium rounded-lg hover:bg-warning/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Review Topic Anyway
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={handleReviewTopic}
                    disabled={!canCreateTopic}
                    className="px-5 py-2.5 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Review Topic
                  </button>
                )
              )}
              {!selectedJournal && (
                <p className="text-xs text-warning mt-2">Select a journal first (Journal stage).</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
