import React from 'react';
import { ConfigProvider } from './config/ConfigContext';
import { Layout } from './layout/Layout';

export const App = () => {
  return (
    <ConfigProvider>
      <Layout />
    </ConfigProvider>
  );
};
