import React, { useState, useEffect } from 'react';
import { useConfig } from '../config/ConfigContext';
import { useWhitelist } from '../hooks/useWhitelist';

export const SettingsModal = ({ open, onClose }) => {
  const { backendHost, useHttps, saveConfig, urls, ready } = useConfig();
  const { registerToWhitelist } = useWhitelist();
  const [host, setHost] = useState(backendHost);
  const [https, setHttps] = useState(useHttps);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState('');

  useEffect(()=>{ if(open){ setHost(backendHost); setHttps(useHttps);} }, [open, backendHost, useHttps]);

  if(!open) return null;

  const testConnection = async () => {
    setTesting(true); 
    setTestResult('Testing connection...');
    
    try {
      // Build test URL with current input values (not saved config)
      const testHost = host.trim();
      if (!testHost) {
        setTestResult('✗ 请输入后端地址');
        setTesting(false);
        return;
      }
      const protocol = https ? 'https' : 'http';
      const testUrl = `${protocol}://${testHost}/health`;
      
      console.log('[Settings] Testing connection to:', testUrl);
      
      // 1. 测试基本连接
      const healthRes = await fetch(testUrl);
      if (!healthRes.ok) throw new Error('Health check failed: HTTP ' + healthRes.status);
      
      const healthData = await healthRes.json();
      console.log('[Settings] Health check OK:', healthData);
      setTestResult('Health OK, registering whitelist...');
      
      // 2. 注册到白名单
      const whitelisted = await registerToWhitelist();
      if (!whitelisted) throw new Error('Failed to register to whitelist');
      
      setTestResult('✓ Connection OK, Whitelist registered');
    } catch (e) {
      console.error('[Settings] Test connection failed:', e);
      setTestResult('✗ Failed: ' + e.message);
    } finally { 
      setTesting(false); 
    }
  };

  const save = () => { saveConfig(host.trim(), https); onClose(); };

  return (
    <div className="modal show">
      <div className="modal-content">
        <div className="modal-header">
          <h3>后端服务配置</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          <div className="setting-group">
            <label>后端服务地址:</label>
            <input value={host} onChange={e=>setHost(e.target.value)} />
            <small className="setting-hint">示例: your-host:8000</small>
          </div>
          <div className="setting-group">
            <label>使用 HTTPS/WSS:</label>
            <input type="checkbox" checked={https} onChange={e=>setHttps(e.target.checked)} />
          </div>
          <div className="connection-test">
            <button className="btn btn-secondary" onClick={testConnection} disabled={testing}>测试连接</button>
            <span className="connection-status">{testResult}</span>
          </div>
          <div className="endpoint-preview">
            <h4>预览:</h4>
            <div className="endpoint-list">
              <div className="endpoint-item"><span className="endpoint-label">Listening:</span> <code>{urls.listening()}</code></div>
              <div className="endpoint-item"><span className="endpoint-label">ASR:</span> <code>{urls.asr()}</code></div>
              <div className="endpoint-item"><span className="endpoint-label">Chat:</span> <code>{urls.chat()}</code></div>
              <div className="endpoint-item"><span className="endpoint-label">Health:</span> <code>{urls.health()}</code></div>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>取消</button>
          <button className="btn btn-primary" onClick={save}>保存设置</button>
        </div>
      </div>
    </div>
  );
};
