import React from 'react';
import { ConfigProvider } from './config/ConfigContext';
import { BootstrapConnect } from './BootstrapConnect';
import { Layout } from './layout/Layout';

export const App = () => {
  return (
    <ConfigProvider>
      <BootstrapConnect />
      <Layout />
    </ConfigProvider>
  );
};
