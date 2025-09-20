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

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
  initializeConfigForm();
  
  // 监听配置输入变化，实时更新预览
  const backendHostInput = document.getElementById('backendHost');
  const useHttpsInput = document.getElementById('useHttps');
  
  if (backendHostInput) {
    backendHostInput.addEventListener('input', updateEndpointPreviews);
  }
  
  if (useHttpsInput) {
    useHttpsInput.addEventListener('change', updateEndpointPreviews);
  }
  
  // 监听保存按钮
  const saveBtn = document.getElementById('saveSettingsBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveConfiguration);
  }
});