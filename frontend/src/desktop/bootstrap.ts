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

const HEALTH_TIMEOUTS = 180; // 秒；onefile 自解压 + 冻结 import，冷启实测可达 ~110s（90s 会误报超时）
// 每次预热窗口只自动整页刷新一次：进 UI 时后端未就绪 → 就绪后 reload 让各页重新拉数；
// 刷新后首探已健康则清标志，允许下一次（如设置页手动重启）的预热刷新
const BOOT_RELOAD_FLAG = 'qc_boot_reloaded_once';

async function probeOnce(baseUrl: string): Promise<boolean> {
  try {
    const res = await fetch(`${baseUrl}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

/** 后台等待后端就绪；就绪且本预热窗口尚未刷新过 → 整页刷新一次。不阻塞 UI 渲染。 */
async function watchWarmup(baseUrl: string, label: string): Promise<void> {
  updateSplash(`${label}…`);
  for (let i = 1; i <= HEALTH_TIMEOUTS; i++) {
    if (await probeOnce(baseUrl)) {
      if (!sessionStorage.getItem(BOOT_RELOAD_FLAG)) {
        sessionStorage.setItem(BOOT_RELOAD_FLAG, '1');
        window.location.reload();
        return;
      }
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  console.error('[desktop] 等待后端就绪超时；各页将以离线态展示，可稍后在设置中重试');
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
    const label = cfg.mode === 'local' ? '正在启动本机后端' : '正在连接远程后端';
    // 不再阻塞等待 /health：立即进入 UI（后端未就绪时各页以离线/空态展示，
    // 与打包产物预览路径同族），就绪后由 watchWarmup 自动刷新一次拿数
    if (!(await probeOnce(baseUrl))) {
      void watchWarmup(baseUrl, label);
    } else {
      sessionStorage.removeItem(BOOT_RELOAD_FLAG);
    }

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
