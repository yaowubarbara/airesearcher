'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface UsageEntry {
  model: string;
  task_type: string;
  calls: number;
  tokens: number;
  cost: number;
}

interface StatsResponse {
  papers_indexed: number;
  topics_discovered: number;
  llm_usage: Record<string, UsageEntry>;
}

export default function StatsPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/stats')
      .then(r => r.json())
      .then(setStats)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-6 h-6 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="bg-error/10 border border-error/30 rounded-lg p-4 text-sm text-error">
          Failed to load stats: {error}
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const entries = Object.values(stats.llm_usage || {});
  const totalTokens = entries.reduce((s, e) => s + e.tokens, 0);
  const totalCost = entries.reduce((s, e) => s + e.cost, 0);
  const totalCalls = entries.reduce((s, e) => s + e.calls, 0);

  // Group by model
  const byModel = new Map<string, { tokens: number; cost: number; calls: number }>();
  for (const e of entries) {
    const existing = byModel.get(e.model) || { tokens: 0, cost: 0, calls: 0 };
    existing.tokens += e.tokens;
    existing.cost += e.cost;
    existing.calls += e.calls;
    byModel.set(e.model, existing);
  }

  // Group by task
  const byTask = new Map<string, { tokens: number; cost: number; calls: number }>();
  for (const e of entries) {
    const existing = byTask.get(e.task_type) || { tokens: 0, cost: 0, calls: 0 };
    existing.tokens += e.tokens;
    existing.cost += e.cost;
    existing.calls += e.calls;
    byTask.set(e.task_type, existing);
  }

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-text-primary">Usage Statistics</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="Papers Indexed" value={stats.papers_indexed.toLocaleString()} />
        <StatCard label="Topics Discovered" value={stats.topics_discovered.toString()} />
        <StatCard label="Total Tokens" value={totalTokens.toLocaleString()} />
        <StatCard label="LLM Calls" value={totalCalls.toString()} />
      </div>

      {/* By model */}
      {byModel.size > 0 && (
        <div className="bg-bg-card rounded-lg p-6 border border-border">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">Usage by Model</h3>
          <div className="space-y-3">
            {Array.from(byModel.entries())
              .sort((a, b) => b[1].tokens - a[1].tokens)
              .map(([model, data]) => (
                <div key={model} className="flex items-center justify-between">
                  <span className="text-sm text-text-primary font-mono">{model}</span>
                  <div className="text-sm text-text-secondary">
                    <span>{data.calls} calls</span>
                    <span className="text-text-muted mx-2">|</span>
                    <span>{data.tokens.toLocaleString()} tokens</span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* By task */}
      {byTask.size > 0 && (
        <div className="bg-bg-card rounded-lg p-6 border border-border">
          <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">Usage by Task</h3>
          <div className="space-y-3">
            {Array.from(byTask.entries())
              .sort((a, b) => b[1].tokens - a[1].tokens)
              .map(([task, data]) => (
                <div key={task} className="flex items-center justify-between">
                  <span className="text-sm text-text-primary">{task.replace(/_/g, ' ')}</span>
                  <div className="text-sm text-text-secondary">
                    <span>{data.calls} calls</span>
                    <span className="text-text-muted mx-2">|</span>
                    <span>{data.tokens.toLocaleString()} tokens</span>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-bg-card rounded-lg p-5 border border-border">
      <p className="text-xs text-text-muted uppercase tracking-wider">{label}</p>
      <p className="text-2xl font-bold text-text-primary mt-1">{value}</p>
    </div>
  );
}
