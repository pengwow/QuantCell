import {
  type BackendConfig,
  getBackendConfig,
  onBackendEvent,
  startBackend,
} from './bridge';
import { setDesktopRuntime } from './env';
import { installNetworkBridge } from './network';
import { updateApiClientBaseUrl } from '../api';
import { hideSplash, showSplash, showSplashError, updateSplash } from './splash';

const HEALTH_TIMEOUTS = 180; // 秒；onefile 自解压 ~1 分钟 + 存量库升级迁移，实测冷启可达 ~110s（90s 会误报超时）

async function waitHealth(baseUrl: string, label: string): Promise<void> {
  updateSplash(`${label}，首次启动约需 1-2 分钟…`);
  for (let i = 0; i < HEALTH_TIMEOUTS; i++) {
    try {
      const res = await fetch(`${baseUrl}/health`);
      if (res.ok) return;
    } catch {
      // 端口未开/解压中
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error('等待后端就绪超时');
}

function installCrashEvents(): void {
  void onBackendEvent(() => {
    // 具体遮罩由 React 层 CrashMask 监听处理；此处仅保证订阅在引导期就建立，
    // 覆盖 React 首屏渲染前的极端崩溃窗口（事件错过则由健康轮询兜底）
  });
}

/** Tauri 环境启动引导；仅在 isTauri() 时由 main.tsx await */
export async function bootstrapDesktop(): Promise<void> {
  showSplash('正在启动 QuantCell…');
  let cfg: BackendConfig;
  try {
    cfg = await getBackendConfig();
    // Rust setup 不自动起 sidecar，local 且已停止时由前端拉起
    if (cfg.mode === 'local' && cfg.status === 'stopped') {
      cfg = await startBackend();
    }

    const baseUrl = cfg.baseUrl;
    if (!baseUrl) {
      throw new Error('未配置后端地址，请在设置中配置远程后端');
    }
    await waitHealth(
      baseUrl,
      cfg.mode === 'local' ? '正在启动本机后端' : '正在连接远程后端',
    );

    setDesktopRuntime({ mode: cfg.mode, baseUrl });
    installNetworkBridge();
    // axios 实例在模块加载期烘焙 baseURL，彼时 runtime.base 还未就绪，
    // 会固化成相对 `/api/v1`——XHR 落到 tauri:// 协议处理器上，全部页面
    // 无声失败（fetch 已被网络桥重写，唯独 axios 走 XHR 不经过它）。
    // 桌面壳就绪后必须重指 axios 到 sidecar/remote 地址。
    updateApiClientBaseUrl();
    installCrashEvents();
    // 仅成功路径移除遮罩；失败时保留错误态（见 catch）
    hideSplash();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    showSplashError(`启动失败：${msg}`, '重试', () => {
      void bootstrapDesktop();
    });
    // 抛出以阻断 React 渲染，避免在无后端状态下进入业务页
    throw e;
  }
}
