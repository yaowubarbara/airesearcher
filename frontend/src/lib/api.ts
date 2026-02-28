const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  // Domain endpoints
  getDomains: () =>
    fetchJSON<{ domains: import('./types').Domain[] }>('/api/domains'),

  // Journal endpoints
  getJournals: (domain?: string) =>
    fetchJSON<{ journals: import('./types').Journal[] }>(
      `/api/journals${domain ? `?domain=${domain}` : ''}`
    ),

  getJournalProfile: (name: string) =>
    fetchJSON<{ name: string; is_active: boolean; profile: unknown }>(
      `/api/journals/${encodeURIComponent(name)}/profile`
    ),

  // Discovery endpoints
  startDiscovery: (journal: string, domain?: string) =>
    fetchJSON<{ task_id: string }>('/api/discover', {
      method: 'POST',
      body: JSON.stringify({ journal, domain: domain || 'comparative_literature' }),
    }),

  getDiscoveryStatus: () =>
    fetchJSON<{
      total_papers: number;
      annotated: number;
      unannotated: number;
      directions: number;
      topics: number;
    }>('/api/discover/status'),

  getDirections: (limit?: number) =>
    fetchJSON<{ directions: import('./types').Direction[] }>(
      `/api/directions?limit=${limit || 20}`
    ),

  getTopics: (directionId?: string) =>
    fetchJSON<{ topics: import('./types').Topic[] }>(
      `/api/topics${directionId ? `?direction_id=${directionId}` : ''}`
    ),

  // Task polling
  getTaskStatus: (taskId: string) =>
    fetchJSON<import('./types').TaskStatus>(`/api/tasks/${taskId}`),
};
