import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Sidebar } from '../ui/Sidebar';
import { SettingsModal } from '../ui/SettingsModal';
import { MonitorView } from '../ui/MonitorView';
import { ASRView } from '../ui/ASRView';
import { CallDisplay } from '../ui/CallDisplay';
import { useListening } from '../hooks/useListening';
import packageInfo from '../../../package.json';

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

const HistoryView = ({ data, onClose, onRefresh }) => {
  const events = useMemo(() => (Array.isArray(data?.events) ? data.events : []), [data]);
  const ticketInfo = useMemo(() => {
    if (!events.length) return null;
    const t = events.find(e => e && e.system === 'ticket' && e.ticket);
    return t && t.ticket ? t.ticket : null;
  }, [events]);
  const hasEnd = useMemo(() => events.some(e => e && e.system === 'conversation_end'), [events]);
  const hasTicketError = useMemo(() => events.some(e => e && e.system === 'ticket_error'), [events]);

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
      if (event.system === 'ticket' && event.ticket) {
        acc.push({
          kind: 'ticket',
          id: `ticket-${index}`,
          ticket: event.ticket,
          timestamp: formatDateTime(event.ts || event.time)
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
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState(null);

  const handleRefresh = async () => {
    if (!onRefresh || refreshing) return;
    setRefreshing(true);
    setRefreshError(null);
    try {
      const result = await onRefresh();
      if (result && result.error) {
        setRefreshError(result.error);
      }
    } catch (err) {
      setRefreshError(err && err.message ? err.message : '发生未知错误');
    } finally {
      setRefreshing(false);
    }
  };

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
            <h3 className="monitor-title">{ticketInfo?.ticket_title || '历史通话回放'}</h3>
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
            {!ticketInfo && events.some(e => e && e.system === 'conversation_end') && !events.some(e => e && e.system === 'ticket_error') && !events.some(e => e && e.system === 'ticket') && (
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
                <div style={{ maxWidth: 520, background: '#f3f4f6', color: '#374151', borderRadius: 8, padding: 16, textAlign: 'center', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" opacity="0.4" />
                      <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2"/>
                    </svg>
                    <span>正在生成工单…</span>
                  </div>
                </div>
              </div>
            )}
            {!ticketInfo && events.some(e => e && e.system === 'ticket_error') && !events.some(e => e && e.system === 'ticket') && (
              <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
                <div style={{ maxWidth: 520, background: '#fef2f2', color: '#b91c1c', borderRadius: 8, padding: 16, textAlign: 'center', boxShadow: '0 1px 2px rgba(0,0,0,0.05)', border: '1px solid #fecaca' }}>
                  工单生成失败，请稍后刷新重试
                </div>
              </div>
            )}
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
                ) : item.kind === 'ticket' ? (
                  <div key={item.id} style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
                    <div style={{ maxWidth: 520, background: '#f1f5f9', color: '#111827', borderRadius: 8, padding: 16, textAlign: 'left', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>
                      <div style={{ fontWeight: 600, marginBottom: 8 }}>工单信息</div>
                      <div style={{ lineHeight: 1.6 }}>
                        <div><span style={{ color: '#6b7280' }}>类型：</span>{item.ticket?.ticket_type || '-'}</div>
                        <div><span style={{ color: '#6b7280' }}>区域：</span>{item.ticket?.ticket_zone || '-'}</div>
                        <div><span style={{ color: '#6b7280' }}>标题：</span>{item.ticket?.ticket_title || '-'}</div>
                        <div><span style={{ color: '#6b7280' }}>内容：</span>{item.ticket?.ticket_content || '-'}</div>
                      </div>
                    </div>
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
{onRefresh && (
              <button
                className="close-button"
                onClick={handleRefresh}
                title={refreshing ? '\u6b63\u5728\u91cd\u65b0\u751f\u6210...' : '\u91cd\u65b0\u751f\u6210\u5de5\u5355'}
                style={{ marginTop: 8, opacity: refreshing ? 0.75 : 1, cursor: refreshing ? 'default' : 'pointer' }}
                disabled={refreshing}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                  <path d="M4 4v6h6" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  <path d="M20 20v-6h-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  <path d="M20 10a8 8 0 1 0-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none"/>
                </svg>
                {refreshing ? '\u6b63\u5728\u91cd\u65b0\u751f\u6210...' : '\u91cd\u65b0\u751f\u6210\u5de5\u5355'}
              </button>
            )}
            {refreshError && (
              <div style={{ marginTop: 8, color: '#b91c1c', fontSize: 12 }}>生成失败：{refreshError}</div>
            )}
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
  const [clientIp, setClientIp] = useState('');
  const { lastAsrUpdate } = useListening();
  const lastHandledUpdateRef = useRef(null);

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

  // Fetch local IPv4 once and display next to version
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        if (!window?.electronAPI?.invoke) {
          console.warn('[Layout] electronAPI.invoke not available');
          return;
        }
        const cfg = await window.electronAPI.invoke('config:get');
        console.log('[Layout] config:get ->', cfg);
        const ip = cfg && cfg.clientIp ? cfg.clientIp : '';
        console.log('[Layout] derived clientIp =', ip);
        if (mounted && ip) setClientIp(ip);
      } catch (e) {
        console.warn('[Layout] failed to fetch client IP via config:get', e && e.message);
      }
    })();
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (!lastAsrUpdate || !lastAsrUpdate.id) return;
    if (view === 'monitor') {
      lastHandledUpdateRef.current = lastAsrUpdate.id;
      return;
    }
    if (lastHandledUpdateRef.current === lastAsrUpdate.id) return;
    lastHandledUpdateRef.current = lastAsrUpdate.id;
    setView('monitor');
  }, [lastAsrUpdate, view]);

  return (
    <div className="app-container">
      <div className="version-tags">
        <div className="info-tag">{`v${packageInfo.version}`}</div>
        {clientIp ? <div className="info-tag">{clientIp}</div> : null}
      </div>
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} onShowMonitor={()=>setView('monitor')} onSelectHistory={handleSelectHistory} />
      <div className="main-content">
        {view === 'monitor' && <MonitorView onClose={() => setView('none')} />}
        {view === 'asr' && <ASRView />}
        {view === 'call' && <CallDisplay call={selectedCall} />}
        {view === 'history' && <HistoryView data={historyData} onClose={handleCloseHistory} onRefresh={async () => {
          if (!historyData?.id || !window.electronAPI?.invoke) {
            return { ok: false, error: 'invalid_id' };
          }
          try {
            const regen = await window.electronAPI.invoke('history:regenerateTicket', historyData.id);
            if (!regen?.ok) {
              console.warn('[HistoryView] regenerate ticket failed', regen?.error || 'unknown error');
              return { ok: false, error: regen?.error || 'ticket_request_failed' };
            }
            const fresh = await window.electronAPI.invoke('history:load', historyData.id);
            setHistoryData(fresh);
            return { ok: true };
          } catch (e) {
            const msg = e && e.message ? e.message : 'unknown_error';
            console.warn('[HistoryView] refresh failed', msg);
            return { ok: false, error: msg };
          }
        }} />}
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
