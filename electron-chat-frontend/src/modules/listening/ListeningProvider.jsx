import React, { createContext, useContext, useRef, useState, useCallback, useEffect } from 'react';
import { useConfig } from '../config/ConfigContext';

const ListeningContext = createContext(null);

export const ListeningProvider = ({ autoConnect = false, heartbeatSec = 1, children, maxBubbles = 20 }) => {
  const { urls } = useConfig();
  const wsRef = useRef(null);
  const [status, setStatus] = useState('disconnected');
  const [bubbles, setBubbles] = useState([]);
  const reconnectAttemptsRef = useRef(0);
  const manualCloseRef = useRef(false);
  const heartbeatTimerRef = useRef(null);
  const connectTimerRef = useRef(null);
  const openedAtRef = useRef(null);
  const seqRef = useRef(0);
  // Simplified: directly append each incoming ASR message (partial or update) as a new bubble
  const appendBubble = useCallback((text, type, source) => {
    const bubble = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2,8)}`,
      text: text || '',
      type,
      source: source || 'asr',
      time: new Date().toISOString()
    };
    setBubbles(prev => {
      const next = [...prev, bubble];
      return next.length > maxBubbles ? next.slice(next.length - maxBubbles) : next;
    });
  }, [maxBubbles]);

  const stopHeartbeat = useCallback(() => { if (heartbeatTimerRef.current) { clearInterval(heartbeatTimerRef.current); heartbeatTimerRef.current = null; } }, []);
  const startHeartbeat = useCallback(() => {
    stopHeartbeat();
    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        try { wsRef.current.send(JSON.stringify({ type: 'ping', ts: new Date().toISOString() })); } catch(e){}
      }
    }, heartbeatSec * 1000);
  }, [heartbeatSec, stopHeartbeat]);

  const cleanupSocket = useCallback(() => {
    if (wsRef.current) { try { wsRef.current.close(); } catch(_) {}; wsRef.current = null; }
  }, []);

  const connect = useCallback(() => {
    manualCloseRef.current = false; // reset so reconnection logic can work
    const url = urls.listening();
    if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) return;
    try {
      setStatus('connecting');
      console.info('[ListeningWS] connecting', url, 'attempt', reconnectAttemptsRef.current);
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        openedAtRef.current = Date.now();
        reconnectAttemptsRef.current = 0;
        setStatus('connected');
        console.info('[ListeningWS] open', url);
        startHeartbeat();
      };
      ws.onmessage = (ev) => {
        seqRef.current += 1;
        let data = null; try { data = JSON.parse(ev.data); } catch { return; }
        if (!data || typeof data !== 'object') return;
        switch(data.type){
          case 'pong': return;
          case 'server_heartbeat': return;
          case 'asr_update':
            appendBubble(data.text, 'asr_update', data.source);
            break;
          case 'asr_partial':
            appendBubble(data.text, 'asr_partial', data.source || 'mock');
            break;
          default: break;
        }
      };
      ws.onerror = () => { console.warn('[ListeningWS] error'); };
      ws.onclose = (ev) => {
        stopHeartbeat();
        const life = openedAtRef.current ? (Date.now() - openedAtRef.current) : -1;
        console.warn(`[ListeningWS] close code=${ev.code} clean=${ev.wasClean} life_ms=${life}`);
        wsRef.current = null;
        setStatus('disconnected');
        if (!manualCloseRef.current) {
          const attempt = reconnectAttemptsRef.current;
            if (attempt < 8) {
              const delay = Math.min(30000, Math.pow(2, attempt) * 500) + Math.round(Math.random()*200);
              console.info(`[ListeningWS] schedule reconnect attempt=${attempt+1} in ${delay}ms`);
              if (connectTimerRef.current) clearTimeout(connectTimerRef.current);
              connectTimerRef.current = setTimeout(() => { reconnectAttemptsRef.current += 1; connect(); }, delay);
            } else {
              console.warn('[ListeningWS] max reconnect attempts reached');
            }
        }
      };
    } catch (e) {
      console.error('[ListeningWS] connect exception', e.message);
      setStatus('disconnected');
    }
  }, [urls, appendBubble, startHeartbeat, stopHeartbeat]);

  const disconnect = useCallback(() => {
    manualCloseRef.current = true;
    if (connectTimerRef.current) { clearTimeout(connectTimerRef.current); connectTimerRef.current = null; }
    stopHeartbeat();
    cleanupSocket();
    setStatus('disconnected');
  }, [cleanupSocket, stopHeartbeat]);

  useEffect(() => {
    return () => { disconnect(); };
  }, [disconnect]);

  const value = { status, bubbles, isListening: status === 'connected', startListening: connect, stopListening: disconnect, connect, disconnect };
  return <ListeningContext.Provider value={value}>{children}</ListeningContext.Provider>;
};

export function useListeningContext(){
  const ctx = useContext(ListeningContext);
  if(!ctx) throw new Error('useListeningContext must be used within ListeningProvider');
  return ctx;
}
