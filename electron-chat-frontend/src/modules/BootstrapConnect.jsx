import React, { useEffect, useRef } from 'react';
import { useWhitelist } from './hooks/useWhitelist';
import { useListening } from './hooks/useListening';

// Background bootstrap: on app start, register whitelist and start WS listening.
export const BootstrapConnect = () => {
  const { ensureWhitelisted } = useWhitelist();
  const { startListening, stopListening } = useListening({ autoConnect: true });

  // Run only once on mount; dependencies are stable due to memoization
  const ranRef = useRef(false);
  useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;
    let active = true;
    (async () => {
      try {
        await ensureWhitelisted();
        if (active) {
          try { console.info('[BootstrapConnect] startListening once'); } catch(_) {}
          startListening();
        }
      } catch (e) {
        try { console.warn('[BootstrapConnect] ensureWhitelisted failed', e); } catch(_) {}
      }
    })();
    return () => { active = false; stopListening(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return null;
};

