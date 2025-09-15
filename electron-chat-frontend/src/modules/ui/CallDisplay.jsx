import React from 'react';

export const CallDisplay = ({ call }) => {
  if (!call) return <div style={{padding:40}}>No call selected.</div>;
  return (
    <div style={{padding:20}}>
      <h3>{call.title || 'Call'}</h3>
      <div style={{marginTop:12}}>
        <strong>User:</strong>
        <div>{call.transcript?.user || 'No user transcript available'}</div>
      </div>
      <div style={{marginTop:12}}>
        <strong>AI Assistant:</strong>
        <div>{call.transcript?.assistant || 'No assistant transcript available'}</div>
      </div>
    </div>
  );
};
