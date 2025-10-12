import React, { useEffect, useRef, useState } from 'react';
import { useListening } from '../hooks/useListening';
import { useHealth } from '../hooks/useHealth';

export const MonitorView = ({ onClose }) => {
  const { bubbles, isListening } = useListening();
  const { ok: healthOk, checking: healthChecking } = useHealth({ intervalMs: 2000, successIntervalMs: 15000 });
  const messagesListRef = useRef(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [userHasScrolled, setUserHasScrolled] = useState(false);
  const lastScrollTime = useRef(0);
  const [ticketInfo, setTicketInfo] = useState(null);
  const currentUniqueKeyRef = useRef(null);

  // Track current session's unique_key from bubbles and clear ticket when needed
  useEffect(() => {
    // If bubbles are empty, clear everything (new session starting or no data)
    if (bubbles.length === 0) {
      if (ticketInfo) {
        console.log('[MonitorView] Bubbles cleared, clearing ticket');
        setTicketInfo(null);
      }
      currentUniqueKeyRef.current = null;
      return;
    }
    
    // Get unique_key from the latest bubble that has it
    const latestBubble = bubbles.find(b => b.uniqueKey || b.metadata?.unique_key);
    const newUniqueKey = latestBubble?.uniqueKey || latestBubble?.metadata?.unique_key || null;
    
    // If unique_key changed, clear ticket info (new session detected)
    if (newUniqueKey && currentUniqueKeyRef.current && newUniqueKey !== currentUniqueKeyRef.current) {
      console.log('[MonitorView] Session changed, clearing ticket', {
        old: currentUniqueKeyRef.current,
        new: newUniqueKey
      });
      setTicketInfo(null);
    }
    
    if (newUniqueKey) {
      currentUniqueKeyRef.current = newUniqueKey;
    }
  }, [bubbles, ticketInfo]);

  // Listen for ticket:generated event from main process
  useEffect(() => {
    if (!window.electronAPI || typeof window.electronAPI.on !== 'function') return;
    
    const handleTicketGenerated = (data) => {
      console.log('[MonitorView] ticket:generated received', data);
      if (data && data.ticket) {
        // Only set ticket if it belongs to current session
        // We can't verify unique_key directly from data, so we rely on the timing
        // The main process sends ticket right after the session ends
        // If bubbles were cleared (new session started), currentUniqueKeyRef would be updated
        console.log('[MonitorView] Setting ticket for current session');
        setTicketInfo(data.ticket);
      }
    };
    
    const cleanup = window.electronAPI.on('ticket:generated', handleTicketGenerated);
    return cleanup;
  }, []);

  // 滚动监听，判断是否显示"滚动到底部"按钮
  useEffect(() => {
    const scrollElement = messagesListRef.current;
    if (!scrollElement) return;

    const handleScroll = () => {
      const now = Date.now();
      const isScrolledToBottom = scrollElement.scrollHeight - scrollElement.clientHeight <= scrollElement.scrollTop + 50;
      
      // 检测用户是否主动滚动（非自动滚动触发的）
      if (now - lastScrollTime.current > 100) {
        setUserHasScrolled(!isScrolledToBottom);
      }
      
      setShowScrollToBottom(!isScrolledToBottom && bubbles.length > 3);
    };

    scrollElement.addEventListener('scroll', handleScroll, { passive: true });
    return () => scrollElement.removeEventListener('scroll', handleScroll);
  }, [bubbles.length]);

  // 自动滚动到底部 - 实时监听场景下始终滚动到最新消息
  useEffect(() => {
    if (messagesListRef.current && bubbles.length > 0) {
      const scrollElement = messagesListRef.current;
      
      console.log('Bubbles updated, count:', bubbles.length, 'Latest bubble:', bubbles[bubbles.length - 1]);
      
      // 强制滚动到底部，确保用户总能看到最新消息
      lastScrollTime.current = Date.now();
      
      // 使用多重确保机制确保滚动生效
      const scrollToEnd = () => {
        if (scrollElement && scrollElement.scrollHeight > scrollElement.clientHeight) {
          const maxScroll = scrollElement.scrollHeight - scrollElement.clientHeight;
          scrollElement.scrollTop = maxScroll;
          console.log('Scrolled to:', scrollElement.scrollTop, 'Max scroll:', maxScroll);
        }
      };
      
      // 立即滚动
      scrollToEnd();
      
      // 延迟滚动，确保 DOM 完全更新
      setTimeout(scrollToEnd, 50);
      requestAnimationFrame(() => {
        setTimeout(scrollToEnd, 0);
      });
    }
  }, [bubbles]);

  // 平滑滚动到底部的函数
  const scrollToBottom = () => {
    if (messagesListRef.current) {
      setUserHasScrolled(false); // 重置用户滚动状态
      lastScrollTime.current = Date.now();
      messagesListRef.current.scrollTo({
        top: messagesListRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  };

  return (
    <div className="monitor-view">
      <div className="monitor-header">
        <div className="header-left">
          <div className="monitor-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="3" fill="currentColor"/>
              <path d="M12 1v6m0 10v6m11-7h-6m-10 0H1" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          </div>
          <div className="header-info">
            <h3 className="monitor-title">实时通话监听</h3>
            <div className="connection-badge">
              <div className={`status-dot ${isListening ? 'connected' : (healthOk ? 'connected' : 'disconnected')}`}></div>
              <span className="status-text">
                {isListening ? '正在监听' : (healthOk ? '服务可用' : (healthChecking ? '检测中...' : '未连接'))}
              </span>
            </div>
          </div>
        </div>
        <button className="close-button" onClick={onClose}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
            <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          关闭
        </button>
      </div>
      
      <div className="chat-container">
        {bubbles.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z" fill="currentColor" opacity="0.3"/>
                <circle cx="12" cy="12" r="3" fill="currentColor"/>
              </svg>
            </div>
            <h4>等待通话数据</h4>
            <p>当有新的通话内容时，将在此处实时显示</p>
          </div>
        ) : (
          <div className="messages-container">
            <div className="messages-list" ref={messagesListRef}>
              {bubbles.map((bubble, index) => (
                <div key={bubble.id || index} className={`message-bubble ${bubble.role || 'other'}`}> 
                  <div className="bubble-content">
                    <span className="text-stable">{bubble.text}</span>
                  </div>
                  <div className="message-meta">
                    <span className="timestamp">{new Date(bubble.time || Date.now()).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))}
              {ticketInfo && (
                <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16, padding: '0 16px' }}>
                  <div style={{ maxWidth: 520, background: '#f1f5f9', color: '#111827', borderRadius: 8, padding: 16, textAlign: 'left', boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
                    <div style={{ fontWeight: 600, marginBottom: 12, fontSize: '15px', display: 'flex', alignItems: 'center', gap: 8 }}>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                      </svg>
                      工单信息
                    </div>
                    <div style={{ lineHeight: 1.8, fontSize: '14px' }}>
                      <div><span style={{ color: '#6b7280', minWidth: 48, display: 'inline-block' }}>类型：</span><span style={{ fontWeight: 500 }}>{ticketInfo.ticket_type || '-'}</span></div>
                      <div><span style={{ color: '#6b7280', minWidth: 48, display: 'inline-block' }}>区域：</span><span style={{ fontWeight: 500 }}>{ticketInfo.ticket_zone || '-'}</span></div>
                      <div><span style={{ color: '#6b7280', minWidth: 48, display: 'inline-block' }}>标题：</span><span style={{ fontWeight: 500 }}>{ticketInfo.ticket_title || '-'}</span></div>
                      <div><span style={{ color: '#6b7280', minWidth: 48, display: 'inline-block' }}>内容：</span><span style={{ fontWeight: 500 }}>{ticketInfo.ticket_content || '-'}</span></div>
                    </div>
                  </div>
                </div>
              )}
            </div>
            
            {showScrollToBottom && (
              <button className="scroll-to-bottom-btn" onClick={scrollToBottom}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M7 14L12 19L17 14M12 5V18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <span>回到底部</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
