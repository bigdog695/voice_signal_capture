import { useEffect, useRef, useState, useCallback } from 'react';

let __wsGlobalId = 0;

export function useWebSocket(url, { autoConnect = false, onMessage, onOpen, onClose, onError, enabled = true, label = 'ws' } = {}) {
  const wsRef = useRef(null);
  const [status, setStatus] = useState('disconnected');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const maxReconnect = 5;
  const connMetaRef = useRef({ connectionId: null, openedAt: null });

  const connect = useCallback(() => {
    if (!enabled || !url) return;
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return;
    try {
      setStatus('connecting');
      const nextId = ++__wsGlobalId;
      connMetaRef.current.connectionId = nextId;
      connMetaRef.current.openedAt = Date.now();
      try { console.info(`[WS] connect_start id=${nextId} label=${label} url=${url} attempt=${reconnectAttempts}`); } catch(_) {}
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = (ev) => {
        setStatus('connected');
        setReconnectAttempts(0);
        connMetaRef.current.openedAt = Date.now();
        try { console.info(`[WS] open id=${connMetaRef.current.connectionId} label=${label} url=${url}`); } catch(_) {}
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
        const lifeMs = connMetaRef.current.openedAt ? (Date.now() - connMetaRef.current.openedAt) : -1;
        try { console.warn(`[WS] close id=${connMetaRef.current.connectionId} label=${label} url=${url} code=${ev.code} clean=${ev.wasClean} lifetime_ms=${lifeMs}`); } catch(_) {}
        onClose && onClose(ev, ws);
        if (reconnectAttempts < maxReconnect && enabled) {
          const timeout = Math.pow(2, reconnectAttempts) * 1000;
            try { console.info(`[WS] schedule_reconnect id=${connMetaRef.current.connectionId} label=${label} url=${url} in=${timeout}ms attempt=${reconnectAttempts+1}`); } catch(_) {}
            setTimeout(() => {
              setReconnectAttempts(a => a + 1);
              connect();
            }, timeout);
        }
      };
      ws.onerror = (ev) => {
        try { console.error(`[WS] error id=${connMetaRef.current.connectionId} label=${label} url=${url}`); } catch(_) {}
        onError && onError(ev, ws);
      };
    } catch (e) {
      setStatus('disconnected');
      try { console.error(`[WS] connect_exception label=${label} url=${url} err=${e?.message}`); } catch(_) {}
    }
  }, [url, enabled, onMessage, onOpen, onClose, onError, reconnectAttempts, label]);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      try { console.info(`[WS] manual_disconnect id=${connMetaRef.current.connectionId} label=${label} url=${url} state=${wsRef.current.readyState}`); } catch(_) {}
      wsRef.current.close();
      wsRef.current = null;
    }
  }, [url, label]);

  const sendJson = useCallback((obj) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(obj));
    }
  }, []);

  useEffect(() => {
    if (autoConnect) connect();
    return () => disconnect();
  }, [autoConnect, connect, disconnect]);

  return { status, connect, disconnect, sendJson, wsRef, connectionId: connMetaRef.current.connectionId };
}
