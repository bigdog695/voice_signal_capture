import React, { useState, useMemo } from 'react';
import { Sidebar } from '../ui/Sidebar';
import { SettingsModal } from '../ui/SettingsModal';
import { MonitorView } from '../ui/MonitorView';
import { ASRView } from '../ui/ASRView';
import { CallDisplay } from '../ui/CallDisplay';

const HistoryView = ({ data }) => {
  if (!data || !data.events) return <div style={{ padding: 24 }}>暂无历史数据</div>;
  return (
    <div className="history-view" style={{ padding: 24, overflowY: 'auto', height: '100%' }}>
      <h3 style={{ marginTop: 0 }}>历史会话：{data.id}</h3>
      <div style={{ fontSize: 12, color: '#666', marginBottom: 12 }}>共 {data.events.length} 行记录</div>
      {data.events.map((e, i) => {
        if (e.system === 'conversation_start') return <div key={i} className="history-divider">—— 开始 ——</div>;
        if (e.system === 'conversation_end') return <div key={i} className="history-divider">—— 结束 ({e.reason}) ——</div>;
        if (e.type === 'call_finished') return <div key={i} className="history-divider">（结束）</div>;
        if (!e.type) return null;
        const role = e.role || (e.source === 'citizen' ? 'citizen' : 'other');
        return (
          <div key={i} className={`bubble ${role}`} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12, opacity: 0.6 }}>{e.time || e.ts}</div>
            <div>{e.text}</div>
          </div>
        );
      })}
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

  return (
    <div className="app-container">
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} onShowMonitor={()=>setView('monitor')} onSelectHistory={handleSelectHistory} />
      <div className="main-content">
        {view === 'monitor' && <MonitorView onClose={() => setView('none')} />}
        {view === 'asr' && <ASRView />}
        {view === 'call' && <CallDisplay call={selectedCall} />}
        {view === 'history' && <HistoryView data={historyData} />}
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
