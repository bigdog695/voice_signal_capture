const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');

let mainWindow;

function createWindow() {
  // 创建浏览器窗口
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true
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
    const devURL = 'http://localhost:5173';
    mainWindow.loadURL(devURL).catch(() => {
      console.log('Dev server not available, loading fallback...');
      mainWindow.loadFile('index.html');
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
app.whenReady().then(createWindow);

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

app.whenReady().then(() => {
  createMenu();
});
