'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import type { TaskProgress } from '@/lib/types';

function startPolling(
  taskId: string,
  setTask: (t: TaskProgress) => void,
  cancelled: () => boolean,
): NodeJS.Timeout {
  return setInterval(async () => {
    if (cancelled()) return;
    try {
      const data = await api.getTaskStatus(taskId);
      setTask(data);
      if (data.status === 'completed' || data.status === 'failed') {
        // Caller will clean up via the returned interval ID
      }
    } catch {}
  }, 1500);
}

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
    const isCancelled = () => cancelled;

    const fallbackToPolling = () => {
      if (cancelled || pollRef.current) return;
      pollRef.current = startPolling(taskId, (data) => {
        setTask(data);
        if (data.status === 'completed' || data.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
        }
      }, isCancelled);
    };

    // Only attempt WebSocket on same-origin (localhost dev).
    // Through tunnels/HTTPS proxies, go straight to polling.
    const isSecure = typeof window !== 'undefined' && window.location.protocol === 'https:';
    const isLocalhost = typeof window !== 'undefined' &&
      (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

    if (!isSecure && isLocalhost) {
      try {
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
          ws.close();
          fallbackToPolling();
        };

        ws.onclose = () => {
          fallbackToPolling();
        };
      } catch {
        fallbackToPolling();
      }
    } else {
      // HTTPS or tunnel — use polling directly
      fallbackToPolling();
    }

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [taskId]); // eslint-disable-line react-hooks/exhaustive-deps

  return task;
}
