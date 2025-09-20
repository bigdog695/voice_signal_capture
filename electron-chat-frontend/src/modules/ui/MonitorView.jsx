import React, { useEffect, useRef, useState } from 'react';
import { useListening } from '../hooks/useListening';

export const MonitorView = ({ onClose }) => {
  const { bubbles, isListening, startListening, stopListening } = useListening();
  const messagesListRef = useRef(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [userHasScrolled, setUserHasScrolled] = useState(false);
  const lastScrollTime = useRef(0);

  // Start connection when monitor opens, stop when closes
  useEffect(() => {
    startListening();
    return () => stopListening();
  }, [startListening, stopListening]);

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
              <div className={`status-dot ${isListening ? 'connected' : 'disconnected'}`}></div>
              <span className="status-text">
                {isListening ? '正在监听' : '未连接'}
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
                <div key={bubble.id || index} className={`message-bubble ${bubble.type || ''}`}> 
                  <div className="bubble-content">
                    <span className="text-stable">{bubble.text}</span>
                  </div>
                  <div className="message-meta">
                    <span className="timestamp">{new Date(bubble.time || Date.now()).toLocaleTimeString()}</span>
                  </div>
                </div>
              ))}
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
