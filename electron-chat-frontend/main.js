const { app, BrowserWindow, Menu } = require('electron');
const fs = require('fs');
const path = require('path');

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
let configModule = null;
try {
  // Resolve relative to this file's directory to be robust when packaged into an asar
  configModule = require(path.join(__dirname, 'config'));
  getDevServerUrl = configModule.getDevServerUrl;
  getConfig = configModule.getConfig;
} catch (err) {
  console.warn('Could not load ./config module, falling back to defaults:', err && err.message);
  const FALLBACK = {
    backendHost: 'localhost:8000',
    useHttps: false,
    devServerHost: 'localhost:5173',
    exampleServerHost: 'localhost:8080'
  };
  getConfig = () => FALLBACK;
  getDevServerUrl = () => `${getConfig().useHttps ? 'https' : 'http'}://${getConfig().devServerHost}`;
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
    title: 'AI Chat - Copilot',
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
    if (configModule && typeof configModule.ensureUserConfigExists === 'function') {
      await configModule.ensureUserConfigExists();
    }
  } catch (err) {
    console.warn('ensureUserConfigExists failed:', err && err.message);
  }
  // Ensure vendor React assets exist for offline file:// fallback
  ensureVendorReact();
  createWindow();
  createMenu();
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
