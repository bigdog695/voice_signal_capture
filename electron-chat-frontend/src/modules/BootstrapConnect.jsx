import React, { useEffect } from 'react';
import { useWhitelist } from './hooks/useWhitelist';
import { useListening } from './hooks/useListening';

// Background bootstrap: on app start, register whitelist and start WS listening.
export const BootstrapConnect = () => {
  const { ensureWhitelisted } = useWhitelist();
  const { startListening, stopListening } = useListening({ autoConnect: true });

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        await ensureWhitelisted();
        if (mounted) startListening();
      } catch (_) {
        // swallow; useListening has its own retry logic
      }
    })();
    return () => {
      mounted = false;
      stopListening();
    };
  }, [ensureWhitelisted, startListening, stopListening]);

  return null;
};

