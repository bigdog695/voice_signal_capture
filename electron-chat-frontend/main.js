const { app, BrowserWindow, Menu, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const http = require('http');
const https = require('https');
const os = require('os');
const net = require('net');

// Safe defaults if config module throws
const DEFAULT_SAFE_CFG = {
  backendHost: '127.0.0.1:8000',
  useHttps: false,
  devServerHost: 'localhost:5173',
  exampleServerHost: 'localhost:8080'
};

const APP_DISPLAY_NAME = '12345智能助手';
const APP_VERSION = (typeof app.getVersion === 'function' && app.getVersion()) || require('./package.json').version;
const WINDOW_TITLE = `${APP_DISPLAY_NAME} - ${APP_VERSION}`;

try {
  if (typeof app.setName === 'function') {
    app.setName(APP_DISPLAY_NAME);
  } else {
    app.name = APP_DISPLAY_NAME;
  }
} catch (_) {}

// Ensure vendor React UMD assets exist (offline fallback) if missing.
function ensureVendorReact() {
  try {
    const vendorDir = path.join(__dirname, 'vendor');
    const reactFile = path.join(vendorDir, 'react.production.min.js');
    const reactDomFile = path.join(vendorDir, 'react-dom.production.min.js');
    console.log('[main] vendor check:', {
      vendorDir,
      reactFileExists: fs.existsSync(reactFile),
      reactDomFileExists: fs.existsSync(reactDomFile)
    });
    if (fs.existsSync(reactFile) && fs.existsSync(reactDomFile)) {
      console.log('[main] vendor React UMD already present');
      return; // already present
    }

    // Attempt to copy from node_modules (dev or unpacked environment)
    const nmReact = path.join(__dirname, 'node_modules', 'react', 'umd', 'react.production.min.js');
    const nmReactDom = path.join(__dirname, 'node_modules', 'react-dom', 'umd', 'react-dom.production.min.js');
    const sourcesState = {
      nmReact,
      nmReactExists: fs.existsSync(nmReact),
      nmReactDom,
      nmReactDomExists: fs.existsSync(nmReactDom)
    };
    console.log('[main] node_modules sources state:', sourcesState);
    if (!sourcesState.nmReactExists || !sourcesState.nmReactDomExists) {
      console.warn('[main] vendor React UMD missing and node_modules sources missing. Run npm install.');
      return;
    }
    if (!fs.existsSync(vendorDir)) fs.mkdirSync(vendorDir, { recursive: true });
    fs.copyFileSync(nmReact, reactFile);
    fs.copyFileSync(nmReactDom, reactDomFile);
    console.log('[main] Copied React UMD assets into vendor/');
  } catch (e) {
    console.warn('[main] ensureVendorReact failed:', e && e.message);
  }
}

// Attempt to load local config module; if it isn't available (e.g. in some packaged builds),
// fall back to safe defaults to avoid crashing the main process.
let getDevServerUrl;
let getConfig;
let ensureUserConfigExists;
let saveUserConfig;
let configModule = null;
try {
  // Resolve relative to this file's directory to be robust when packaged into an asar
  configModule = require(path.join(__dirname, 'config'));
  getDevServerUrl = configModule.getDevServerUrl;
  getConfig = configModule.getConfig;
  ensureUserConfigExists = configModule.ensureUserConfigExists;
  saveUserConfig = configModule.saveUserConfig;
} catch (err) {
  console.warn('Could not load ./config module, falling back to defaults:', err && err.message);
  const FALLBACK = {
    backendHost: '192.168.0.201:8000',
    useHttps: false,
    devServerHost: 'localhost:5173',
    exampleServerHost: 'localhost:8080'
  };
  getConfig = () => FALLBACK;
  getDevServerUrl = () => `${getConfig().useHttps ? 'https' : 'http'}://${getConfig().devServerHost}`;
  ensureUserConfigExists = async () => {};
  saveUserConfig = () => {};
}

let mainWindow;

function createWindow() {
  // 创建浏览器窗口
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      sandbox: false
    },
    titleBarStyle: 'default',
    title: WINDOW_TITLE,
    icon: path.join(__dirname, 'assets/icon.png'), // 可选：应用图标
    show: false, // 先不显示，等准备好后再显示
    backgroundColor: '#f8fafc', // 设置背景色与应用一致
    vibrancy: 'under-window', // macOS 毛玻璃效果
    transparent: false
  });

  const isDev = process.argv.includes('--dev');
  if (isDev) {
    const devURL = getDevServerUrl();
    mainWindow.loadURL(devURL).catch(() => {
      console.log('Dev server not available, loading fallback...');
      // If a built dist exists, prefer loading it (it contains compiled assets).
      const distIndex = path.join(__dirname, 'dist', 'index.html');
      if (fs.existsSync(distIndex)) {
        mainWindow.loadFile(distIndex).catch(() => {
          mainWindow.loadFile('index.html');
        });
      } else {
        mainWindow.loadFile('index.html');
      }
    });
  } else {
    // 生产模式加载打包后的 React 入口
    const distIndex = path.join(__dirname, 'dist', 'index.html');
    mainWindow.loadFile(distIndex).catch(() => {
      console.log('Built files not found, loading fallback...');
      mainWindow.loadFile('index.html');
    });
  }

  // 窗口准备好后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // 当窗口被关闭时，取消引用 window 对象
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 开发模式下打开开发者工具
  if (process.argv.includes('--dev')) {
    mainWindow.webContents.openDevTools();
  }
}

// Electron 初始化完成并准备创建浏览器窗口时调用此方法
// Ensure user-editable config exists before creating app UI
app.whenReady().then(async () => {
  try {
    if (typeof ensureUserConfigExists === 'function') {
      await ensureUserConfigExists();
    }
  } catch (err) {
    console.warn('ensureUserConfigExists failed:', err && err.message);
  }
  // Ensure vendor React assets exist for offline file:// fallback
  ensureVendorReact();
  createWindow();
  createMenu();
});

// Config IPC to unify renderer and main
ipcMain.handle('config:get', async () => {
  let cfg;
  try {
    cfg = getConfig();
  } catch (e) {
    console.warn('[main] config:get getConfig() threw, using DEFAULT_SAFE_CFG:', e && e.message);
    cfg = DEFAULT_SAFE_CFG;
  }
  let ip = '0.0.0.0';
  try {
    if (typeof getLocalIPv4 === 'function') {
      ip = getLocalIPv4();
    }
    if (!ip || ip === '127.0.0.1' || ip === '0.0.0.0') {
      // Fallback: determine outbound local address by opening a short-lived socket
      ip = await new Promise((resolve) => {
        try {
          const socket = net.createConnection({ host: '8.8.8.8', port: 53 });
          let finished = false;
          const finish = (addr) => {
            if (finished) return; finished = true;
            try { socket.destroy(); } catch(_) {}
            resolve(addr || '0.0.0.0');
          };
          socket.once('connect', () => finish(socket.localAddress));
          socket.once('error', () => finish('0.0.0.0'));
          setTimeout(() => finish('0.0.0.0'), 400);
        } catch (_) { resolve('0.0.0.0'); }
      });
    }
  } catch (e) {
    console.warn('[main] getLocalIPv4 threw:', e && e.message);
  }
  const merged = Object.assign({}, cfg || {}, { clientIp: ip });
  try { console.log('[main] config:get returns', merged); } catch(_) {}
  return merged;
});
ipcMain.handle('config:set', async (_e, partial) => {
  try {
    const curr = getConfig();
    const p = Object.assign({}, partial || {});
    // Only trim whitespace, do not convert localhost
    if (typeof p.backendHost === 'string') {
      p.backendHost = p.backendHost.trim();
    }
    const next = Object.assign({}, curr, p);
    if (typeof saveUserConfig === 'function') {
      // Persist under default env for simplicity
      const wrapper = { default: next, development: next, production: Object.assign({}, next, { useHttps: true }) };
      saveUserConfig(wrapper);
    }
    return next;
  } catch (e) {
    console.warn('[main] config:set failed', e && e.message);
    throw e;
  }
});

// 当全部窗口关闭时退出应用 (macOS 除外)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  // 在 macOS 上，当单击 dock 图标并且没有其他窗口打开时，
  // 通常会在应用程序中重新创建一个窗口
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// 设置应用菜单
function createMenu() {
  const template = [
    {
      label: 'File',
      submenu: [
        {
          label: 'New Chat',
          accelerator: 'CmdOrCtrl+N',
          click: () => {
            mainWindow.webContents.send('new-chat');
          }
        },
        {
          label: 'Settings',
          accelerator: 'CmdOrCtrl+,',
          click: () => {
            mainWindow.webContents.send('open-settings');
          }
        },
        { type: 'separator' },
        {
          label: 'Quit',
          accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
          click: () => {
            app.quit();
          }
        }
      ]
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectall' }
      ]
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' }
      ]
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About',
          click: () => {
            mainWindow.webContents.send('show-about');
          }
        }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

let conversationsDir; // path to store conversation files
function ensureConversationsDir() {
  try {
    if (!conversationsDir) {
      conversationsDir = path.join(app.getPath('userData'), 'conversations');
    }
    if (!fs.existsSync(conversationsDir)) fs.mkdirSync(conversationsDir, { recursive: true });
    return conversationsDir;
  } catch (e) {
    console.warn('[main] ensureConversationsDir failed', e && e.message);
    return null;
  }
}

function getHistoryMetadata(filePath) {
  let firstTimestamp = null;
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split(/\r?\n/);
    for (const line of lines) {
      if (!line) continue;
      let evt;
      try {
        evt = JSON.parse(line);
      } catch {
        continue;
      }
      if (!firstTimestamp && (evt.time || evt.ts)) {
        firstTimestamp = evt.time || evt.ts;
        break; // 只需要第一个时间戳就够了
      }
    }
  } catch (e) {
    console.warn('[main] getHistoryMetadata failed', e && e.message);
  }

  let formattedTime = '';
  if (firstTimestamp) {
    try {
      const date = new Date(firstTimestamp);
      if (!Number.isNaN(date.getTime())) {
        const parts = new Intl.DateTimeFormat('zh-CN', {
          timeZone: 'Asia/Shanghai',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false
        }).formatToParts(date);
        const map = Object.fromEntries(parts.filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
        formattedTime = `${map.year || '0000'}-${map.month || '00'}-${map.day || '00'} ${map.hour || '00'}:${map.minute || '00'}:${map.second || '00'}`;
      }
    } catch (e) {
      console.warn('[main] format timestamp failed', e && e.message);
    }
  }

  return { formattedTime };
}

// Enhanced metadata that also extracts ticket title if present
function getHistoryMetadata2(filePath) {
  let firstTimestamp = null;
  let ticketTitle = '';
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split(/\r?\n/);
    for (const line of lines) {
      if (!line) continue;
      let evt;
      try { evt = JSON.parse(line); } catch { continue; }
      if (!ticketTitle && evt && evt.system === 'ticket' && evt.ticket && typeof evt.ticket.ticket_title === 'string') {
        ticketTitle = evt.ticket.ticket_title;
      }
      if (!firstTimestamp && (evt.time || evt.ts)) {
        firstTimestamp = evt.time || evt.ts;
      }
    }
  } catch (e) {
    console.warn('[main] getHistoryMetadata2 failed', e && e.message);
  }
  let formattedTime = '';
  if (firstTimestamp) {
    try {
      const date = new Date(firstTimestamp);
      if (!Number.isNaN(date.getTime())) {
        const parts = new Intl.DateTimeFormat('zh-CN', {
          timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
        }).formatToParts(date);
        const map = Object.fromEntries(parts.filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
        formattedTime = `${map.year || '0000'}-${map.month || '00'}-${map.day || '00'} ${map.hour || '00'}:${map.minute || '00'}:${map.second || '00'}`;
      }
    } catch (e) { console.warn('[main] format timestamp failed', e && e.message); }
  }
  return { formattedTime, ticketTitle };
}

// Maintain current active conversation file handle metadata
let activeConv = null; // { id, filePath, createdAt, lastEventTs }
function startConversationIfNeeded(ts) {
  ensureConversationsDir();
  if (activeConv) {
    console.log('[main] startConversationIfNeeded: conversation already active', { id: activeConv.id, filePath: activeConv.filePath });
    return activeConv;
  }
  const id = new Date(ts || Date.now()).toISOString().replace(/[:.]/g, '-');
  const filePath = path.join(conversationsDir, id + '.ndjson');
  activeConv = { id, filePath, createdAt: Date.now(), lastEventTs: Date.now() };
  console.log('[main] ⭐ NEW CONVERSATION CREATED ⭐', { id, filePath });
  console.log('[main] Stack trace for new conversation:', new Error().stack);
  fs.appendFileSync(filePath, JSON.stringify({ system: 'conversation_start', ts: new Date().toISOString() }) + '\n', 'utf8');
  return activeConv;
}
function appendConversationEvent(evt) {
  try {
    console.log('[main] appendConversationEvent called', { 
      type: evt.type, 
      source: evt.source, 
      hasActiveConv: !!activeConv,
      activeConvId: activeConv?.id,
      is_finished: evt.is_finished 
    });
    startConversationIfNeeded(evt.ts || Date.now());
    if (!activeConv) {
      console.warn('[main] appendConversationEvent: no active conversation after startConversationIfNeeded!');
      return;
    }
    activeConv.lastEventTs = Date.now();
    console.log('[main] appendConversationEvent: saving to file', { 
      filePath: activeConv.filePath,
      type: evt.type, 
      source: evt.source, 
      text: evt.text?.substring(0, 30), 
      is_finished: evt.is_finished 
    });
    fs.appendFileSync(activeConv.filePath, JSON.stringify(evt, null, 0) + '\n', 'utf8');
  } catch (e) {
    console.warn('[main] appendConversationEvent failed', e && e.message);
  }
}
function finalizeConversationIfNeeded(reason) {
  if (!activeConv) {
    console.log('[main] finalizeConversationIfNeeded: no active conversation');
    return null;
  }
  console.log('[main] 🔴 FINALIZING CONVERSATION 🔴', { reason, filePath: activeConv.filePath, id: activeConv.id });
  const finished = { ...activeConv };
  try {
    fs.appendFileSync(activeConv.filePath, JSON.stringify({ system: 'conversation_end', reason: reason || 'call_finished', ts: new Date().toISOString() }) + '\n', 'utf8');
    // Debug: print file content
    const content = fs.readFileSync(activeConv.filePath, 'utf8');
    const lineCount = content.split('\n').filter(Boolean).length;
    console.log('[main] finalizeConversationIfNeeded: final file stats:', {
      filePath: activeConv.filePath,
      lineCount,
      sizeBytes: content.length
    });
    console.log('[main] finalizeConversationIfNeeded: file content preview (first 500 chars):');
    console.log(content.substring(0, 500));
  } catch (e) {
    console.warn('[main] finalizeConversationIfNeeded write failed', e && e.message);
  }
  console.log('[main] 🔴 Setting activeConv to NULL 🔴');
  activeConv = null;
  return finished.filePath;
}

const finishStates = new Map(); // Map<'citizen' | 'hot-line', boolean>
let conversationFinalized = false; // Track if current conversation has been finalized

ipcMain.on('listening:event', (_ev, data) => {
  // data = { type, text, role, source, time, uniqueKey?, isFinished?, finishSequence? }
  try {
    const incomingMeta = data && typeof data === 'object' ? data : {};
    const source = incomingMeta.source || data.source || 'unknown';
    const finishedFlag = incomingMeta.isFinished === true || incomingMeta.is_finished === true || (incomingMeta.metadata && (incomingMeta.metadata.is_finished === true || incomingMeta.metadata.isFinished === true));

    console.log('[main] 📨 listening:event received', {
      type: data.type,
      source,
      finishedFlag,
      conversationFinalized,
      hasActiveConv: !!activeConv,
      activeConvId: activeConv?.id,
      text: data.text?.substring(0, 50)
    });

    // Check if this is a new session starting (has unique_key and different from current)
    const incomingUniqueKey = incomingMeta.uniqueKey || (incomingMeta.metadata && incomingMeta.metadata.unique_key) || null;
    if (incomingUniqueKey && conversationFinalized) {
      console.log('[main] 🔄 New session detected after finalization, resetting state', { incomingUniqueKey });
      conversationFinalized = false;
      finishStates.clear();
    }

    // If conversation is already finalized, ignore all subsequent events until a new session
    // This prevents creating ghost sessions from stray messages after finalization
    if (conversationFinalized) {
      console.log('[main] 🚫 BLOCKED: Conversation already finalized, ignoring event to prevent ghost session', {
        type: data.type,
        source,
        text: data.text?.substring(0, 30)
      });
      return;
    }

    // IMPORTANT: Only append to conversation if not call_finished
    // call_finished should only finalize, not create new conversation
    if (data.type !== 'call_finished') {
      appendConversationEvent(data);
    }

    if (finishedFlag && (source === 'citizen' || source === 'hot-line')) {
      // 使用OR逻辑更新对应source的状态
      const currentState = finishStates.get(source) || false;
      finishStates.set(source, currentState || finishedFlag);

      // 检查是否两个source都已finished
      const citizenFinished = finishStates.get('citizen') || false;
      const hotlineFinished = finishStates.get('hot-line') || false;

      console.log('[main] finish states updated', {
        source,
        citizenFinished,
        hotlineFinished,
        finishStates: Object.fromEntries(finishStates)
      });

      if (citizenFinished && hotlineFinished) {
        console.log('[main] BOTH SOURCES FINISHED! Finalizing conversation');
        const filePath = finalizeConversationIfNeeded('both_sources_finished');
        conversationFinalized = true; // Mark as finalized to ignore subsequent events
        if (filePath) {
          requestTicketForConversation(filePath)
            .then(result => logTicketRequestResult(result, 'both_sources_finished'))
            .catch(err => {
              console.warn('[main] ticket request failed', err && err.message);
            });
        }
        finishStates.clear();
        return; // ← 移到这里，只有双方都完成时才 return
      }
      // 如果只是单方完成，继续处理后续逻辑（但 call_finished 类型会在下面被处理）
    }

    if (data.type === 'call_finished') {
      console.log('[main] call_finished event received', {
        conversationFinalized,
        hasActiveConv: !!activeConv,
        source
      });

      // If already finalized (e.g., by both_sources_finished), skip this call_finished
      if (conversationFinalized) {
        console.log('[main] 🚫 BLOCKED: call_finished ignored, conversation already finalized');
        return;
      }

      // Append call_finished marker ONLY if we have an active conversation
      if (activeConv) {
        appendConversationEvent(data);
      } else {
        console.log('[main] call_finished: no active conversation, skipping append');
      }

      // IMPORTANT: call_finished should also update finish states and check if both sources finished
      // Do NOT finalize immediately - wait for both sources
      if (source === 'citizen' || source === 'hot-line') {
        const currentState = finishStates.get(source) || false;
        finishStates.set(source, currentState || true);

        const citizenFinished = finishStates.get('citizen') || false;
        const hotlineFinished = finishStates.get('hot-line') || false;

        console.log('[main] call_finished updated finish states', {
          source,
          citizenFinished,
          hotlineFinished,
          finishStates: Object.fromEntries(finishStates)
        });

        // Only finalize when BOTH sources have sent call_finished
        if (citizenFinished && hotlineFinished) {
          console.log('[main] BOTH SOURCES call_finished! Finalizing conversation');
          const filePath = finalizeConversationIfNeeded('both_call_finished');
          conversationFinalized = true;
          if (filePath) {
            requestTicketForConversation(filePath)
              .then(result => logTicketRequestResult(result, 'both_call_finished'))
              .catch(err => {
                console.warn('[main] ticket request failed', err && err.message);
              });
          }
          finishStates.clear();
        } else {
          console.log('[main] call_finished: waiting for other source to finish', {
            waitingFor: citizenFinished ? 'hot-line' : 'citizen'
          });
        }
      }
    }
  } catch (e) {
    console.warn('[main] listening:event handling failed', e && e.message);
  }
});
ipcMain.handle('history:list', async () => {
  ensureConversationsDir();
  const files = fs.readdirSync(conversationsDir).filter(f => f.endsWith('.ndjson'));
  return files.sort().reverse().map(f => {
    const full = path.join(conversationsDir, f);
    const stat = fs.statSync(full);
    const meta = getHistoryMetadata2(full);
    let displayName = meta.ticketTitle || meta.formattedTime || f.replace(/\.ndjson$/, '');
    return {
      id: f.replace(/\.ndjson$/, ''),
      file: f,
      mtime: stat.mtimeMs,
      size: stat.size,
      displayName,
      formattedTime: meta.formattedTime || null,
      ticketTitle: meta.ticketTitle || null
    };
  });
});

// Provide the first non-internal IPv4 address of this machine to renderer
function getLocalIPv4() {
  try {
    const ifaces = os.networkInterfaces();
    const names = Object.keys(ifaces || {});
    try { console.log('[main] getLocalIPv4: interfaces =', names); } catch(_) {}

    const preferTokens = ['ethernet', '以太网', 'wi-fi', 'wifi', 'wlan', 'lan', 'en', 'eth'];
    const candidates = [];
    for (const name of names) {
      const list = ifaces[name] || [];
      for (const net of list) {
        const family = typeof net.family === 'string' ? net.family : (net.family === 4 ? 'IPv4' : String(net.family));
        const address = net.address;
        if (family !== 'IPv4') continue;
        if (!address || address === '127.0.0.1' || address === '0.0.0.0') continue;
        const lower = (name || '').toLowerCase();
        const preferred = preferTokens.some(t => lower.includes(t));
        const cand = { name, address, internal: !!net.internal, preferred };
        candidates.push(cand);
        try { console.log('[main] getLocalIPv4: candidate', cand); } catch(_) {}
      }
    }
    const byPref = candidates.find(c => !c.internal && c.preferred) ||
                   candidates.find(c => !c.internal) ||
                   candidates[0];
    if (byPref) {
      try { console.log('[main] getLocalIPv4: selected', byPref); } catch(_) {}
      return byPref.address;
    }
  } catch (e) {
    console.warn('[main] getLocalIPv4 failed:', e && e.message);
  }
  return '0.0.0.0';
}

ipcMain.handle('system:client-ip', async () => {
  try {
    let ip = typeof getLocalIPv4 === 'function' ? getLocalIPv4() : '0.0.0.0';
    if (!ip || ip === '127.0.0.1' || ip === '0.0.0.0') {
      ip = await new Promise((resolve) => {
        try {
          const socket = net.createConnection({ host: '8.8.8.8', port: 53 });
          let finished = false;
          const finish = (addr) => { if (finished) return; finished = true; try { socket.destroy(); } catch(_) {}; resolve(addr || '0.0.0.0'); };
          socket.once('connect', () => finish(socket.localAddress));
          socket.once('error', () => finish('0.0.0.0'));
          setTimeout(() => finish('0.0.0.0'), 400);
        } catch (_) { resolve('0.0.0.0'); }
      });
    }
    return ip || '0.0.0.0';
  } catch (_) {
    return '0.0.0.0';
  }
});
ipcMain.handle('history:load', async (_e, id) => {
  ensureConversationsDir();
  const filePath = path.join(conversationsDir, id + '.ndjson');
  if (!fs.existsSync(filePath)) return { error: 'not_found' };
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/).filter(Boolean).map(l => {
    try { return JSON.parse(l); } catch { return { raw: l }; }
  });
  return { id, events: lines };
});

ipcMain.handle('history:regenerateTicket', async (_e, id) => {
  ensureConversationsDir();
  if (!id) return { ok: false, error: 'invalid_id' };
  const filePath = path.join(conversationsDir, id + '.ndjson');
  if (!fs.existsSync(filePath)) {
    return { ok: false, error: 'not_found' };
  }
  try {
    console.log('[main] history:regenerateTicket invoked', { id });
    const result = await requestTicketForConversation(filePath, { force: true });
    if (result && result.ok) {
      return { ok: true };
    }
    const reason = result && typeof result === 'object' ? (result.reason || result.error || 'ticket_request_failed') : 'ticket_request_failed';
    return { ok: false, error: reason };
  } catch (err) {
    console.warn('[main] history:regenerateTicket failed', err && err.message);
    return { ok: false, error: String(err && err.message || err) };
  }
});

// Optional timeout to auto-finalize stale conversation (e.g., no events for 5 minutes)
setInterval(() => {
  if (activeConv && Date.now() - activeConv.lastEventTs > 5 * 60 * 1000) {
    const filePath = finalizeConversationIfNeeded('idle_timeout');
    if (filePath) {
      requestTicketForConversation(filePath)
        .then(result => logTicketRequestResult(result, 'idle_timeout'))
        .catch(err => console.warn('[main] ticket request failed', err && err.message));
    }
    // Clean up finish states for the timed-out conversation
    finishStates.clear();
  }
}, 60 * 1000);

// ------- Ticket proxy integration (main process) -------
const ticketRequestsInFlight = new Set(); // Track in-flight ticket requests by file path

function buildTicketRequestFromFile(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split(/\r?\n/).filter(Boolean);
    const events = lines.map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
    console.log('[main] buildTicketRequestFromFile: total events', events.length);
    const id = path.basename(filePath).replace(/\.ndjson$/, '');
    let unique_key = id;
    let hasTicket = false;
    let hasTicketError = false;
    for (const evt of events) {
      if (evt && (evt.uniqueKey || (evt.metadata && evt.metadata.unique_key))) {
        unique_key = evt.uniqueKey || (evt.metadata && evt.metadata.unique_key) || unique_key;
        break;
      }
    }
    const conversations = [];
    for (const evt of events) {
      if (!evt) continue;
      if (evt.system === 'ticket') {
        hasTicket = true;
        continue;
      }
      if (evt.system === 'ticket_error') {
        hasTicketError = true;
        continue;
      }
      console.log('[main] buildTicketRequestFromFile: processing event', { 
        type: evt.type, 
        source: evt.source, 
        text: evt.text?.substring(0, 30), 
        is_finished: evt.is_finished,
        isFinished: evt.isFinished,
        metadata_is_finished: evt.metadata?.is_finished,
        metadata_isFinished: evt.metadata?.isFinished
      });
      // Skip events with is_finished flag (these are end markers, not conversation content)
      if (evt.is_finished === true || evt.isFinished === true) {
        console.log('[main] buildTicketRequestFromFile: skipping is_finished event');
        continue;
      }
      if (evt.metadata && (evt.metadata.is_finished === true || evt.metadata.isFinished === true)) {
        console.log('[main] buildTicketRequestFromFile: skipping metadata is_finished event');
        continue;
      }
      
      const text = typeof evt.text === 'string' ? evt.text.trim() : '';
      const src = evt.source;
      if (!text) {
        console.log('[main] buildTicketRequestFromFile: skipping empty text event');
        continue;
      }
      if (src === 'citizen' || src === 'hot-line') {
        console.log('[main] buildTicketRequestFromFile: adding conversation', { source: src, text: text.substring(0, 30) });
        conversations.push({ source: src, text });
      }
    }
    console.log('[main] buildTicketRequestFromFile: final conversation count', conversations.length);
    return { unique_key, conversation: conversations, hasTicket, hasTicketError };
  } catch (e) {
    console.warn('[main] buildTicketRequestFromFile failed', e && e.message);
    return null;
  }
}

function postJson(url, data, { timeoutMs = 15000 } = {}) {
  return new Promise((resolve, reject) => {
    try {
      const u = new URL(url);
      const isHttps = u.protocol === 'https:';
      const lib = isHttps ? https : http;
      const payload = Buffer.from(JSON.stringify(data));
      const req = lib.request({
        hostname: u.hostname,
        port: u.port || (isHttps ? 443 : 80),
        path: u.pathname + (u.search || ''),
        method: 'POST',
        family: 4,  // Force IPv4
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Length': payload.length
        }
      }, (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
        res.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf8');
          if (res.statusCode < 200 || res.statusCode >= 300) {
            return reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0,200)}`));
          }
          try {
            const json = JSON.parse(body);
            resolve(json);
          } catch (e) {
            reject(new Error('Invalid JSON from ticket service'));
          }
        });
      });
      req.on('error', reject);
      req.setTimeout(timeoutMs, () => {
        try { req.destroy(new Error('Request timeout')); } catch(_){}
      });
      req.write(payload);
      req.end();
    } catch (e) {
      reject(e);
    }
  });
}

function logTicketRequestResult(result, context) {
  if (!result || typeof result !== 'object') {
    console.warn(`[main] ${context}: ticket request returned invalid result`, result);
    return;
  }
  if (!result.ok) {
    console.log(`[main] ${context}: ticket request not completed`, result);
  }
}

async function requestTicketForConversation(filePath, options) {
  const force = !!(options && options.force);
  if (!filePath) {
    return { ok: false, reason: 'invalid_file' };
  }

  const guardKey = path.resolve(filePath);
  if (ticketRequestsInFlight.has(guardKey)) {
    console.log('[main] requestTicketForConversation skipped: already in flight', { filePath });
    return { ok: false, reason: 'in_flight' };
  }

  ticketRequestsInFlight.add(guardKey);
  try {
    const payloadInfo = buildTicketRequestFromFile(filePath);
    if (!payloadInfo) {
      return { ok: false, reason: 'build_failed' };
    }
    if (payloadInfo.hasTicket && !force) {
      console.log('[main] requestTicketForConversation skipped: ticket already exists', { filePath });
      return { ok: false, reason: 'already_has_ticket' };
    }

    const payload = {
      unique_key: payloadInfo.unique_key,
      conversation: payloadInfo.conversation
    };
    console.log('[main] requestTicketForConversation: generated payload meta', {
      unique_key: payload.unique_key,
      items: payload.conversation.length
    });
    if (!Array.isArray(payload.conversation) || payload.conversation.length === 0) {
      console.warn('[main] ticket payload empty, skipping');
      return { ok: false, reason: 'empty_payload' };
    }

    console.log('[main] requestTicketForConversation: reading file', filePath);
    try {
      const fileContent = fs.readFileSync(filePath, 'utf8');
      console.log('[main] requestTicketForConversation: file content:');
      console.log(fileContent);
    } catch (e) {
      console.warn('[main] failed to read file for debug', e && e.message);
    }

    const cfg = getConfig();
    if (!cfg || !cfg.backendHost) {
      console.warn('[main] ticket request skipped: backend not configured');
      return { ok: false, reason: 'backend_not_configured' };
    }
    // Use backend host as-is from config
    const hostNorm = (cfg.backendHost || '').trim();
    const protocol = cfg.useHttps ? 'https' : 'http';
    const base = `${protocol}://${hostNorm}`;
    const url = `${base}/ticketGeneration`;
    console.log('[main] ticket payload body', JSON.stringify(payload, null, 2));
    console.log('[main] requesting ticketGeneration', { url, unique_key: payload.unique_key, items: payload.conversation.length, cfg, force });
    try {
      const resp = await postJson(url, payload, { timeoutMs: 20000 });
      const ticketEvent = {
        system: 'ticket',
        ticket: resp,
        ts: new Date().toISOString()
      };
      fs.appendFileSync(filePath, JSON.stringify(ticketEvent) + '\n', 'utf8');
      console.log('[main] ticket appended to history');
      // Notify renderer process about new ticket
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('ticket:generated', { ticket: resp, filePath });
        console.log('[main] ticket:generated event sent to renderer');
      }
      return { ok: true };
    } catch (e) {
      console.warn('[main] ticket request error', e && e.message);
      const errEvent = {
        system: 'ticket_error',
        error: String(e && e.message || e),
        ts: new Date().toISOString()
      };
      try { fs.appendFileSync(filePath, JSON.stringify(errEvent) + '\n', 'utf8'); } catch(_){ }
      // Notify renderer process about ticket error
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('ticket:error', { error: String(e && e.message || e), filePath });
        console.log('[main] ticket:error event sent to renderer');
      }
      return { ok: false, reason: 'request_failed', error: String(e && e.message || e) };
    }
  } finally {
    ticketRequestsInFlight.delete(guardKey);
  }
}
