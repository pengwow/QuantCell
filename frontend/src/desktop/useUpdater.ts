import { useEffect } from 'react';
import { notification } from 'antd';
import i18n from '../i18n/config';
import { getDesktopRuntime, isTauri } from './env';
import { checkUpdate, installUpdate, onUpdateProgress } from './updateBridge';
import { useUpdateStore } from './updateStore';

/** 静默检查间隔：24 小时 */
export const CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
/** 上次检查时间戳（毫秒），localStorage 持久化 */
const LAST_CHECK_KEY = 'update_last_check_ms';
/** 启动后延迟检查，避开首屏引导与 sidecar 启动抢带宽 */
const STARTUP_DELAY_MS = 8000;

/** 纯函数：是否已过检查间隔（时间戳缺失/非法一律视为需要检查） */
export function shouldCheck(lastCheckMs: number, nowMs: number): boolean {
  if (!Number.isFinite(lastCheckMs) || lastCheckMs <= 0) {
    return true;
  }
  return nowMs - lastCheckMs >= CHECK_INTERVAL_MS;
}

/** 静默检查只调度一次：ConsoleLayout 与设置页都会挂载触发，模块级标记防止重复 */
let silentScheduled = false;

export function scheduleSilentCheck(): void {
  if (silentScheduled || !isTauri()) {
    return;
  }
  silentScheduled = true;
  const last = Number(localStorage.getItem(LAST_CHECK_KEY) ?? 0);
  if (!shouldCheck(last, Date.now())) {
    return;
  }
  window.setTimeout(() => {
    void runCheck({ silent: true });
  }, STARTUP_DELAY_MS);
}

/** 手动/静默检查；静默失败不打扰用户，只回落到 idle */
export async function runCheck(opts: { silent?: boolean } = {}): Promise<void> {
  const store = useUpdateStore.getState();
  if (store.status === 'checking' || store.status === 'downloading') {
    return;
  }
  store.setChecking();
  try {
    const info = await checkUpdate();
    localStorage.setItem(LAST_CHECK_KEY, String(Date.now()));
    store.setResult(info);
    if (opts.silent && info) {
      // 静默发现新版：一次性轻提示 + 侧边栏红点，不弹窗打断当前操作
      notification.info({
        message: i18n.t('update_available', { version: info.version }),
        description: i18n.t('update_notification_hint'),
      });
    }
  } catch (e) {
    if (opts.silent) {
      store.reset();
    } else {
      store.setError(e instanceof Error ? e.message : String(e));
    }
  }
}

/** 进度监听只绑定一次（模块级）：下载中切页面回来仍能拿到进度 */
let progressBound = false;

/** 查询后端运行中的策略数；后端不可达时按 0 处理（不阻断升级） */
async function fetchRunningStrategies(): Promise<number> {
  const { baseUrl } = getDesktopRuntime();
  if (!baseUrl) {
    return 0;
  }
  try {
    const res = await fetch(`${baseUrl}/health`);
    if (!res.ok) {
      return 0;
    }
    const data: { engine?: { running_strategies?: number } } = await res.json();
    return Number(data.engine?.running_strategies ?? 0);
  } catch {
    return 0;
  }
}

export interface InstallOptions {
  /** 有运行中策略时询问用户；未提供则视为直接继续 */
  confirm?: (runningStrategies: number) => Promise<boolean>;
}

/** 下载并安装；重启由 Rust 侧在安装完成后执行 */
export async function runInstall(opts: InstallOptions = {}): Promise<void> {
  const store = useUpdateStore.getState();
  if (store.status !== 'available') {
    return;
  }
  // 安装后应用会重启，运行中的策略会被中断，必须先让用户知情
  const running = await fetchRunningStrategies();
  if (running > 0 && opts.confirm && !(await opts.confirm(running))) {
    return;
  }
  if (!progressBound) {
    progressBound = true;
    void onUpdateProgress((p) => useUpdateStore.getState().setProgress(p.downloaded, p.total));
  }
  store.setDownloading();
  try {
    await installUpdate();
    // 安装成功后 Rust 侧会重启应用，这里不会继续执行
  } catch (e) {
    store.setError(e instanceof Error ? e.message : String(e));
  }
}

/** 组件挂载即参与静默调度，返回可复用的更新动作 */
export function useUpdater() {
  useEffect(() => {
    scheduleSilentCheck();
  }, []);
  return { check: runCheck, install: runInstall };
}
