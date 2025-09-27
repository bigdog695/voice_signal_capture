import React, { createContext, useContext, useState, useCallback, useMemo, useEffect } from 'react';

const DEFAULT_CONFIG = {
  // No default backend to avoid masking config problems
  backendHost: '',
  useHttps: false,
  devServerHost: 'localhost:5173',
  exampleServerHost: 'localhost:8080'
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
          if (cfg && mounted) {
            setBackendHost(cfg.backendHost || '');
            setUseHttps(!!cfg.useHttps);
            setDevServerHost(cfg.devServerHost || DEFAULT_CONFIG.devServerHost);
            setExampleServerHost(cfg.exampleServerHost || DEFAULT_CONFIG.exampleServerHost);
            setReady(true);
            return;
          }
        }
      } catch {}
      if (!mounted) return;
      // Stay not ready; require user to set config via Settings
    };
    load();
    return () => { mounted = false; };
  }, []);

  const saveConfig = useCallback(async (host, https) => {
    setBackendHost(host);
    setUseHttps(https);
    if (window && window.electronAPI && typeof window.electronAPI.invoke === 'function') {
      await window.electronAPI.invoke('config:set', { backendHost: host, useHttps: !!https });
    }
    // After saving, consider config ready
    setReady(!!host);
  }, []);

  const protocols = useMemo(() => ({
    http: useHttps ? 'https' : 'http',
    ws: useHttps ? 'wss' : 'ws'
  }), [useHttps]);

  const urls = useMemo(() => {
    const host = (backendHost || '').replace(/^localhost(?=[:/]|$)/i, '127.0.0.1');
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
