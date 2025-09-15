import React, { useState } from 'react';
import { Sidebar } from '../ui/Sidebar';
import { SettingsModal } from '../ui/SettingsModal';
import { MonitorView } from '../ui/MonitorView';
import { ASRView } from '../ui/ASRView';
import { CallDisplay } from '../ui/CallDisplay';

export const Layout = () => {
  const [view, setView] = useState('none'); // 'monitor'|'asr'|'call'|'none'
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedCall, setSelectedCall] = useState(null);

  return (
    <div className="app-container">
      <Sidebar onOpenSettings={() => setSettingsOpen(true)} onShowMonitor={()=>setView('monitor')} />
      <div className="main-content">
        {view === 'monitor' && <MonitorView onClose={() => setView('none')} />}
        {view === 'asr' && <ASRView />}
        {view === 'call' && <CallDisplay call={selectedCall} />}
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
