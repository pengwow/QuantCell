import { ConfigProvider, App as AntdApp, theme as antdTheme } from 'antd';
import type { MessageInstance } from 'antd/es/message/interface';
import { BrowserRouter } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { DynamicRouter } from './router/DynamicRouter';
import { useConfigStore } from './store';
import { useWorkerStore } from './store/workerStore';
import { wsService } from './services/websocketService';
import { PluginProvider } from './plugins';
import './i18n/config';
import './global.css';
import './index.css';

function App() {
  const [isDarkMode, setIsDarkMode] = useState(() => document.documentElement.classList.contains('dark'));
  const loadConfig = useConfigStore((state) => state.loadConfig);
  const setMessageApi = useWorkerStore((state) => state.setMessageApi);

  useEffect(() => {
    // 加载系统配置
    console.log('[App] 开始加载系统配置');
    loadConfig();
  }, [loadConfig]);

  // 全局 WebSocket 连接管理
  useEffect(() => {
    console.log('[App] 初始化全局 WebSocket 连接');

    // 监听连接状态变化
    const handleConnectionChange = (connected: boolean) => {
      console.log('[App] WebSocket 连接状态变化:', connected);
    };

    wsService.onConnectionChange(handleConnectionChange);

    // 确保 WebSocket 连接已建立
    if (!wsService.connected) {
      console.log('[App] WebSocket 未连接，调用 connect');
      wsService.connect();
    } else {
      console.log('[App] WebSocket 已连接');
    }

    return () => {
      wsService.offConnectionChange(handleConnectionChange);
    };
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
        <BrowserRouter>
          <PluginProvider>
            <AppInjector setMessageApi={setMessageApi} />
            <DynamicRouter />
          </PluginProvider>
        </BrowserRouter>
      </AntdApp>
    </ConfigProvider>
  );
}

// 注入 Ant Design App 的 message API 到 store
function AppInjector({ setMessageApi }: { setMessageApi: (api: MessageInstance) => void }) {
  const { message: apiMessage } = AntdApp.useApp();

  useEffect(() => {
    if (setMessageApi && apiMessage) {
      setMessageApi(apiMessage);
      console.log('[App] Message API 已注入到 WorkerStore');
    }
  }, [setMessageApi, apiMessage]);

  return null;
}

export default App;
