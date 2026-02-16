'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useTask } from '@/hooks/useTask';
import type { PlanMessage } from '@/lib/types';

interface Props {
  planId: string;
  onPlanUpdated: (plan: any) => void;
}

let msgCounter = 0;
function nextId() {
  return `msg-${Date.now()}-${++msgCounter}`;
}

export default function PlanChat({ planId, onPlanUpdated }: Props) {
  const [messages, setMessages] = useState<PlanMessage[]>([
    {
      id: nextId(),
      role: 'system',
      content: 'Plan created. Describe any changes you\'d like.',
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState('');
  const [refineTaskId, setRefineTaskId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const task = useTask(refineTaskId);

  // Auto-scroll on new messages or task updates
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, task]);

  // Handle task completion
  const completedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!task || !refineTaskId) return;
    if (task.status === 'completed' && task.result && completedRef.current !== refineTaskId) {
      completedRef.current = refineTaskId;
      const result = task.result as { plan: any; message: string };
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: result.message || 'Plan updated.',
          timestamp: Date.now(),
        },
      ]);
      onPlanUpdated(result.plan);
      setRefineTaskId(null);
    }
    if (task.status === 'failed') {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: `Refinement failed: ${task.error || 'Unknown error'}. Please try again.`,
          timestamp: Date.now(),
        },
      ]);
      setRefineTaskId(null);
    }
  }, [task, refineTaskId, onPlanUpdated]);

  const handleSubmit = useCallback(async () => {
    const text = input.trim();
    if (!text || refineTaskId) return;

    const userMsg: PlanMessage = {
      id: nextId(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');

    // Build conversation history from prior user/assistant messages (exclude system)
    const history = messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const res = await api.refinePlan(planId, text, history);
      completedRef.current = null;
      setRefineTaskId(res.task_id);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'assistant',
          content: `Error: ${e.message}`,
          timestamp: Date.now(),
        },
      ]);
    }
  }, [input, refineTaskId, messages, planId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="bg-bg-card rounded-lg border border-slate-700 overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700">
        <h3 className="text-sm font-medium text-text-muted uppercase tracking-wider">
          Refine Plan
        </h3>
      </div>

      {/* Message list */}
      <div className="max-h-72 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-accent/15 text-text-primary'
                  : msg.role === 'system'
                    ? 'bg-slate-700/50 text-text-muted italic'
                    : 'bg-slate-700/80 text-text-secondary'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {/* Thinking indicator */}
        {refineTaskId && task && task.status !== 'completed' && task.status !== 'failed' && (
          <div className="flex justify-start">
            <div className="bg-slate-700/80 rounded-lg px-3 py-2 text-sm text-text-muted flex items-center gap-2">
              <div className="w-3 h-3 border-2 border-accent border-t-transparent rounded-full animate-spin" />
              <span>{task.message || 'Refining plan...'}</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-slate-700 px-4 py-3 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Describe changes to the plan..."
          disabled={!!refineTaskId}
          className="flex-1 bg-bg-primary border border-slate-600 rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent disabled:opacity-50"
        />
        <button
          onClick={handleSubmit}
          disabled={!input.trim() || !!refineTaskId}
          className="px-4 py-2 bg-accent text-bg-primary text-sm font-medium rounded-lg hover:bg-accent-dim disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
}
