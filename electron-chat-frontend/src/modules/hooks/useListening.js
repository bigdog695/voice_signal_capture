import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useWebSocket } from './useWebSocket';
import { useConfig } from '../config/ConfigContext';
import { useWhitelist } from './useWhitelist';

// 正则：以句末终止符结束的完整句子
const SENTENCE_REGEX = /[^。！？!?]*[。！？!?]/g;

export function useListening({ autoConnect = true, maxBubbles = 20 } = {}) {
  const { urls } = useConfig();
  const { ensureWhitelisted } = useWhitelist();
  const [bubbles, setBubbles] = useState([]); // {id,text,final,source,time,revision,isPartial,stableLen}
  const segmentSplitState = useRef(new Map()); // segmentId -> { emitted }
  const pendingTexts = useRef(new Map()); // segmentId -> last pending tail
  const connInfoRef = useRef({ seq: 0 });
  const heartbeatTimer = useRef(null);

  const addOrReplace = useCallback((bubble) => {
    setBubbles(prev => {
      // 如果 id 已存在则替换
      const idx = prev.findIndex(b => b.id === bubble.id);
      let next = [...prev];
      if (idx >= 0) {
        next[idx] = { ...next[idx], ...bubble };
      } else {
        next.push(bubble);
      }
      // 限制数量
      if (next.length > maxBubbles) {
        next = next.slice(next.length - maxBubbles);
      }
      return next;
    });
  }, [maxBubbles]);

  const removeBubble = useCallback((id) => {
    setBubbles(prev => prev.filter(b => b.id !== id));
  }, []);

  const handleAsrUpdate = useCallback((msg) => {
    const { segmentId, revision, text = '', is_final, stable_len, source, timestamp } = msg;
    if (!segmentId || typeof text !== 'string') return;

    // 拆分完整句子
    SENTENCE_REGEX.lastIndex = 0; // 重置 lastIndex
    const completed = [];
    let m;
    while ((m = SENTENCE_REGEX.exec(text)) !== null) {
      const s = m[0].trim();
      if (s) completed.push(s);
    }
    const pendingTail = text.slice(SENTENCE_REGEX.lastIndex);
    const state = segmentSplitState.current.get(segmentId) || { emitted: 0 };

    // 输出新增完整句子
    for (let i = state.emitted; i < completed.length; i++) {
      const sentence = completed[i];
      const bubbleId = `${segmentId}-s${i}`;
      addOrReplace({
        id: bubbleId,
        text: sentence,
        final: true,
        source,
        time: timestamp || new Date().toISOString(),
        revision: revision ?? 0,
        isPartial: false,
        stableLen: sentence.length
      });
    }
    state.emitted = completed.length;
    segmentSplitState.current.set(segmentId, state);

    const pendingId = `${segmentId}-pending`;
    if (pendingTail) {
      // 只有在非最终 或 final 但仍有尾部（未成句）时显示
      if (!is_final || (is_final && !/[。！？!?]$/.test(pendingTail))) {
        addOrReplace({
          id: pendingId,
            text: pendingTail,
            final: !!(is_final && !pendingTail.match(/[。！？!?]$/)),
            source,
            time: timestamp || new Date().toISOString(),
            revision: revision ?? 0,
            isPartial: !is_final,
            stableLen: typeof stable_len === 'number' ? stable_len : undefined
        });
      }
    } else {
      // 没有尾部 => 移除旧 pending
      removeBubble(pendingId);
    }

    // 整段无标点且 final 情况 => 把整段当作单句
    if (is_final && completed.length === 0 && !pendingTail && text.trim()) {
      const bubbleId = `${segmentId}-s0`;
      addOrReplace({
        id: bubbleId,
        text: text.trim(),
        final: true,
        source,
        time: timestamp || new Date().toISOString(),
        revision: revision ?? 0,
        isPartial: false,
        stableLen: text.length
      });
    }
  }, [addOrReplace, removeBubble]);

  const onMessage = useCallback((data, ws) => {
    connInfoRef.current.seq += 1;
    if (data.type === 'asr_update') {
      handleAsrUpdate(data);
    } else if (data.type === 'pong') {
      // ignore
    } else if (data.type === 'listening_ready') {
      // 可根据需要设置状态
    }
  }, [handleAsrUpdate]);

  const { status, connect: wsConnect, disconnect, sendJson } = useWebSocket(urls.listening(), { autoConnect: false, onMessage });

  // 包装连接函数，先注册白名单
  const connect = useCallback(async () => {
    try {
      console.log('Ensuring whitelist registration before connecting...');
      const whitelisted = await ensureWhitelisted();
      if (whitelisted) {
        console.log('Whitelist confirmed, connecting to WebSocket...');
        wsConnect();
      } else {
        console.error('Failed to register to whitelist, cannot connect');
      }
    } catch (error) {
      console.error('Error during whitelist registration:', error);
    }
  }, [ensureWhitelisted, wsConnect]);

  // 自动连接逻辑
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
  }, [autoConnect, connect]);

  // Heartbeat
  useEffect(() => {
    if (status === 'connected') {
      heartbeatTimer.current = setInterval(() => {
        sendJson({ type: 'ping', ts: new Date().toISOString() });
      }, 1000);
    }
    return () => {
      if (heartbeatTimer.current) {
        clearInterval(heartbeatTimer.current);
        heartbeatTimer.current = null;
      }
    };
  }, [status, sendJson]);

  const isListening = status === 'connected';
  const startListening = useCallback(() => connect(), [connect]);
  const stopListening = useCallback(() => disconnect(), [disconnect]);

  return { 
    status, 
    bubbles, 
    isListening,
    startListening,
    stopListening,
    connect, 
    disconnect 
  };
}
