import { ConfigProvider, App as AntdApp, theme as antdTheme } from 'antd';
import type { MessageInstance } from 'antd/es/message/interface';
import { BrowserRouter } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { DynamicRouter } from './router/DynamicRouter';
import CrashMask from './desktop/CrashMask';
import { isTauri } from './desktop/env';
import { useConfigStore } from './store';
import { useWorkerStore } from './store/workerStore';
import { wsService } from './services/websocketService';
import { RESEARCH_BUDGET_EXHAUSTED_STAGE, researchWsService } from './services/researchWs';
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
  const tradingToken = useMemo(() => (isDarkMode
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
      }), [isDarkMode]);

  // 静态方法主题桥接：message/notification/Modal 的静态调用通过独立 render 创建弹窗 DOM，
  // 不消费 React 树内 ConfigProvider 的动态主题（dev 下会报
  // "Static function can not consume context like dynamic theme" 警告）。
  // 用官方 holderRender 把静态 holder 包进带当前主题的 ConfigProvider，主题切换后立即生效。
  useEffect(() => {
    ConfigProvider.config({
      holderRender: (node) => (
        <ConfigProvider
          theme={{
            algorithm: isDarkMode ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
            token: tradingToken,
          }}
        >
          {node}
        </ConfigProvider>
      ),
    });
  }, [isDarkMode, tradingToken]);

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
            <ResearchEventBridge />
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

// 研究事件全局桥（PRD §6.10 #3）：预算耗尽等关键事件用全站级 notification 提醒，
// 不依赖用户停留在研究详情页。事件流展示仍在详情页内轮询，二者互不替代。
function ResearchEventBridge() {
  const { notification } = AntdApp.useApp();
  // 同一会话只提醒一次；WS 断线期间的事件由详情页轮询补齐（不在此重放）
  const notifiedRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    const handler = (data: unknown) => {
      const payload = data as
        | { session_id?: number; event?: { stage?: string; msg?: string } }
        | undefined;
      if (payload?.event?.stage !== RESEARCH_BUDGET_EXHAUSTED_STAGE) return;
      const sessionId = payload.session_id;
      if (typeof sessionId !== 'number' || notifiedRef.current.has(sessionId)) return;
      notifiedRef.current.add(sessionId);
      notification.warning({
        key: `research-budget-${sessionId}`,
        message: '研究预算已耗尽，会话按完成收尾',
        description: payload.event?.msg,
        duration: 0,
      });
    };

    researchWsService.on('research.event', handler);
    if (!researchWsService.connected) {
      researchWsService.connect();
    }
    return () => {
      researchWsService.off('research.event', handler);
    };
  }, [notification]);

  return null;
}

export default App;
