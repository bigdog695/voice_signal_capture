import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';

const DEFAULT_CONFIG = {
  // Default backend for out-of-box experience
  backendHost: '127.0.0.1:8000',
  useHttps: false,
  devServerHost: '127.0.0.1:5173',
  exampleServerHost: '127.0.0.1:8080'
};

const ConfigContext = createContext(null);

export const ConfigProvider = ({ children }) => {
  const [backendHost, setBackendHost] = useState(DEFAULT_CONFIG.backendHost);
  const [useHttps, setUseHttps] = useState(DEFAULT_CONFIG.useHttps);
  const [devServerHost, setDevServerHost] = useState(DEFAULT_CONFIG.devServerHost);
  const [exampleServerHost, setExampleServerHost] = useState(DEFAULT_CONFIG.exampleServerHost);
  const [ready, setReady] = useState(false);

  // Load config from main process; if missing, stay not ready (no silent default)
  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        if (window && window.electronAPI && typeof window.electronAPI.invoke === 'function') {
          const cfg = await window.electronAPI.invoke('config:get');
          console.log('[ConfigContext] Loaded config from main:', cfg);
          if (cfg && mounted) {
            const host = (cfg.backendHost || DEFAULT_CONFIG.backendHost).trim();
            setBackendHost(host);
            setUseHttps(!!cfg.useHttps);
            setDevServerHost(cfg.devServerHost || DEFAULT_CONFIG.devServerHost);
            setExampleServerHost(cfg.exampleServerHost || DEFAULT_CONFIG.exampleServerHost);
            setReady(!!host);
            console.log('[ConfigContext] Config ready:', { host, useHttps: !!cfg.useHttps });
            return;
          }
        }
      } catch (error) {
        console.error('[ConfigContext] Failed to load config:', error);
      }
      if (!mounted) return;
      // Fallback to default config if electron API not available
      console.log('[ConfigContext] Using default config');
      setBackendHost(DEFAULT_CONFIG.backendHost);
      setUseHttps(DEFAULT_CONFIG.useHttps);
      setReady(true);
    };
    load();
    return () => { mounted = false; };
  }, []);

  const saveConfig = useCallback(async (host, https) => {
    const trimmedHost = (host || '').trim();
    console.log('[ConfigContext] Saving config:', { host: trimmedHost, https });
    
    // Update state immediately
    setBackendHost(trimmedHost);
    setUseHttps(!!https);
    setReady(!!trimmedHost);
    
    // Persist to main process
    if (window && window.electronAPI && typeof window.electronAPI.invoke === 'function') {
      try {
        await window.electronAPI.invoke('config:set', { backendHost: trimmedHost, useHttps: !!https });
        console.log('[ConfigContext] Config saved to main process');
      } catch (error) {
        console.error('[ConfigContext] Failed to save config:', error);
      }
    }
  }, []);

  const protocols = useMemo(() => ({
    http: useHttps ? 'https' : 'http',
    ws: useHttps ? 'wss' : 'ws'
  }), [useHttps]);

  const urls = useMemo(() => {
    // Use backendHost as-is, no automatic localhost conversion
    const host = (backendHost || '').trim();
    console.log('[ConfigContext] Generating URLs with host:', host);
    const make = (path) => {
      if (!host) throw new Error('Backend host not configured');
      return `${protocols.http}://${host}${path}`;
    };
    const makeWs = (path) => {
      if (!host) throw new Error('Backend host not configured');
      return `${protocols.ws}://${host}${path}`;
    };
    return {
      chat: (chatId='test_001') => makeWs(`/chatting?id=${chatId}`),
      asr: () => makeWs('/ws'),
      listening: () => makeWs('/listening'),
      health: () => make('/health'),
      ticketGeneration: () => make('/ticketGeneration'),
      base: () => make('')
    };
  }, [protocols, backendHost]);

  const value = { backendHost, useHttps, devServerHost, exampleServerHost, saveConfig, protocols, urls, ready };
  try { if (ready) console.info('[Config] backendHost=', backendHost, 'listeningURL=', urls.listening()); } catch(_) {}
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
};

export const useConfig = () => {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error('useConfig must be used within ConfigProvider');
  return ctx;
};
