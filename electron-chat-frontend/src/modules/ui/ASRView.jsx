import React, { useState } from 'react';

export const ASRView = () => {
  const [lines, setLines] = useState([]);
  return (
    <div style={{padding:20}}>
      <h3>Real-time Transcription</h3>
      <div className="asr-content-wrapper"><div className="asr-content">
        {lines.map((l,i)=>(<div key={i}>{l}</div>))}
      </div></div>
    </div>
  );
};
