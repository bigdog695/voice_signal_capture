import { useEffect, useRef, useState, useCallback } from 'react';

export function useWebSocket(url, { autoConnect = false, onMessage, onOpen, onClose, onError, enabled = true } = {}) {
  const wsRef = useRef(null);
  const [status, setStatus] = useState('disconnected');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const maxReconnect = 5;

  const connect = useCallback(() => {
    if (!enabled || !url) return;
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return;
    try {
      setStatus('connecting');
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = (ev) => {
        setStatus('connected');
        setReconnectAttempts(0);
        onOpen && onOpen(ev, ws);
      };
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          onMessage && onMessage(data, ws);
        } catch (e) {
          // ignore non JSON
        }
      };
      ws.onclose = (ev) => {
        setStatus('disconnected');
        onClose && onClose(ev, ws);
        if (reconnectAttempts < maxReconnect && enabled) {
          const timeout = Math.pow(2, reconnectAttempts) * 1000;
            setTimeout(() => {
              setReconnectAttempts(a => a + 1);
              connect();
            }, timeout);
        }
      };
      ws.onerror = (ev) => {
        onError && onError(ev, ws);
      };
    } catch (e) {
      setStatus('disconnected');
    }
  }, [url, enabled, onMessage, onOpen, onClose, onError, reconnectAttempts]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const sendJson = useCallback((obj) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(obj));
    }
  }, []);

  useEffect(() => {
    if (autoConnect) connect();
    return () => disconnect();
  }, [autoConnect, connect, disconnect]);

  return { status, connect, disconnect, sendJson, wsRef };
}
