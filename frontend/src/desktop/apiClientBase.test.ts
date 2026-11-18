import { beforeEach, describe, expect, it, vi } from 'vitest';

// 桌面打包实录回归(2026-11-18):axios 实例在模块加载期以彼时尚未就绪的
// runtime 烘焙 baseURL(固化成相对 /api/v1),XHR 落到 tauri:// 协议处理器,
// 全部页面无声失败——fetch 有网络桥重写,axios 走 XHR 不经过它。
// bootstrap 必须在 setDesktopRuntime 后调用 updateApiClientBaseUrl 重指。
const runtimeState = vi.hoisted(() => ({
  mode: 'local' as 'local' | 'remote',
  baseUrl: null as string | null,
}));

vi.mock('./env', () => ({
  getDesktopRuntime: () => runtimeState,
  setDesktopRuntime: (next: Partial<typeof runtimeState>) => {
    Object.assign(runtimeState, next);
  },
  isTauri: () => true,
  desktopBypassAuth: () => true,
}));

import { api, handleUnauthorized, updateApiClientBaseUrl } from '../api';
import { setDesktopRuntime } from './env';

describe('桌面 axios baseURL 绑定', () => {
  beforeEach(() => {
    runtimeState.baseUrl = null;
    api.defaults.baseURL = '/api/v1'; // 模拟模块加载期的固化结果
  });

  it('runtime 就绪后 updateApiClientBaseUrl 重指到 sidecar 地址', () => {
    setDesktopRuntime({ mode: 'local', baseUrl: 'http://127.0.0.1:59999' });
    updateApiClientBaseUrl();
    expect(api.defaults.baseURL).toBe('http://127.0.0.1:59999/api/v1');
  });

  it('remote 模式同样跟随 runtime base', () => {
    setDesktopRuntime({ mode: 'remote', baseUrl: 'http://192.168.1.8:8000' });
    updateApiClientBaseUrl();
    expect(api.defaults.baseURL).toBe('http://192.168.1.8:8000/api/v1');
  });

  it('桌面 local 下 401 不跳登录页(免登录实录:点菜单被踢回登录)', () => {
    const scheduled = vi.spyOn(globalThis, 'setTimeout');
    handleUnauthorized();
    expect(scheduled).not.toHaveBeenCalled(); // 未安排任何跳转
    scheduled.mockRestore();
  });
});
