import React from 'react';
import { ConfigProvider } from './config/ConfigContext';
import { ListeningProvider } from './listening/ListeningProvider';
import { Layout } from './layout/Layout';

export const App = () => {
  return (
    <ConfigProvider>
      <ListeningProvider autoConnect>
        <Layout />
      </ListeningProvider>
    </ConfigProvider>
  );
};
