import { useEffect, useRef, useState, useCallback } from 'react';
import { useConfig } from '../config/ConfigContext';

// Simple health polling hook.
// Behavior:
//  - Immediately attempts fetch to /health
//  - Retries every `intervalMs` until success
//  - After first success, keeps a slower heartbeat check (successIntervalMs) to detect regression
//  - Exposes { ok, lastOkAt, lastError, checking }
export function useHealth({ intervalMs = 2000, successIntervalMs = 15000 } = {}) {
  const { urls } = useConfig();
  const [ok, setOk] = useState(false);
  const [checking, setChecking] = useState(false);
  const [lastOkAt, setLastOkAt] = useState(null);
  const [lastError, setLastError] = useState(null);
  const timerRef = useRef(null);
  const slowModeRef = useRef(false);

  const clearTimer = () => { if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; } };

  const scheduleNext = useCallback((delay) => {
    clearTimer();
    timerRef.current = setTimeout(runCheck, delay);
  // runCheck is defined later; we rely on function hoisting for closure content stable enough
  }, []);

  const runCheck = useCallback(async () => {
    setChecking(true);
    let success = false;
    try {
      const res = await fetch(urls.health(), { method: 'GET' });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        success = true;
        setOk(true);
        setLastOkAt(Date.now());
        setLastError(null);
        if (!slowModeRef.current) {
          slowModeRef.current = true; // switch to slower interval after first success
        }
      } else {
        throw new Error('HTTP ' + res.status);
      }
    } catch (e) {
      setLastError(e.message || String(e));
      setOk(false);
    } finally {
      setChecking(false);
      // choose next interval
      const nextDelay = success ? successIntervalMs : intervalMs;
      scheduleNext(nextDelay);
    }
  }, [urls, intervalMs, successIntervalMs, scheduleNext]);

  useEffect(() => {
    runCheck();
    return () => clearTimer();
  }, [runCheck]);

  return { ok, checking, lastOkAt, lastError };
}
