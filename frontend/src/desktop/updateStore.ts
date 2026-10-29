import { create } from 'zustand';
import type { UpdateInfo } from './updateBridge';

/** idle 无更新/未检查；available 有可用更新；error 仅手动检查与安装失败时出现 */
export type UpdateStatus = 'idle' | 'checking' | 'available' | 'downloading' | 'error';

interface UpdateState {
  status: UpdateStatus;
  info: UpdateInfo | null;
  downloaded: number;
  total: number | null;
  error: string | null;
  setChecking: () => void;
  setResult: (info: UpdateInfo | null) => void;
  setDownloading: () => void;
  setProgress: (downloaded: number, total: number | null) => void;
  setError: (message: string) => void;
  reset: () => void;
}

export const useUpdateStore = create<UpdateState>((set) => ({
  status: 'idle',
  info: null,
  downloaded: 0,
  total: null,
  error: null,
  setChecking: () => set({ status: 'checking', error: null }),
  setResult: (info) =>
    set(info ? { status: 'available', info } : { status: 'idle', info: null }),
  setDownloading: () => set({ status: 'downloading', downloaded: 0, total: null, error: null }),
  setProgress: (downloaded, total) => set({ downloaded, total }),
  setError: (message) => set({ status: 'error', error: message }),
  reset: () => set({ status: 'idle', info: null, downloaded: 0, total: null, error: null }),
}));
