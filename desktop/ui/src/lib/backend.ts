import { type UnlistenFn, listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";

export type BackendMode = "local" | "remote";
export type BackendStatus = "stopped" | "starting" | "crashed";

export interface BackendConfig {
  mode: BackendMode;
  baseUrl: string | null;
  port: number | null;
  remoteUrl: string | null;
  status: BackendStatus;
}

export interface BackendEvent {
  type: "terminated" | "force-killed";
  code?: number | null;
  port?: number | null;
  status?: BackendStatus;
}

export const getBackendConfig = () => invoke<BackendConfig>("get_backend_config");
export const startBackend = () => invoke<BackendConfig>("backend_start");
export const stopBackend = () => invoke<void>("backend_stop");
export const restartBackend = () => invoke<BackendConfig>("backend_restart");

// Tauri 参数按驼峰自动映射到 Rust 形参 remote_url
export const setBackendMode = (mode: BackendMode, remoteUrl?: string) =>
  invoke<BackendConfig>("set_backend_mode", {
    mode,
    remoteUrl: remoteUrl ?? null,
  });

export const onBackendEvent = (
  handler: (event: BackendEvent) => void,
): Promise<UnlistenFn> =>
  listen<BackendEvent>("backend:event", (e) => handler(e.payload));
