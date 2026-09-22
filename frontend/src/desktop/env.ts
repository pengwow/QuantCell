// 桌面运行时：仅 Tauri 壳内由 bootstrap 填充，Web 版永远是初始值
export type BackendMode = 'local' | 'remote';

export interface DesktopRuntime {
  mode: BackendMode;
  /** sidecar/远端地址，形如 http://127.0.0.1:58964；未就绪时为 null */
  baseUrl: string | null;
}

let runtime: DesktopRuntime = { mode: 'local', baseUrl: null };

export function setDesktopRuntime(next: DesktopRuntime): void {
  runtime = next;
}

export function getDesktopRuntime(): DesktopRuntime {
  return runtime;
}

/** Tauri 2 在 window 上注入 __TAURI_INTERNALS__；普通浏览器不存在 */
export function isTauri(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/** local 模式免登录：必须同时满足「在 Tauri 内」与「local 模式」 */
export function desktopBypassAuth(): boolean {
  return isTauri() && runtime.mode === 'local';
}
