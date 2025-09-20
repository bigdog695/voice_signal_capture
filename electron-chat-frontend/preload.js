const { contextBridge, ipcRenderer } = require('electron');

// Expose a minimal, safe API to the renderer.
contextBridge.exposeInMainWorld('electronAPI', {
  send: (channel, ...args) => {
    // Whitelist channels if needed
    ipcRenderer.send(channel, ...args);
  },
  invoke: (channel, ...args) => ipcRenderer.invoke(channel, ...args),
  on: (channel, listener) => {
    const subscription = (_, ...rest) => listener(...rest);
    ipcRenderer.on(channel, subscription);
    return () => ipcRenderer.removeListener(channel, subscription);
  },
  once: (channel, listener) => {
    ipcRenderer.once(channel, (_, ...rest) => listener(...rest));
  }
});
