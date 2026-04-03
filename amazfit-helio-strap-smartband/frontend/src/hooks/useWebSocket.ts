import { useEffect, useRef, useState, useCallback } from 'react';

export function useWebSocket<T>(url: string) {
  const [data, setData] = useState<T[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const mountedRef = useRef(true);
  const maxPoints = 300;

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${url}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (mountedRef.current) setConnected(true);
      };

      ws.onclose = () => {
        if (mountedRef.current) {
          setConnected(false);
          retryRef.current = setTimeout(connect, 5000);
        }
      };

      ws.onerror = () => {
        // Silently handle — onclose will fire after this and trigger retry
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data) as T;
          setData((prev) => {
            const next = [...prev, parsed];
            return next.length > maxPoints ? next.slice(-maxPoints) : next;
          });
        } catch {
          // ignore
        }
      };

      wsRef.current = ws;
    } catch {
      retryRef.current = setTimeout(connect, 5000);
    }
  }, [url]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { data, connected };
}
