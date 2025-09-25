import React, { useState, useMemo } from 'react';
import { Sidebar } from '../ui/Sidebar';
import { SettingsModal } from '../ui/SettingsModal';
import { MonitorView } from '../ui/MonitorView';
import { ASRView } from '../ui/ASRView';
import { CallDisplay } from '../ui/CallDisplay';

const parseTimestamp = (value) => {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === 'number') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return null;
  return new Date(parsed);
};

const formatDateTime = (value, { withDate = true } = {}) => {
  const date = parseTimestamp(value);
  if (!date) return '';
  return withDate
    ? date.toLocaleString('zh-CN', { hour12: false })
    : date.toLocaleTimeString('zh-CN', { hour12: false });
};

const formatDuration = (ms) => {
  if (!ms || ms < 0) return '';
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}小时${String(minutes).padStart(2, '0')}分${String(seconds).padStart(2, '0')}秒`;
  }
  if (minutes > 0) {
    return `${minutes}分${String(seconds).padStart(2, '0')}秒`;
  }
  return `${seconds}秒`;
};

const HistoryView = ({ data, onClose }) => {
  const events = useMemo(() => (Array.isArray(data?.events) ? data.events : []), [data]);

  const conversationInfo = useMemo(() => {
    if (!events.length) {
      return { start: '', end: '', duration: '', messageCount: 0 };
    }
    const startEvent = events.find(evt => evt.system === 'conversation_start');
    const endEvent = [...events].reverse().find(evt => evt.system === 'conversation_end');
    const startDate = parseTimestamp(startEvent?.ts || startEvent?.time);
    const endDate = parseTimestamp(endEvent?.ts || endEvent?.time);
    const duration = startDate && endDate ? formatDuration(endDate.getTime() - startDate.getTime()) : '';
    const messageCount = events.filter(evt => typeof evt.text === 'string' && evt.text.trim().length > 0).length;
    return {
      start: formatDateTime(startDate),
      end: formatDateTime(endDate),
      duration,
      messageCount
    };
  }, [events]);

  const items = useMemo(() => {
    if (!events.length) return [];
    return events.reduce((acc, event, index) => {
      if (event.system === 'conversation_start') {
        acc.push({
          kind: 'divider',
          id: `start-${index}`,
          label: '通话开始',
          timestamp: formatDateTime(event.ts || event.time)
        });
        return acc;
      }
      if (event.system === 'conversation_end') {
        acc.push({
          kind: 'divider',
          id: `end-${index}`,
          label: event.reason ? `通话结束 · ${event.reason}` : '通话结束',
          timestamp: formatDateTime(event.ts || event.time)
        });
        return acc;
      }
      if (event.type === 'call_finished') {
        acc.push({
          kind: 'divider',
          id: `finished-${index}`,
          label: '通话结束',
          timestamp: formatDateTime(event.time || event.ts)
        });
        return acc;
      }
      const text = typeof event.text === 'string' ? event.text.trim() : '';
      if (!text) return acc;
      const role = event.role === 'citizen' || event.source === 'citizen' ? 'citizen' : 'other';
      const isPending = typeof event.type === 'string' && event.type.includes('partial');
      acc.push({
        kind: 'message',
        id: event.id || `msg-${index}`,
        role,
        text,
        timestamp: formatDateTime(event.time || event.ts, { withDate: false }),
        fullTimestamp: formatDateTime(event.time || event.ts),
        pending: isPending
      });
      return acc;
    }, []);
  }, [events]);

  const hasError = !!data?.error;

  return (
    <div className="monitor-view history-mode">
      <div className="monitor-header">
        <div className="header-left">
          <div className="monitor-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M12 1a11 11 0 1 0 11 11A11 11 0 0 0 12 1Zm0 2a9 9 0 1 1-9 9a9 9 0 0 1 9-9Zm0 3a1 1 0 0 0-1 1v4.382l-2.447 2.447a1 1 0 1 0 1.414 1.414l2.74-2.74A1 1 0 0 0 13 12V7a1 1 0 0 0-1-1Z" fill="currentColor"/>
            </svg>
          </div>
          <div className="header-info">
            <h3 className="monitor-title">历史通话回放</h3>
            <div className="history-subtitle">会话ID：{data?.id || '未知'}</div>
            <div className="connection-badge">
              <div className="status-dot connected"></div>
              <div className="badge-text">
                <span>共 {conversationInfo.messageCount} 条消息</span>
                <span>{conversationInfo.duration ? `持续时长 ${conversationInfo.duration}` : '时长未知'}</span>
              </div>
            </div>
            <div className="conversation-summary">
              <div><span className="meta-label">开始</span><span className="meta-value">{conversationInfo.start || '—'}</span></div>
              <div><span className="meta-label">结束</span><span className="meta-value">{conversationInfo.end || '—'}</span></div>
            </div>
          </div>
        </div>
        {onClose && (
          <button className="close-button" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            返回
          </button>
        )}
      </div>

      <div className="chat-container">
        {hasError ? (
          <div className="empty-state">
            <h4>无法加载会话</h4>
            <p>请稍后重试或选择其他记录。</p>
          </div>
        ) : items.length === 0 ? (
          <div className="empty-state">
            <h4>暂无历史数据</h4>
            <p>选择其他通话记录查看详情。</p>
          </div>
        ) : (
          <div className="messages-container history-messages">
            <div className="messages-list history-messages-list">
              {items.map(item =>
                item.kind === 'divider' ? (
                  <div key={item.id} className="conversation-divider" title={item.timestamp || undefined}>
                    <span>{item.label}</span>
                    {item.timestamp && <span className="divider-time">{item.timestamp}</span>}
                  </div>
                ) : (
                  <div
                    key={item.id}
                    className={`message-bubble ${item.role}${item.pending ? ' pending' : ''}`}
                    title={item.fullTimestamp || undefined}
                  >
                    <div className="bubble-content">
                      <span className="text-stable">{item.text}</span>
                    </div>
                    {item.timestamp && (
                      <div className="message-meta">
                        <span className="timestamp">{item.timestamp}</span>
                      </div>
                    )}
                  </div>
                )
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export const Layout = () => {
  const [view, setView] = useState('none'); // 'monitor'|'asr'|'call'|'none'|'history'
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedCall, setSelectedCall] = useState(null);
  const [historyData, setHistoryData] = useState(null);

  const handleSelectHistory = (data) => {
    if (data && !data.error) {
      setHistoryData(data);
      setView('history');
    }
  };

  const handleCloseHistory = () => {
    setView('none');
    setHistoryData(null);
  };

  return (
    <div className="app-container">
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} onShowMonitor={()=>setView('monitor')} onSelectHistory={handleSelectHistory} />
      <div className="main-content">
        {view === 'monitor' && <MonitorView onClose={() => setView('none')} />}
        {view === 'asr' && <ASRView />}
        {view === 'call' && <CallDisplay call={selectedCall} />}
        {view === 'history' && <HistoryView data={historyData} onClose={handleCloseHistory} />}
        {view === 'none' && (
          <div style={{padding:40}}>
            <h2>Call Records Display</h2>
            <p>Select a call or open realtime monitor.</p>
          </div>
        )}
      </div>
      <SettingsModal open={settingsOpen} onClose={()=>setSettingsOpen(false)} />
    </div>
  );
};
