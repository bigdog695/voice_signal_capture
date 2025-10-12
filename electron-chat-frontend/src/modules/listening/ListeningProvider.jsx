import React, { createContext, useContext, useRef, useState, useCallback, useEffect } from 'react';
import { useConfig } from '../config/ConfigContext';

const ListeningContext = createContext(null);

export const ListeningProvider = ({ autoConnect = true, heartbeatSec = 1, children, maxBubbles = 50 }) => {
  const { urls, ready } = useConfig();
  const wsRef = useRef(null);
  const [status, setStatus] = useState('disconnected');
  const [bubbles, setBubbles] = useState([]);
  const [lastAsrUpdate, setLastAsrUpdate] = useState(null);
  const reconnectAttemptsRef = useRef(0);
  const manualCloseRef = useRef(false);
  const heartbeatTimerRef = useRef(null);
  const connectTimerRef = useRef(null);
  const openedAtRef = useRef(null);
  const seqRef = useRef(0);
  const finishStatesRef = useRef(new Map()); // Map<'citizen' | 'hot-line', boolean>
  const sessionCompletedRef = useRef(false); // Track if current session has been completed (ticket generated)
  const currentUniqueKeyRef = useRef(null); // Track current session unique_key
  const prevListeningUrlRef = useRef(null); // Track previous listening URL to detect real changes
  
  // Simplified: directly append each incoming ASR message (partial or update) as a new bubble
  const appendBubble = useCallback((text, type, source, extras = {}) => {
    // Check if this is a new session based on unique_key change
    const incomingUniqueKey = extras?.unique_key || extras?.uniqueKey || null;
    if (incomingUniqueKey && currentUniqueKeyRef.current && incomingUniqueKey !== currentUniqueKeyRef.current) {
      console.log('[ListeningWS] New session detected via unique_key change', {
        old: currentUniqueKeyRef.current,
        new: incomingUniqueKey
      });
      setBubbles([]);
      finishStatesRef.current.clear();
      sessionCompletedRef.current = false;
    }
    
    // Update current unique_key
    if (incomingUniqueKey) {
      currentUniqueKeyRef.current = incomingUniqueKey;
    }
    
    const role = source === 'citizen' ? 'citizen' : 'other';
    const uniqueKey = extras?.unique_key || extras?.uniqueKey || null;
    const isFinishedFlag = !!(extras && (extras.is_finished === true || extras.isFinished === true || type === 'call_finished'));
    
    console.log('[ListeningWS] appendBubble', { text, type, source, isFinishedFlag, extras });
    
    let finishSequence = null;
    if (isFinishedFlag && (source === 'citizen' || source === 'hot-line')) {
      // 使用OR逻辑更新对应source的状态
      const currentState = finishStatesRef.current.get(source) || false;
      finishStatesRef.current.set(source, currentState || isFinishedFlag);
      
      // 检查是否两个source都已finished
      const citizenFinished = finishStatesRef.current.get('citizen') || false;
      const hotlineFinished = finishStatesRef.current.get('hot-line') || false;
      
      console.log('[ListeningWS] finish states', { 
        source, 
        citizenFinished, 
        hotlineFinished, 
        finishStates: Object.fromEntries(finishStatesRef.current) 
      });
      
      if (citizenFinished && hotlineFinished) {
        finishSequence = 2; // 表示双方都已完成
        console.log('[ListeningWS] BOTH SOURCES FINISHED! Will clear bubbles soon');
      } else {
        finishSequence = 1; // 表示只有一方完成
      }
    }
    const bubble = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2,8)}`,
      text: text || '',
      type,
      source: source || 'asr',
      role,
      time: new Date().toISOString(),
      uniqueKey,
      isFinished: isFinishedFlag,
      finishSequence,
      metadata: extras && typeof extras === 'object' ? extras : undefined
    };
    setBubbles(prev => {
      const next = [...prev, bubble];
      return next.length > maxBubbles ? next.slice(next.length - maxBubbles) : next;
    });
    if (type === 'asr_update') {
      const trimmed = bubble.text && typeof bubble.text === 'string' ? bubble.text.trim() : '';
      if (trimmed) {
        setLastAsrUpdate({
          id: bubble.id,
          text: trimmed,
          role: bubble.role,
          time: bubble.time,
          uniqueKey: bubble.uniqueKey || null
        });
      }
    }
    try {
      if (window && window.electronAPI && typeof window.electronAPI.send === 'function') {
        window.electronAPI.send('listening:event', bubble);
      }
    } catch(_) {}
    return bubble;
  }, [maxBubbles]);

  const clearBubbles = useCallback(() => {
    setBubbles([]);
    finishStatesRef.current.clear();
    console.info('[ListeningWS] bubbles cleared');
  }, []);

  // Request ticket/summary generation when both sources have finished
  const requestTicketGeneration = useCallback(async () => {
    // Prevent duplicate ticket generation requests
    if (sessionCompletedRef.current) {
      console.log('[ListeningWS] Ticket generation already requested for this session, skipping');
      return;
    }

    // Note: Ticket generation is now handled by main process
    // Main process has complete conversation history saved in files
    // The main process will send 'ticket:generated' event when ticket is ready
    console.log('[ListeningWS] Ticket generation is handled by main process, waiting for event...');
    // Mark session as completed to prevent duplicate requests
    sessionCompletedRef.current = true;
  }, []);

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
            {
              const bubble = appendBubble(data.text, 'asr_update', data.source, data);
              console.log('[ListeningWS] asr_update processed, bubble:', {
                hasFinishSequence: !!bubble?.finishSequence,
                finishSequence: bubble?.finishSequence,
                isFinished: data.is_finished,
                source: data.source
              });
              // 检查是否双方都完成，如果是则请求生成工单/摘要
              if (bubble && bubble.finishSequence >= 2) {
                console.log('[ListeningWS] Both sources finished via asr_update, requesting ticket generation');
                finishStatesRef.current.clear();
                // Schedule ticket request on next tick so the end marker is visible
                setTimeout(() => {
                  requestTicketGeneration();
                }, 100);
              }
            }
            break;
          case 'asr_partial':
            appendBubble(data.text, 'asr_partial', data.source || 'mock', data);
            break;
          case 'call_finished':
            // Append an end-of-call marker bubble then request ticket when both sources finished
            {
              const bubble = appendBubble('（结束）', 'call_finished', data.source || 'asr', data);
              console.log('[ListeningWS] call_finished processed, bubble:', {
                hasFinishSequence: !!bubble?.finishSequence,
                finishSequence: bubble?.finishSequence,
                source: data.source
              });
              if (bubble && bubble.finishSequence >= 2) {
                console.log('[ListeningWS] Both sources finished via call_finished, requesting ticket generation');
                finishStatesRef.current.clear();
                // Schedule ticket request on next tick so the end marker is visible
                setTimeout(() => {
                  requestTicketGeneration();
                }, 100);
              }
            }
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
  }, [urls, appendBubble, startHeartbeat, stopHeartbeat, requestTicketGeneration]);

  const disconnect = useCallback(() => {
    manualCloseRef.current = true;
    if (connectTimerRef.current) { clearTimeout(connectTimerRef.current); connectTimerRef.current = null; }
    stopHeartbeat();
    cleanupSocket();
    setStatus('disconnected');
  }, [cleanupSocket, stopHeartbeat]);

  useEffect(() => {
    if (!ready) return; // Wait until config is loaded from main
    if (autoConnect) {
      connect();
    }
  }, [autoConnect, connect, ready]);

  // Reconnect when backend URL actually changes (not just urls object reference)
  useEffect(() => {
    if (!ready) return;
    
    try {
      const currentUrl = urls.listening();
      
      // Only reconnect if URL string actually changed
      if (prevListeningUrlRef.current && prevListeningUrlRef.current !== currentUrl) {
        console.log('[ListeningWS] Backend URL changed, reconnecting...', {
          old: prevListeningUrlRef.current,
          new: currentUrl
        });
        // Disconnect existing connection
        if (wsRef.current) {
          manualCloseRef.current = true;
          if (connectTimerRef.current) { 
            clearTimeout(connectTimerRef.current); 
            connectTimerRef.current = null; 
          }
          stopHeartbeat();
          cleanupSocket();
        }
        // Reconnect with new URL
        if (autoConnect) {
          manualCloseRef.current = false;
          reconnectAttemptsRef.current = 0;
          setTimeout(() => connect(), 100); // Small delay to ensure cleanup
        }
      }
      
      prevListeningUrlRef.current = currentUrl;
    } catch (e) {
      console.error('[ListeningWS] Error in URL change detection:', e);
    }
  }, [urls, ready, autoConnect, connect, stopHeartbeat, cleanupSocket]);

  useEffect(() => {
    return () => { disconnect(); };
  }, [disconnect]);

  // Expose a dev helper for quick manual clearing in the browser console
  useEffect(() => {
    if (typeof window !== 'undefined' && typeof process !== 'undefined' && process?.env && process.env.NODE_ENV !== 'production') {
      window.__LISTENING_CLEAR = clearBubbles;
    }
  }, [clearBubbles]);
  const value = {
    status,
    bubbles,
    isListening: status === 'connected',
    startListening: connect,
    stopListening: disconnect,
    connect,
    disconnect,
    clearBubbles,
    lastAsrUpdate
  };
  return <ListeningContext.Provider value={value}>{children}</ListeningContext.Provider>;
};

export function useListeningContext(){
  const ctx = useContext(ListeningContext);
  if(!ctx) throw new Error('useListeningContext must be used within ListeningProvider');
  return ctx;
}
