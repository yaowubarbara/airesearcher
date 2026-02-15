'use client';

import { useTask } from '@/hooks/useTask';
import type { TaskProgress as TaskProgressType } from '@/lib/types';

interface Props {
  taskId: string | null;
  onComplete?: (result: any) => void;
  label?: string;
}

export default function TaskProgress({ taskId, onComplete, label }: Props) {
  const task = useTask(taskId);

  if (!taskId || !task) return null;

  // Fire onComplete callback
  if (task.status === 'completed' && task.result && onComplete) {
    // Use setTimeout to avoid calling during render
    setTimeout(() => onComplete(task.result), 0);
  }

  const percentage = Math.round(task.progress * 100);

  return (
    <div className="bg-bg-card rounded-lg p-6 border border-slate-700">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-text-primary">
          {label || 'Processing...'}
        </span>
        <span className="text-xs text-text-secondary">{percentage}%</span>
      </div>

      <div className="w-full bg-slate-700 rounded-full h-2 mb-3">
        <div
          className="bg-accent h-2 rounded-full transition-all duration-500"
          style={{ width: `${percentage}%` }}
        />
      </div>

      <p className="text-sm text-text-secondary">{task.message}</p>

      {task.status === 'failed' && (
        <div className="mt-3 p-3 bg-error/10 border border-error/30 rounded text-sm text-error">
          {task.error || 'Task failed'}
        </div>
      )}
    </div>
  );
}
