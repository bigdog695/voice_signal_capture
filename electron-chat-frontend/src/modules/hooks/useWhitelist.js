import { useCallback, useRef } from 'react';
import { useConfig } from '../config/ConfigContext';

export function useWhitelist() {
  const { urls } = useConfig();
  const isRegistered = useRef(false);
  const registrationPromise = useRef(null);

  const registerToWhitelist = useCallback(async () => {
    // 避免重复注册
    if (isRegistered.current) {
      return true;
    }

    // 如果正在注册，等待结果
    if (registrationPromise.current) {
      return await registrationPromise.current;
    }

    // 开始注册流程
    registrationPromise.current = (async () => {
      try {
        console.log('Registering IP to whitelist...');
        const response = await fetch(urls.whitelistRegister());
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Whitelist registration successful:', data);
        isRegistered.current = true;
        return true;
      } catch (error) {
        console.error('Failed to register to whitelist:', error);
        isRegistered.current = false;
        return false;
      } finally {
        registrationPromise.current = null;
      }
    })();

    return await registrationPromise.current;
  }, [urls]);

  const ensureWhitelisted = useCallback(async () => {
    if (!isRegistered.current) {
      await registerToWhitelist();
    }
    return isRegistered.current;
  }, [registerToWhitelist]);

  return {
    registerToWhitelist,
    ensureWhitelisted,
    isRegistered: () => isRegistered.current
  };
}