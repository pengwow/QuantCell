import { ConfigProvider, App as AntdApp, theme as antdTheme } from 'antd';
import type { MessageInstance } from 'antd/es/message/interface';
import { BrowserRouter } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { DynamicRouter } from './router/DynamicRouter';
import CrashMask from './desktop/CrashMask';
import { isTauri } from './desktop/env';
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

  // ponytail: 量化交易语义色，集中在 ConfigProvider token 里作为单一真相源。
  // 各组件（QUANT_COLORS、ECharts、MetricCard）通过 theme.useToken() 取色，
  // 禁止在子组件里硬编码 QUANT_COLORS.positive / QUANT_COLORS.negative / QUANT_COLORS.info 等 antd v5 风格颜色。
  const tradingToken = isDarkMode
    ? {
        // 暗色模式
        colorPrimary: '#f97316',
        colorInfo: '#478be6',
        colorSuccess: '#57ab5a',   // 正收益 / 盈利
        colorWarning: '#daaa3f',
        colorError: '#e5534b',     // 负收益 / 亏损
        colorBgBase: '#17191c',
        colorTextBase: '#fafaf9',
        // Chart/ECharts 专用
        colorChartLine: '#478be6',
        colorChartAxis: '#4b5563',
        colorChartSplit: '#374151',
        colorChartMark: '#9ca3af',
        colorChartGradientStart: 'rgba(71, 139, 230, 0.35)',
        colorChartGradientEnd: 'rgba(71, 139, 230, 0.04)',
        colorDrawdownArea: 'rgba(229, 83, 75, 0.18)',
      }
    : {
        // 亮色模式
        colorPrimary: '#ea580c',
        colorInfo: '#0969da',
        colorSuccess: '#1a7f37',
        colorWarning: '#eac54f',
        colorError: '#d1242f',
        colorBgBase: '#ffffff',
        colorTextBase: '#141414',
        // Chart/ECharts 专用
        colorChartLine: '#0969da',
        colorChartAxis: '#d1d5db',
        colorChartSplit: '#e5e7eb',
        colorChartMark: '#9ca3af',
        colorChartGradientStart: 'rgba(9, 105, 218, 0.25)',
        colorChartGradientEnd: 'rgba(9, 105, 218, 0.02)',
        colorDrawdownArea: 'rgba(209, 36, 47, 0.12)',
      };

  return (
    <ConfigProvider
      theme={{
        algorithm: isDarkMode ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: tradingToken,
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
            {isTauri() && <CrashMask />}
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
