const API_BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || err.error || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Journals
  getJournals: () => request<{ journals: import('./types').Journal[] }>('/journals'),
  getJournalProfile: (name: string) =>
    request<{ name: string; is_active: boolean; profile: any }>(`/journals/${encodeURIComponent(name)}/profile`),

  // Discovery
  startDiscovery: (journal: string, limit = 200) =>
    request<{ task_id: string }>('/discover', {
      method: 'POST',
      body: JSON.stringify({ journal, limit }),
    }),
  getAnnotationStatus: () =>
    request<import('./types').AnnotationStatus>('/discover/status'),
  getDirections: (limit = 20) =>
    request<{ directions: import('./types').ProblematiqueDirection[] }>(
      `/directions?limit=${limit}`
    ),
  getDirectionWithTopics: (id: string) =>
    request<import('./types').DirectionWithTopics>(`/directions/${encodeURIComponent(id)}`),
  getTopics: (status?: string, limit = 20, directionId?: string) =>
    request<{ topics: import('./types').Topic[] }>(
      `/topics?limit=${limit}${status ? `&status=${status}` : ''}${directionId ? `&direction_id=${directionId}` : ''}`
    ),

  // References
  searchReferences: (topic: string, maxResults = 50) =>
    request<{ task_id: string }>('/references/search', {
      method: 'POST',
      body: JSON.stringify({ topic, max_results: maxResults }),
    }),
  uploadPdf: async (file: File, sessionId?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (sessionId) form.append('session_id', sessionId);
    const res = await fetch(`${API_BASE}/references/upload`, { method: 'POST', body: form });
    if (!res.ok) throw new Error(`Upload failed: ${res.statusText}`);
    return res.json();
  },
  getWishlist: () =>
    request<import('./types').WishlistResponse>('/references/wishlist'),
  getDownloaded: () =>
    request<import('./types').DownloadedResponse>('/references/downloaded'),
  getPdfUrl: (paperId: string) => `${API_BASE}/references/pdf/${paperId}`,
  getSearchSessions: () =>
    request<{ sessions: import('./types').SearchSession[] }>('/references/sessions'),
  getSessionPapers: (sessionId: string) =>
    request<{ papers: import('./types').SessionPaper[] }>(`/references/sessions/${encodeURIComponent(sessionId)}/papers`),
  browserDownload: (sessionId?: string, limit = 20) =>
    request<{ task_id: string }>('/references/browser-download', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, limit }),
    }),
  addByDoi: (doi: string, refType?: string, sessionId?: string) =>
    request<import('./types').ManualAddResult>('/references/add-by-doi', {
      method: 'POST',
      body: JSON.stringify({ doi, ref_type: refType, session_id: sessionId }),
    }),
  addManual: (data: {
    title: string; authors?: string[]; year?: number; journal?: string;
    doi?: string; volume?: string; issue?: string; pages?: string;
    publisher?: string; ref_type?: string; session_id?: string;
  }) =>
    request<import('./types').ManualAddResult>('/references/add-manual', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  crossrefSearch: (query: string, rows = 10) =>
    request<{ results: import('./types').CrossRefMatch[]; total: number }>('/references/crossref-search', {
      method: 'POST',
      body: JSON.stringify({ query, rows }),
    }),

  // Plan
  synthesizeTopic: (params: { session_id?: string; paper_ids?: string[]; hint?: string }) =>
    request<{ task_id: string }>('/plan/synthesize-topic', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
  createPlan: (topicId: string, journal: string, language = 'en', editedTopic?: { title: string; research_question: string; gap_description: string }) =>
    request<{ task_id: string }>('/plan', {
      method: 'POST',
      body: JSON.stringify({
        topic_id: topicId, journal, language,
        ...(editedTopic ? {
          edited_title: editedTopic.title,
          edited_research_question: editedTopic.research_question,
          edited_gap_description: editedTopic.gap_description,
        } : {}),
      }),
    }),
  createPlanFromSession: (sessionId: string, journal: string, language = 'en', referenceIds?: string[], editedTopic?: { title: string; research_question: string; gap_description: string }) =>
    request<{ task_id: string }>('/plan/from-session', {
      method: 'POST',
      body: JSON.stringify({
        session_id: sessionId, journal, language, reference_ids: referenceIds,
        ...(editedTopic ? {
          edited_title: editedTopic.title,
          edited_research_question: editedTopic.research_question,
          edited_gap_description: editedTopic.gap_description,
        } : {}),
      }),
    }),
  createPlanFromUploads: (journal: string, paperIds: string[], language = 'en', editedTopic?: { title: string; research_question: string; gap_description: string }) =>
    request<{ task_id: string }>('/plan/from-uploads', {
      method: 'POST',
      body: JSON.stringify({
        journal, paper_ids: paperIds, language,
        ...(editedTopic ? {
          edited_title: editedTopic.title,
          edited_research_question: editedTopic.research_question,
          edited_gap_description: editedTopic.gap_description,
        } : {}),
      }),
    }),
  createPlanFromCustom: (params: {
    title: string; research_question: string; gap_description: string;
    journal: string; language?: string; session_id?: string; reference_ids?: string[];
  }) =>
    request<{ task_id: string }>('/plan/from-custom', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
  getPlan: (planId: string) => request<import('./types').ResearchPlan>(`/plans/${planId}`),
  checkPlanReadiness: (params: { sessionId?: string; topicId?: string; query?: string }) =>
    request<import('./types').ReadinessReport>('/plan/readiness-check', {
      method: 'POST',
      body: JSON.stringify({
        session_id: params.sessionId,
        topic_id: params.topicId,
        query: params.query,
      }),
    }),
  refinePlan: (planId: string, feedback: string, history: { role: string; content: string }[]) =>
    request<{ task_id: string }>(`/plans/${planId}/refine`, {
      method: 'POST',
      body: JSON.stringify({ feedback, conversation_history: history }),
    }),
  theorySupplementPlan: (planId: string) =>
    request<{ task_id: string }>(`/plans/${planId}/theory-supplement`, {
      method: 'POST',
    }),

  // Write
  startWriting: (planId: string) =>
    request<{ task_id: string }>(`/write/${planId}`, { method: 'POST' }),
  getManuscript: (msId: string) => request<import('./types').Manuscript>(`/manuscripts/${msId}`),

  // Review
  startReview: (msId: string) =>
    request<{ task_id: string }>(`/review/${msId}`, { method: 'POST' }),
  getReview: (msId: string) => request<any>(`/reviews/${msId}`),

  // Submit
  formatSubmission: (msId: string) =>
    request<{ task_id: string }>(`/submit/${msId}`, { method: 'POST' }),

  // Tasks
  getTaskStatus: (taskId: string) => request<import('./types').TaskProgress>(`/tasks/${taskId}`),

  // Stats
  getStats: () => request<import('./types').StatsData>('/stats'),
};
