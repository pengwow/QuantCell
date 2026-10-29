import { invoke } from '@tauri-apps/api/core';
import { type UnlistenFn, listen } from '@tauri-apps/api/event';

/** Rust 侧 update::UpdateInfo（serde rename_all = camelCase） */
export interface UpdateInfo {
  currentVersion: string;
  version: string;
  notes: string | null;
}

/** 下载进度：downloaded 为累计字节，total 未知时为 null */
export interface UpdateProgress {
  downloaded: number;
  total: number | null;
}

export const getUpdateMirror = () => invoke<string | null>('update_get_mirror');

// Tauri 参数按驼峰映射到 Rust 形参 mirror_base_url；null 表示清空镜像
export const setUpdateMirror = (mirrorBaseUrl: string | null) =>
  invoke<void>('update_set_mirror', { mirrorBaseUrl });

export const checkUpdate = () => invoke<UpdateInfo | null>('update_check');
export const installUpdate = () => invoke<void>('update_install');

export const onUpdateProgress = (handler: (p: UpdateProgress) => void): Promise<UnlistenFn> =>
  listen<UpdateProgress>('update://progress', (e) => handler(e.payload));
