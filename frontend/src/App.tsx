import { ConfigProvider, App as AntdApp, theme as antdTheme } from 'antd';
import { RouterProvider } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { router } from './router';
import { useConfigStore } from './store';
import './i18n/config';
import './global.css';
import './index.css';

function App() {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const loadConfig = useConfigStore((state) => state.loadConfig);

  useEffect(() => {
    // 加载系统配置
    console.log('[App] 开始加载系统配置');
    loadConfig();
  }, [loadConfig]);

  // 输出当前全局配置（用于调试）
  useEffect(() => {
    const config = useConfigStore.getState().config;
    console.log('[App] 当前全局配置:', config);
  }, []);

  useEffect(() => {
    // 监听主题变化
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          const isDark = document.documentElement.classList.contains('dark');
          setIsDarkMode(isDark);
        }
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });

    // 初始检查
    setIsDarkMode(document.documentElement.classList.contains('dark'));

    return () => observer.disconnect();
  }, []);

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: isDarkMode ? '#f97316' : '#ea580c',
          colorInfo: isDarkMode ? '#478be6' : '#0969da',
          colorSuccess: isDarkMode ? '#57ab5a' : '#1a7f37',
          colorWarning: isDarkMode ? '#daaa3f' : '#eac54f',
          colorError: isDarkMode ? '#e5534b' : '#d1242f',
          colorBgBase: isDarkMode ? '#17191c' : '#ffffff',
          colorTextBase: isDarkMode ? '#fafaf9' : '#141414',
        },
        components: {
          Layout: {
            bodyBg: 'transparent',
            headerBg: 'transparent',
            siderBg: 'transparent',
          },
        },
      }}
    >
      <AntdApp>
        <RouterProvider router={router} />
      </AntdApp>
    </ConfigProvider>
  );
}

export default App;
