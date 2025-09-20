import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

const DEFAULT_CONFIG = {
  backendHost: 'localhost:8000',
  useHttps: false,
  devServerHost: 'localhost:5173',
  exampleServerHost: 'localhost:8080'
};

const ConfigContext = createContext(null);

export const ConfigProvider = ({ children }) => {
  const [backendHost, setBackendHost] = useState(localStorage.getItem('backendHost') || DEFAULT_CONFIG.backendHost);
  const [useHttps, setUseHttps] = useState(localStorage.getItem('useHttps') === 'true' || DEFAULT_CONFIG.useHttps);
  const [devServerHost] = useState(localStorage.getItem('devServerHost') || DEFAULT_CONFIG.devServerHost);
  const [exampleServerHost] = useState(localStorage.getItem('exampleServerHost') || DEFAULT_CONFIG.exampleServerHost);

  const saveConfig = useCallback((host, https) => {
    setBackendHost(host);
    setUseHttps(https);
    localStorage.setItem('backendHost', host);
    localStorage.setItem('useHttps', https.toString());
  }, []);

  const protocols = useMemo(() => ({
    http: useHttps ? 'https' : 'http',
    ws: useHttps ? 'wss' : 'ws'
  }), [useHttps]);

  const urls = useMemo(() => ({
    chat: (chatId='test_001') => `${protocols.ws}://${backendHost}/chatting?id=${chatId}`,
    asr: () => `${protocols.ws}://${backendHost}/ws`,
    listening: () => `${protocols.ws}://${backendHost}/listening`,
    health: () => `${protocols.http}://${backendHost}/health`,
    base: () => `${protocols.http}://${backendHost}`
  }), [protocols, backendHost]);

  const value = { backendHost, useHttps, devServerHost, exampleServerHost, saveConfig, protocols, urls };
  try { console.info('[Config] backendHost=', backendHost, 'listeningURL=', urls.listening()); } catch(_) {}
  return <ConfigContext.Provider value={value}>{children}</ConfigContext.Provider>;
};

export const useConfig = () => {
  const ctx = useContext(ConfigContext);
  if (!ctx) throw new Error('useConfig must be used within ConfigProvider');
  return ctx;
};
