import { ConfigProvider, App as AntdApp } from 'antd';
// locale 必须走 antd/es 深路径：antd v6 根路径 antd/locale/* 是 CJS 转发文件，
// vite 依赖预打包做 CJS interop 时会产生双层 default 包装（实际传入 { default: {...} }），
// 导致 ConfigProvider 下所有内置文案（分页"条/页"、日期选择器等）回退英文
import zhCN from 'antd/es/locale/zh_CN';
import enUS from 'antd/es/locale/en_US';
import { useTranslation } from 'react-i18next';
import type { MessageInstance } from 'antd/es/message/interface';
import { BrowserRouter, useNavigate } from 'react-router-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { DynamicRouter } from './router/DynamicRouter';
import CrashMask from './desktop/CrashMask';
import { isTauri } from './desktop/env';
import { useConfigStore } from './store';
import { useNotificationStore } from './store/notificationStore';
import { useWorkerStore } from './store/workerStore';
import { wsService } from './services/websocketService';
import { RESEARCH_BUDGET_EXHAUSTED_STAGE, researchWsService } from './services/researchWs';
import type { InboxNotificationItem } from './api';
import { taskNotificationRoute } from './utils/taskRoutes';
import { PluginProvider } from './plugins';
import { applyThemeVars, paletteToTradingToken, themeAlgorithm } from './theme';
import './i18n/config';
import './global.css';
import './index.css';

/**
 * ConfigProvider 主题基座（组件外定义，单点维护）：
 * - algorithm 仍随亮暗切换（唯一动态部分）；
 * - token 由 palette 派生（品牌色唯一真相源 = src/theme/builtin.ts），再叠加 design-spec §3/§10.2
 *   的紧凑排印与几何（13px 正文 / 32px 控件 / 8-10 圆角 / 1.6 行高）；
 * - Layout 底色统一透明，页面底色交给 --qc-canvas / background 控制。
 * 树内 ConfigProvider 与 holderRender（静态 message/Modal）共用本函数，避免两处漂移。
 */
const baseTheme = (mode: 'light' | 'dark') => ({
  algorithm: themeAlgorithm(mode),
  token: {
    ...paletteToTradingToken(mode),
    fontSize: 13,
    controlHeight: 32,
    borderRadius: 8,
    borderRadiusLG: 10,
    lineHeight: 1.6,
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei", sans-serif',
  },
  components: {
    Layout: {
      bodyBg: 'transparent',
      headerBg: 'transparent',
      siderBg: 'transparent',
    },
  },
});

function App() {
  const { i18n } = useTranslation();
  const [isDarkMode, setIsDarkMode] = useState(() => document.documentElement.classList.contains('dark'));
  // antd 组件内置文案（分页"12 条/页"、日期选择器等）跟随应用语言，缺失时 ConfigProvider 默认英文
  const antdLocale = i18n.language?.startsWith('zh') ? zhCN : enUS;
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
    // 监听主题变化：.dark class 是模式开关的唯一真相（index.html 首帧脚本 / useBrowserTheme / 设置页都改它），
    // 任一路径触发时同步重写 CSS 变量 + 通知 React 侧 isDarkMode
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          const isDark = document.documentElement.classList.contains('dark');
          applyThemeVars(isDark ? 'dark' : 'light');
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

  // ponytail: 交易语义色一切以 src/theme/palettes.ts 为准（品牌色唯一真相源）。
  // 这里只做 palette → antd token 的渠道映射；各组件（QUANT_COLORS、ECharts、MetricCard）
  // 通过 theme.useToken() / useQuantColors() 取色，禁止在子组件里硬编码颜色值。
  const appTheme = useMemo(() => baseTheme(isDarkMode ? 'dark' : 'light'), [isDarkMode]);

  // 静态方法主题桥接：message/notification/Modal 的静态调用通过独立 render 创建弹窗 DOM，
  // 不消费 React 树内 ConfigProvider 的动态主题（dev 下会报
  // "Static function can not consume context like dynamic theme" 警告）。
  // 用官方 holderRender 把静态 holder 包进带当前主题的 ConfigProvider，主题切换后立即生效。
  useEffect(() => {
    ConfigProvider.config({
      holderRender: (node) => (
        <ConfigProvider locale={antdLocale} theme={appTheme}>
          {node}
        </ConfigProvider>
      ),
    });
  }, [appTheme, antdLocale]);

  return (
    <ConfigProvider locale={antdLocale} theme={appTheme}>
      <AntdApp>
        <BrowserRouter>
          <PluginProvider>
            <AppInjector setMessageApi={setMessageApi} />
            <ResearchEventBridge />
            <NotificationBridge />
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
  const { t } = useTranslation();
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
        message: t('research_budget_exhausted_notice'),
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
  }, [notification, t]);

  return null;
}

/**
 * 站内通知实时桥：WS 推送 type=notification 的消息 → 未读数 +1 + 全站浮层提醒。
 * 未读数的权威值以后端为准（收件箱加载时 loadList 拉取），这里只做增量叠加。
 */
function NotificationBridge() {
  const { notification } = AntdApp.useApp();
  const navigate = useNavigate();
  const bumpUnread = useNotificationStore((s) => s.bumpUnread);

  useEffect(() => {
    const handler = (data: unknown) => {
      const payload = data as
        | {
            title?: string;
            content?: string;
            level?: string;
            source?: string;
            created_at?: string;
            metadata?: Record<string, unknown>;
          }
        | undefined;
      if (!payload?.title) return;

      const item: InboxNotificationItem = {
        // ponytail: ws 推送无 id，用负时间戳做临时 key 避免与真实 id 冲突；刷新列表时以服务端为准
        id: -Date.now(),
        title: payload.title,
        content: payload.content ?? '',
        level: payload.level ?? 'info',
        source: payload.source ?? 'system',
        created_at: payload.created_at ?? null,
        read: false,
        processed: false,
        metadata: payload.metadata,
      };
      bumpUnread(item);

      // 任务类通知点击浮层直达详情页（兜底逻辑见 taskRoutes.ts 头注释）
      const route = taskNotificationRoute(payload.source ?? '', {
        id: typeof payload.metadata?.task_id === 'string' ? payload.metadata.task_id : null,
        detail: payload.metadata,
      });

      // 浮层按 level 分级：info/success 自动关，error/critical 常驻需手动关
      const byLevel: Record<string, (cfg: { message: string; description?: string; duration?: number; onClick?: () => void }) => void> = {
        info: notification.info,
        success: notification.success,
        warning: notification.warning,
        error: notification.error,
        critical: notification.error,
      };
      const show = byLevel[payload.level ?? 'info'] ?? notification.info;
      show({
        message: payload.title,
        description: payload.content || undefined,
        duration: payload.level === 'error' || payload.level === 'critical' ? 0 : 4.5,
        ...(route ? { onClick: () => navigate(route) } : {}),
      });
    };

    // 消息结构 {type:'notification', data:{...}}，wsService 对未知 type 走 fallback 分发
    wsService.on('notification', handler);
    return () => wsService.off('notification', handler);
  }, [notification, bumpUnread, navigate]);

  return null;
}

export default App;
