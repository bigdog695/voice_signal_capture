// Electron主进程配置管理
const fs = require('fs');
const path = require('path');

// 默认配置
const DEFAULT_CONFIG = {
  backendHost: 'localhost:8000',
  useHttps: false,
  devServerHost: 'localhost:5173',
  exampleServerHost: 'localhost:8080'
};

// 是否在Electron环境中运行（主进程）
let electronApp = null;
try {
  if (process && process.versions && process.versions.electron) {
    electronApp = require('electron').app;
  }
} catch (e) {
  electronApp = null;
}

// 路径：优先使用用户数据目录的配置文件（可在安装后修改），其次使用打包在应用中的配置文件
function getPackagedConfigPath() {
  return path.join(__dirname, 'app-config.json');
}

function getUserConfigPath() {
  if (electronApp) {
    try {
      const userDataPath = electronApp.getPath('userData');
      return path.join(userDataPath, 'app-config.json');
    } catch (e) {
      // 获取 userData 路径失败，回退到 packaged 路径
    }
  }
  return null;
}

// 读取配置文件（优先用户目录配置）
function loadConfigFile() {
  try {
    const userPath = getUserConfigPath();
    if (userPath && fs.existsSync(userPath)) {
      const configData = JSON.parse(fs.readFileSync(userPath, 'utf8'));
      const env = process.env.NODE_ENV || 'default';
      return configData[env] || configData.default || DEFAULT_CONFIG;
    }

    const packagedPath = getPackagedConfigPath();
    if (fs.existsSync(packagedPath)) {
      const configData = JSON.parse(fs.readFileSync(packagedPath, 'utf8'));
      const env = process.env.NODE_ENV || 'default';
      return configData[env] || configData.default || DEFAULT_CONFIG;
    }
  } catch (error) {
    console.warn('无法读取配置文件，使用默认配置:', error && error.message);
  }
  return DEFAULT_CONFIG;
}

// 确保 userData 下存在可被用户修改的配置文件
function ensureUserConfigExists() {
  const userPath = getUserConfigPath();
  if (!userPath) return false; // 非Electron环境或无法获取路径
  try {
    // Ensure parent directory exists so we can write the file
    const dir = path.dirname(userPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    if (!fs.existsSync(userPath)) {
      const packagedPath = getPackagedConfigPath();
      if (fs.existsSync(packagedPath)) {
        // 复制一份到 userData
        fs.copyFileSync(packagedPath, userPath);
      } else {
        // 写入默认结构（包含 default/development/production）
        const defaultWrapper = {
          default: DEFAULT_CONFIG,
          development: DEFAULT_CONFIG,
          production: Object.assign({}, DEFAULT_CONFIG, { useHttps: true })
        };
        fs.writeFileSync(userPath, JSON.stringify(defaultWrapper, null, 2), 'utf8');
      }
      return true;
    }
  } catch (err) {
    console.warn('无法创建用户配置文件:', err && err.message);
  }
  return false;
}

// 保存完整配置对象到 userData
function saveUserConfig(configObject) {
  const userPath = getUserConfigPath();
  if (!userPath) throw new Error('userData path unavailable for saving config');
  try {
    const dir = path.dirname(userPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(userPath, JSON.stringify(configObject, null, 2), 'utf8');
  } catch (err) {
    console.warn('保存用户配置失败:', err && err.message);
    throw err;
  }
}

// 从环境变量、配置文件或默认值获取配置
function getConfig() {
  const fileConfig = loadConfigFile();
  return {
    backendHost: process.env.BACKEND_HOST || fileConfig.backendHost,
    useHttps: (process.env.USE_HTTPS === 'true') || fileConfig.useHttps,
    devServerHost: process.env.DEV_SERVER_HOST || fileConfig.devServerHost,
    exampleServerHost: process.env.EXAMPLE_SERVER_HOST || fileConfig.exampleServerHost
  };
}

function getDevServerUrl() {
  const config = getConfig();
  const protocol = config.useHttps ? 'https' : 'http';
  return `${protocol}://${config.devServerHost}`;
}

module.exports = {
  getConfig,
  getDevServerUrl,
  ensureUserConfigExists,
  saveUserConfig,
  DEFAULT_CONFIG
};