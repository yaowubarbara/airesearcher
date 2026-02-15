'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import type { TaskProgress } from '@/lib/types';

export function useTask(taskId: string | null) {
  const [task, setTask] = useState<TaskProgress | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const cleanup = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      return;
    }

    let cancelled = false;

    // Try WebSocket first
    const wsUrl = `ws://${window.location.hostname}:8001/api/ws/tasks/${taskId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      if (cancelled) return;
      try {
        const data = JSON.parse(event.data);
        setTask({
          taskId: data.taskId || taskId,
          status: data.status,
          progress: data.progress,
          message: data.message || '',
          result: data.result,
          error: data.error,
        });
      } catch {}
    };

    ws.onerror = () => {
      // Fallback to polling
      ws.close();
      if (cancelled) return;
      pollRef.current = setInterval(async () => {
        if (cancelled) return;
        try {
          const data = await api.getTaskStatus(taskId);
          setTask(data);
          if (data.status === 'completed' || data.status === 'failed') {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {}
      }, 1000);
    };

    ws.onclose = () => {
      // If task isn't done yet, switch to polling
      if (cancelled) return;
      if (task?.status !== 'completed' && task?.status !== 'failed') {
        pollRef.current = setInterval(async () => {
          if (cancelled) return;
          try {
            const data = await api.getTaskStatus(taskId);
            setTask(data);
            if (data.status === 'completed' || data.status === 'failed') {
              if (pollRef.current) clearInterval(pollRef.current);
            }
          } catch {}
        }, 1000);
      }
    };

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

  return task;
}
