import { afterEach, describe, expect, it } from 'vitest';
import {
  desktopBypassAuth,
  getDesktopRuntime,
  isTauri,
  setDesktopRuntime,
} from './env';

describe('isTauri', () => {
  afterEach(() => {
    delete (globalThis as { window?: unknown }).window;
  });

  it('无 window 时返回 false', () => {
    delete (globalThis as { window?: unknown }).window;
    expect(isTauri()).toBe(false);
  });

  it('普通浏览器 window 无 __TAURI_INTERNALS__ 时返回 false', () => {
    (globalThis as { window?: unknown }).window = {};
    expect(isTauri()).toBe(false);
  });

  it('window 含 __TAURI_INTERNALS__ 时返回 true', () => {
    (globalThis as { window?: unknown }).window = { __TAURI_INTERNALS__: {} };
    expect(isTauri()).toBe(true);
  });
});

describe('desktopBypassAuth', () => {
  it('Tauri local 模式放行', () => {
    (globalThis as { window?: unknown }).window = { __TAURI_INTERNALS__: {} };
    setDesktopRuntime({ mode: 'local', baseUrl: 'http://127.0.0.1:58964' });
    expect(desktopBypassAuth()).toBe(true);
  });

  it('Tauri remote 模式不放行', () => {
    (globalThis as { window?: unknown }).window = { __TAURI_INTERNALS__: {} };
    setDesktopRuntime({ mode: 'remote', baseUrl: 'https://api.example.com' });
    expect(desktopBypassAuth()).toBe(false);
  });

  it('非 Tauri 环境即使 runtime 为 local 也不放行', () => {
    delete (globalThis as { window?: unknown }).window;
    setDesktopRuntime({ mode: 'local', baseUrl: null });
    expect(desktopBypassAuth()).toBe(false);
    expect(getDesktopRuntime().mode).toBe('local');
  });
});
