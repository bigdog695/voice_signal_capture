console.log('[renderer] loaded');

// Electron渲染进程配置管理
const DEFAULT_CONFIG = {
  backendHost: '192.168.0.201:8000',
  useHttps: false
};

// 从localStorage获取配置，如果没有则使用默认值
function getStoredConfig() {
  const backendHost = localStorage.getItem('backendHost') || DEFAULT_CONFIG.backendHost;
  const useHttps = localStorage.getItem('useHttps') === 'true' || DEFAULT_CONFIG.useHttps;
  return { backendHost, useHttps };
}

// 更新端点预览显示
function updateEndpointPreviews() {
  const config = getStoredConfig();
  const protocol = config.useHttps ? 'https' : 'http';
  const wsProtocol = config.useHttps ? 'wss' : 'ws';
  
  // 更新各个端点预览
  const chatPreview = document.getElementById('chatEndpointPreview');
  const asrPreview = document.getElementById('asrEndpointPreview');
  const listeningPreview = document.getElementById('listeningEndpointPreview');
  const healthPreview = document.getElementById('healthEndpointPreview');
  
  if (chatPreview) chatPreview.textContent = `${wsProtocol}://${config.backendHost}/chatting`;
  if (asrPreview) asrPreview.textContent = `${wsProtocol}://${config.backendHost}/ws`;
  if (listeningPreview) listeningPreview.textContent = `${wsProtocol}://${config.backendHost}/listening`;
  if (healthPreview) healthPreview.textContent = `${protocol}://${config.backendHost}/health`;
}

// 初始化配置表单
function initializeConfigForm() {
  const config = getStoredConfig();
  
  const backendHostInput = document.getElementById('backendHost');
  const useHttpsInput = document.getElementById('useHttps');
  
  if (backendHostInput) {
    backendHostInput.value = config.backendHost;
    // 移除硬编码的placeholder和value，使用配置值
    backendHostInput.placeholder = config.backendHost;
  }
  
  if (useHttpsInput) {
    useHttpsInput.checked = config.useHttps;
  }
  
  // 更新端点预览
  updateEndpointPreviews();
}

// 保存配置
function saveConfiguration() {
  const backendHostInput = document.getElementById('backendHost');
  const useHttpsInput = document.getElementById('useHttps');
  
  if (backendHostInput && useHttpsInput) {
    const backendHost = backendHostInput.value.trim();
    const useHttps = useHttpsInput.checked;
    
    // 保存到localStorage
    localStorage.setItem('backendHost', backendHost);
    localStorage.setItem('useHttps', useHttps.toString());
    
    // 更新端点预览
    updateEndpointPreviews();
    
    console.log('配置已保存:', { backendHost, useHttps });
  }
}

let listeningSocket = null;
let listeningStarted = false;

function showSettingsModal(show) {
  const settingsModal = document.getElementById('settingsModal');
  if (!settingsModal) return;
  if (show) settingsModal.classList.add('show');
  else settingsModal.classList.remove('show');
}

// Test HTTP health endpoint and WebSocket listening endpoint
async function testConnection() {
  const resultSpan = document.getElementById('connectionTestResult');
  if (!resultSpan) return;
  resultSpan.textContent = '测试中...';

  const cfg = getStoredConfig();
  const httpProtocol = cfg.useHttps ? 'https' : 'http';
  const wsProtocol = cfg.useHttps ? 'wss' : 'ws';
  const base = cfg.backendHost;

  // Test HTTP health
  try {
    const healthUrl = `${httpProtocol}://${base}/health`;
    const r = await fetch(healthUrl, { method: 'GET', cache: 'no-store' });
    if (r.ok) {
      resultSpan.textContent = `Health OK (${healthUrl})`;
    } else {
      resultSpan.textContent = `Health fail: ${r.status}`;
    }
  } catch (err) {
    resultSpan.textContent = `Health error: ${err && err.message}`;
  }

  // Test WS listening (open then close quickly)
  try {
    const listeningUrl = `${wsProtocol}://${base}/listening`;
    await testWebSocketOpen(listeningUrl, 3000);
    resultSpan.textContent += `; Listening OK (${listeningUrl})`;
  } catch (err) {
    resultSpan.textContent += `; Listening error: ${err && err.message}`;
  }
}

function testWebSocketOpen(url, timeout = 3000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    try {
      const ws = new WebSocket(url);
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          try { ws.close(); } catch(e){}
          reject(new Error('timeout')); 
        }
      }, timeout);
      ws.addEventListener('open', () => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          ws.close();
          resolve(true);
        }
      });
      ws.addEventListener('error', (ev) => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          reject(new Error('ws error'));
        }
      });
    } catch (err) {
      reject(err);
    }
  });
}

function appendLiveMessage(text) {
  const live = document.getElementById('liveMessages');
  if (!live) return;
  const p = document.createElement('div');
  p.className = 'message';
  p.textContent = text;
  live.appendChild(p);
}

function startListening() {
  if (listeningStarted) return;
  console.log('[renderer] startListening clicked');
  const cfg = getStoredConfig();
  const wsProtocol = cfg.useHttps ? 'wss' : 'ws';
  const url = `${wsProtocol}://${cfg.backendHost}/listening`;

  try {
    listeningSocket = new WebSocket(url);
    listeningSocket.addEventListener('open', () => {
      console.log('[renderer] listening socket open', url);
      listeningStarted = true;
      document.getElementById('startListeningBtn').textContent = 'Stop Listening';
      appendLiveMessage(`[listening] connected to ${url}`);
      const live = document.getElementById('liveMessages');
      if (live) live.style.display = '';
    });
    listeningSocket.addEventListener('message', (evt) => {
      console.log('[renderer] listening message:', evt.data);
      appendLiveMessage(evt.data || JSON.stringify(evt));
    });
    listeningSocket.addEventListener('close', () => {
      console.log('[renderer] listening socket closed');
      listeningStarted = false;
      document.getElementById('startListeningBtn').textContent = 'Start Listening';
      appendLiveMessage('[listening] closed');
    });
    listeningSocket.addEventListener('error', (err) => {
      console.log('[renderer] listening socket error', err);
      appendLiveMessage('[listening] error');
    });
  } catch (err) {
    console.log('[renderer] startListening exception', err && err.message);
    appendLiveMessage('[listening] failed to start: ' + (err && err.message));
  }
}

function stopListening() {
  console.log('[renderer] stopListening clicked');
  if (!listeningStarted) return;
  try {
    listeningSocket && listeningSocket.close();
  } catch (err) {
    console.warn('stopListening error', err && err.message);
  }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  console.log('[renderer] DOMContentLoaded');
  initializeConfigForm();
  
  // show welcome by default
  const welcome = document.getElementById('welcomeMessage');
  if (welcome) welcome.style.display = '';

  const backendHostInput = document.getElementById('backendHost');
  const useHttpsInput = document.getElementById('useHttps');

  if (backendHostInput) {
    backendHostInput.addEventListener('input', updateEndpointPreviews);
  }
  
  if (useHttpsInput) {
    useHttpsInput.addEventListener('change', updateEndpointPreviews);
  }
  
  const saveBtn = document.getElementById('saveSettingsBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveConfiguration);
  }

  // Replace previous modal open/close wiring to toggle 'show' class
  const openBtn = document.getElementById('openSettingsBtn');
  const closeBtn = document.getElementById('closeSettingsBtn');
  const cancelBtn = document.getElementById('cancelSettingsBtn');
  const settingsModal = document.getElementById('settingsModal');

  if (openBtn && settingsModal) {
    openBtn.addEventListener('click', () => { showSettingsModal(true); });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', () => { showSettingsModal(false); });
  }
  if (cancelBtn) {
    cancelBtn.addEventListener('click', () => { showSettingsModal(false); });
  }

  // Test connection button
  const testBtn = document.getElementById('testConnectionBtn');
  if (testBtn) testBtn.addEventListener('click', testConnection);

  // Start/Stop listening button
  const startBtn = document.getElementById('startListeningBtn');
  if (startBtn) startBtn.addEventListener('click', () => {
    if (!listeningStarted) startListening(); else stopListening();
  });

  console.log('[renderer] initialized UI elements (updated)');
});