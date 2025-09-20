import React from 'react';
import { useHealth } from '../hooks/useHealth';

export const Sidebar = ({ onOpenSettings, onShowMonitor }) => {
  const { ok: healthOk, checking } = useHealth({ intervalMs: 2000, successIntervalMs: 15000 });
  const statusClass = healthOk ? 'connected' : 'disconnected';
  const statusText = healthOk ? '服务可用' : (checking ? '检测中...' : '未连接');
  return (
    <div className="sidebar-modern">
      <div className="sidebar-header-modern">
        <div className="logo-section">
          <div className="app-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none">
              <path d="M12 1L3 5V11C3 16.55 6.84 21.74 12 23C17.16 21.74 21 16.55 21 11V5L12 1Z" stroke="currentColor" strokeWidth="2" fill="url(#gradient)"/>
              <defs>
                <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#3b82f6"/>
                  <stop offset="100%" stopColor="#1d4ed8"/>
                </linearGradient>
              </defs>
            </svg>
          </div>
          <h2>通话记录</h2>
        </div>
      </div>
      
      <div className="chat-history-modern">
        <div className="empty-history">
          <div className="empty-history-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
              <path d="M8 12H16M8 16H16M6 20H18C19.1046 20 20 19.1046 20 18V6C20 4.89543 19.1046 4 18 4H6C4.89543 4 4 4.89543 4 6V18C4 19.1046 4.89543 20 6 20Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <p>暂无通话记录</p>
          <span>新的通话记录将在此显示</span>
        </div>
      </div>
      
      <div className="sidebar-footer-modern">
        <div className="connection-status-modern">
          <div className={`status-indicator-modern ${statusClass}`}>
            <div className="status-dot-modern"></div>
          </div>
            <div className="status-info">
              <span className="status-label">连接状态</span>
              <span className="status-text">{statusText}</span>
            </div>
        </div>
        
        <div className="action-buttons">
          <button className="primary-action-btn" onClick={onShowMonitor}>
            <div className="btn-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="3" fill="currentColor"/>
                <path d="M12 1v6m0 10v6m11-7h-6m-10 0H1" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
            </div>
            <div className="btn-content">
              <span className="btn-title">实时监听</span>
              <span className="btn-subtitle">开始监听通话</span>
            </div>
          </button>
        </div>
        
        <button className="settings-btn-modern" onClick={onOpenSettings}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" stroke="currentColor" strokeWidth="1.5"/>
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.5"/>
          </svg>
          系统设置
        </button>
      </div>
    </div>
  );
};
