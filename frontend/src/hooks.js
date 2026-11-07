import { useCallback, useEffect, useRef, useState } from 'react';
import { getWebSocketUrl } from './api';

export function useApi(loader, deps = [], { pollMs = 0 } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    async function run(showLoading) {
      if (showLoading) setLoading(true);
      try {
        const result = await loaderRef.current(controller.signal);
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && err.name !== 'AbortError') {
          setError(err);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    run(true);
    let interval;
    if (pollMs) {
      interval = window.setInterval(() => run(false), pollMs);
    }
    return () => {
      cancelled = true;
      controller.abort();
      if (interval) window.clearInterval(interval);
    };
  }, [...deps, nonce, pollMs]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, loading, error, reload };
}

export function useLiveEvents(onEvent) {
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let socket = null;
    let reconnectTimer = null;
    let heartbeat = null;
    let attempts = 0;
    let closed = false;

    function connect() {
      try {
        socket = new WebSocket(getWebSocketUrl());
      } catch {
        scheduleReconnect();
        return;
      }

      socket.onopen = () => {
        attempts = 0;
        setConnected(true);
        heartbeat = window.setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send('ping');
        }, 25_000);
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'hello' || data.type === 'pong') return;
          handlerRef.current?.(data);
        } catch {
        }
      };

      socket.onclose = () => {
        setConnected(false);
        if (heartbeat) window.clearInterval(heartbeat);
        heartbeat = null;
        scheduleReconnect();
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    function scheduleReconnect() {
      if (closed) return;
      const delay = Math.min(30_000, 1_000 * 2 ** attempts);
      attempts += 1;
      reconnectTimer = window.setTimeout(connect, delay);
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      if (heartbeat) window.clearInterval(heartbeat);
      socket?.close();
    };
  }, []);

  return connected;
}

export function useDocumentTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · PulseWatch` : 'PulseWatch · API İzleme';
  }, [title]);
}
