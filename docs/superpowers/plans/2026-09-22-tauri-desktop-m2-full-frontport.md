# Tauri 桌面客户端 M2（整套 Web 前端移植）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让现有 `frontend/` 全部 9 个页面 + 插件系统在 Tauri 壳内运行，local 免登录，Web 版行为不变。

**Architecture:** Tauri 壳（M1）改为直接加载 `frontend/` 工程（frontendDist/devUrl 切换），前端新增仅 Tauri 环境激活的薄适配层 `src/desktop/`（启动引导、fetch/WebSocket 全局重写、免登录判定、Splash/崩溃遮罩、模式设置卡片）；后端 sidecar 注入 `QUANTCELL_DESKTOP_LOCAL=1` 走现有 auth 豁免通道。

**Tech Stack:** React 18 + antd 6 + Vite（frontend 现有）、Tauri 2 invoke/event、vitest（新增 devDep）、pytest、Rust 不变。

设计文档：`docs/superpowers/specs/2026-09-22-tauri-desktop-m2-full-frontport-design.md`

---

## 文件结构总览

新建（均在 `frontend/src/desktop/`）：

| 文件 | 职责 |
| --- | --- |
| `env.ts` | Tauri 环境探测、桌面运行时（mode/baseUrl）单例、免登录判定 |
| `bridge.ts` | Tauri invoke/event 封装与类型（从 M1 `desktop/ui/src/lib/backend.ts` 迁移） |
| `network.ts` | URL 重写纯函数 + fetch/WebSocket 全局安装器（幂等） |
| `splash.ts` | 原生 DOM 冷启动遮罩（不依赖 React bundle） |
| `bootstrap.ts` | 启动引导：拿配置→启 sidecar→等健康→注入网络/鉴权→崩溃守护 |
| `CrashMask.tsx` | 崩溃全屏遮罩（React 组件，重启后 reload） |
| `DesktopBackendSettings.tsx` | 设置页「桌面后端」卡片 |
| `env.test.ts` / `network.test.ts` | vitest 单测 |

修改：

- `backend/desktop_entry.py`（注入 `QUANTCELL_DESKTOP_LOCAL`、CORS 加 5173）
- `backend/utils/auth.py`（豁免分支，生产 fail-closed）
- `backend/tests/unit/test_desktop_entry.py` + 新建 `test_desktop_auth.py`
- `frontend/src/main.tsx`（render 前条件 bootstrap）
- `frontend/src/components/AuthGuard.tsx`（local 直通）
- `frontend/src/utils/portConfig.ts`（Tauri 环境读桌面 base）
- `frontend/src/pages/setting/Setting.tsx` + `frontend/src/router/DynamicRouter.tsx`（桌面设置项）
- `frontend/vite.config.ts`（strictPort）、`frontend/package.json`（@tauri-apps/api、vitest）
- `desktop/src-tauri/tauri.conf.json`（指向 frontend）
- `desktop/README.md`

废弃：`desktop/ui/`（mv 到临时隔离目录，不 rm）。

---

## Task 1: 后端 sidecar local 免登录（TDD）

**Files:**
- Modify: `backend/desktop_entry.py`
- Modify: `backend/utils/auth.py:50-61`
- Test: `backend/tests/unit/test_desktop_entry.py`
- Test: `backend/tests/unit/test_desktop_auth.py`（新建）

- [ ] **Step 1: 先写失败测试**

在 `backend/tests/unit/test_desktop_entry.py` 末尾追加：

```python
def test_build_runtime_env_enables_desktop_local_bypass_and_dev_cors():
    from desktop_entry import build_runtime_env

    env = build_runtime_env("/tmp/whatever")

    # local 模式免登录开关，供 utils.auth._auth_disabled 读取
    assert env["QUANTCELL_DESKTOP_LOCAL"] == "1"
    # M2 dev 时前端 Vite 跑在 5173，需放行（M1 的 1420 保留）
    assert "http://localhost:5173" in env["CORS_ORIGINS"]
    assert "http://127.0.0.1:5173" in env["CORS_ORIGINS"]
```

新建 `backend/tests/unit/test_desktop_auth.py`：

```python
"""QUANTCELL_DESKTOP_LOCAL 鉴权豁免三态测试。"""


def test_desktop_local_flag_disables_auth(monkeypatch):
    import utils.auth as auth

    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.setattr(auth, "IS_DEBUG_MODE", False)
    monkeypatch.setenv("QUANTCELL_DESKTOP_LOCAL", "1")

    assert auth._auth_disabled() is True


def test_without_desktop_flag_auth_stays_enabled(monkeypatch):
    import utils.auth as auth

    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)
    monkeypatch.delenv("QUANTCELL_DESKTOP_LOCAL", raising=False)
    monkeypatch.setattr(auth, "IS_DEBUG_MODE", False)

    assert auth._auth_disabled() is False


def test_production_env_overrides_desktop_local(monkeypatch):
    import utils.auth as auth

    # 生产环境即使误带开关也必须 fail-closed，不允许豁免
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("QUANTCELL_DESKTOP_LOCAL", "1")

    assert auth._auth_disabled() is False
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && .venv/bin/python -m pytest tests/unit/test_desktop_entry.py tests/unit/test_desktop_auth.py -v
```

Expected: `test_build_runtime_env_enables_desktop_local_bypass_and_dev_cors` 与 `test_desktop_local_flag_disables_auth` FAIL（KeyError / assert False）。

- [ ] **Step 3: 修改 desktop_entry.py**

`_DEFAULT_CORS_ORIGINS` 改为（加 5173 两个 origin）：

```python
# macOS/Linux WebView origin 为 tauri://localhost，Windows 为 http://tauri.localhost；
# 1420 是 M1 桌面 UI 的 Vite 端口，5173 是 M2 复用 frontend 的 Vite 端口
_DEFAULT_CORS_ORIGINS = (
    "tauri://localhost,http://tauri.localhost,"
    "http://localhost:1420,http://127.0.0.1:1420,"
    "http://localhost:5173,http://127.0.0.1:5173"
)
```

`build_runtime_env` 返回的 dict 中加一项（放在 CORS_ORIGINS 后）：

```python
        "CORS_ORIGINS": _DEFAULT_CORS_ORIGINS,
        # 桌面 local 模式免登录标记：仅本 sidecar 进程内生效，
        # utils.auth 读取；APP_ENV=production 时该豁免被强制忽略
        "QUANTCELL_DESKTOP_LOCAL": "1",
```

- [ ] **Step 4: 修改 auth.py 的 _auth_disabled**

在 `IS_DEBUG_MODE = _is_debug_mode()` 之后新增常量与判定函数：

```python
# 桌面 sidecar local 模式的免登录开关（desktop_entry 注入）
_DESKTOP_LOCAL_TRUE = {"1", "true", "yes"}


def _is_desktop_local() -> bool:
    return os.environ.get("QUANTCELL_DESKTOP_LOCAL", "").lower() in _DESKTOP_LOCAL_TRUE
```

把 `_auth_disabled()` 改为：

```python
def _auth_disabled() -> bool:
    """鉴权豁免判定（生产环境强制关闭）。

    两类豁免：debug 模式，或桌面 sidecar local 模式（QUANTCELL_DESKTOP_LOCAL）。
    env 每次请求实时读取；APP_ENV=production/prod 一律 fail-closed，
    即使测试 patch IS_DEBUG_MODE 或误带桌面开关也无法绕过。
    """
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env in ("production", "prod"):
        return False
    if _is_desktop_local():
        return True
    return IS_DEBUG_MODE or _is_debug_mode()
```

- [ ] **Step 5: 运行确认通过**

```bash
cd backend && .venv/bin/python -m pytest tests/unit/test_desktop_entry.py tests/unit/test_desktop_auth.py -v
```

Expected: 全部 PASS（desktop_entry 原有 1 个 + 新增 1 个；desktop_auth 3 个）。

- [ ] **Step 6: 提交**

```bash
git add backend/desktop_entry.py backend/utils/auth.py backend/tests/unit/test_desktop_entry.py backend/tests/unit/test_desktop_auth.py
git commit -m "feat(desktop): local sidecar auth bypass via QUANTCELL_DESKTOP_LOCAL with production fail-closed"
```

---

## Task 2: vitest 基础设施 + env.ts + bridge.ts

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/desktop/env.ts`
- Create: `frontend/src/desktop/env.test.ts`
- Create: `frontend/src/desktop/bridge.ts`

- [ ] **Step 1: 安装依赖**

```bash
cd frontend && bun add @tauri-apps/api@^2 && bun add -d vitest
```

在 `frontend/package.json` 的 `scripts` 中加：

```json
    "test": "vitest run",
```

- [ ] **Step 2: 创建 vitest.config.ts**

```ts
import { defineConfig } from 'vitest/config';
import path from 'path';

// 桌面适配层纯函数测试用 node 环境（不引 jsdom）；
// 需要 DOM 的判定一律抽成可注入参数的纯函数
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
```

- [ ] **Step 3: 先写 env.test.ts（失败测试）**

```ts
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
```

- [ ] **Step 4: 运行确认失败**

```bash
cd frontend && bun run test
```

Expected: FAIL（Cannot find module './env'）。

- [ ] **Step 5: 实现 env.ts**

```ts
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
```

- [ ] **Step 6: 创建 bridge.ts（从 M1 desktop/ui/src/lib/backend.ts 原样迁移）**

```ts
import { type UnlistenFn, listen } from '@tauri-apps/api/event';
import { invoke } from '@tauri-apps/api/core';
import type { BackendMode } from './env';

export type BackendStatus = 'stopped' | 'starting' | 'crashed';

export interface BackendConfig {
  mode: BackendMode;
  baseUrl: string | null;
  port: number | null;
  remoteUrl: string | null;
  status: BackendStatus;
}

export interface BackendEvent {
  type: 'terminated' | 'force-killed';
  code?: number | null;
  port?: number | null;
  status?: BackendStatus;
}

export const getBackendConfig = () => invoke<BackendConfig>('get_backend_config');
export const startBackend = () => invoke<BackendConfig>('backend_start');
export const stopBackend = () => invoke<void>('backend_stop');
export const restartBackend = () => invoke<BackendConfig>('backend_restart');

// Tauri 参数按驼峰自动映射到 Rust 形参 remote_url
export const setBackendMode = (mode: BackendMode, remoteUrl?: string) =>
  invoke<BackendConfig>('set_backend_mode', {
    mode,
    remoteUrl: remoteUrl ?? null,
  });

export const onBackendEvent = (handler: (event: BackendEvent) => void): Promise<UnlistenFn> =>
  listen<BackendEvent>('backend:event', (e) => handler(e.payload));
```

- [ ] **Step 7: 运行确认通过并提交**

```bash
cd frontend && bun run test
```

Expected: 5 个用例 PASS。

```bash
git add frontend/package.json frontend/bun.lock frontend/vitest.config.ts frontend/src/desktop/
git commit -m "feat(desktop): add tauri env/bridge layer with vitest setup"
```

---

## Task 3: network.ts 全局 URL 重写（核心，TDD）

**Files:**
- Create: `frontend/src/desktop/network.ts`
- Test: `frontend/src/desktop/network.test.ts`

背景：Tauri 内页面 origin 为 `tauri://localhost`（Win 为 `http://tauri.localhost`，host 无 sidecar 端口）。16 处相对路径 `fetch('/api/...')` 会打到壳自身；3 处手工拼的 `ws://localhost/api/...` 缺端口。

- [ ] **Step 1: 先写 network.test.ts（失败测试）**

```ts
import { describe, expect, it } from 'vitest';
import { rewriteHttpUrl, rewriteWsUrl } from './network';

// local sidecar；pageHost 模拟 WKWebView 的 tauri://localhost（host=localhost，无端口）
const LOCAL = { baseUrl: 'http://127.0.0.1:58964', pageHost: 'localhost' };

describe('rewriteHttpUrl', () => {
  it('相对 /api 路径前置后端 base', () => {
    expect(rewriteHttpUrl({ url: '/api/v1/auth/logout', ...LOCAL })).toBe(
      'http://127.0.0.1:58964/api/v1/auth/logout',
    );
  });

  it('误指向页面 host 的绝对 /api URL 替换 origin 并保留 query', () => {
    const out = rewriteHttpUrl({
      url: 'http://localhost/api/v1/x?a=1#frag',
      ...LOCAL,
    });
    expect(out).toBe('http://127.0.0.1:58964/api/v1/x?a=1#frag');
  });

  it('第三方绝对 URL 原样透传', () => {
    const url = 'https://api.github.com/repos';
    expect(rewriteHttpUrl({ url, ...LOCAL })).toBe(url);
  });

  it('已指向后端的 URL 原样透传', () => {
    const url = 'http://127.0.0.1:58964/health';
    expect(rewriteHttpUrl({ url, ...LOCAL })).toBe(url);
  });

  it('baseUrl 为 null 时一律透传', () => {
    expect(rewriteHttpUrl({ url: '/api/x', baseUrl: null, pageHost: 'localhost' })).toBe(
      '/api/x',
    );
  });

  it('非 http(s) 且非相对 API 路径原样透传', () => {
    expect(rewriteHttpUrl({ url: 'data:text/plain,hi', ...LOCAL })).toBe('data:text/plain,hi');
  });
});

describe('rewriteWsUrl', () => {
  it('相对 /ws 路径转后端 ws 地址', () => {
    expect(rewriteWsUrl({ url: '/ws/worker', ...LOCAL })).toBe(
      'ws://127.0.0.1:58964/ws/worker',
    );
  });

  it('手工拼的 ws://localhost/api 流地址替换 origin 为带端口的后端', () => {
    expect(
      rewriteWsUrl({
        url: 'ws://localhost/api/v1/backtest/progress/123/stream',
        ...LOCAL,
      }),
    ).toBe('ws://127.0.0.1:58964/api/v1/backtest/progress/123/stream');
  });

  it('remote https 后端派生 wss', () => {
    expect(
      rewriteWsUrl({
        url: 'wss://tauri.localhost/ws/worker',
        baseUrl: 'https://api.example.com',
        pageHost: 'tauri.localhost',
      }),
    ).toBe('wss://api.example.com/ws/worker');
  });

  it('第三方 ws 透传', () => {
    const url = 'wss://stream.binance.com:9443/ws';
    expect(rewriteWsUrl({ url, ...LOCAL })).toBe(url);
  });
});
```

- [ ] **Step 2: 运行确认失败**

```bash
cd frontend && bun run test
```

Expected: FAIL（Cannot find module './network'）。

- [ ] **Step 3: 实现 network.ts**

```ts
import { getDesktopRuntime } from './env';

// 后端 API/WS 的相对路径前缀；WS 流地址实际也挂在 /api/v1 下（如回测进度流）
const API_PREFIXES = ['/api', '/ws'];

export interface RewriteInput {
  url: string;
  /** 后端 base（http/https），null 表示未就绪，一律透传 */
  baseUrl: string | null;
  /** 页面自身 location.host，用于识别误指向壳自身的绝对 URL */
  pageHost: string;
}

function startsWithBackendPath(pathname: string): boolean {
  // startsWith 已同时覆盖 '/api'、'/api/...'、'/wsx'（后端无此前缀外的其他路由，
  // 命中面仅限这两个保留前缀）
  return API_PREFIXES.some((p) => pathname.startsWith(p));
}

/** HTTP/HTTPS：相对 /api|/ws 前置 base；host=页面自身的绝对后端 URL 换 origin */
export function rewriteHttpUrl({ url, baseUrl, pageHost }: RewriteInput): string {
  if (!baseUrl) return url;
  if (startsWithBackendPath(url)) return `${baseUrl}${url}`;
  try {
    const u = new URL(url);
    if ((u.protocol === 'http:' || u.protocol === 'https:') && u.host === pageHost
        && startsWithBackendPath(u.pathname)) {
      return `${baseUrl}${u.pathname}${u.search}${u.hash}`;
    }
  } catch {
    // 非绝对 URL（如 data:、blob: 或畸形 URL），不在重写范围，透传
  }
  return url;
}

function toWsBase(baseUrl: string): string {
  return baseUrl.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
}

/** WebSocket：规则同 HTTP，协议按后端 base 同步取 ws/wss */
export function rewriteWsUrl({ url, baseUrl, pageHost }: RewriteInput): string {
  if (!baseUrl) return url;
  const wsBase = toWsBase(baseUrl);
  if (startsWithBackendPath(url)) return `${wsBase}${url}`;
  try {
    const u = new URL(url);
    if ((u.protocol === 'ws:' || u.protocol === 'wss:') && u.host === pageHost
        && startsWithBackendPath(u.pathname)) {
      return `${wsBase}${u.pathname}${u.search}`;
    }
  } catch {
    // 透传非绝对 URL
  }
  return url;
}

const PATCH_FLAG = '__QC_NET_PATCHED__';

/**
 * 在 Tauri 环境安装全局网络重写（幂等）。
 * ponytail: 猴子补丁是有意为之——16 处相对 fetch + 3 处手工拼 WS 分散在各页面，
 * 单点改写比逐个调用点修改侵入小且不会漏新代码；上限：升级 Vite/Tauri 大版本
 * 或后端 API 前缀调整时需回归 network.test.ts。
 */
export function installNetworkBridge(): void {
  const g = globalThis as unknown as Record<string, unknown>;
  if (g[PATCH_FLAG]) return;

  const origFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const raw =
      typeof input === 'string' ? input
      : input instanceof URL ? input.href
      : input.url; // Request
    const { baseUrl } = getDesktopRuntime();
    const rewritten = rewriteHttpUrl({ url: raw, baseUrl, pageHost: window.location.host });
    if (rewritten === raw) return origFetch(input, init);
    if (typeof input === 'string' || input instanceof URL) {
      return origFetch(rewritten, init);
    }
    // Request：以原 Request 为模板复制（继承 method/headers/body），仅换 URL
    return origFetch(new Request(rewritten, input), init);
  };

  const OrigWebSocket = window.WebSocket;
  class PatchedWebSocket extends OrigWebSocket {
    constructor(url: string | URL, protocols?: string | string[]) {
      const raw = url instanceof URL ? url.href : url;
      const { baseUrl } = getDesktopRuntime();
      const rewritten = rewriteWsUrl({ url: raw, baseUrl, pageHost: window.location.host });
      super(rewritten, protocols);
    }
  }
  window.WebSocket = PatchedWebSocket as typeof WebSocket;

  g[PATCH_FLAG] = true;
}
```

- [ ] **Step 4: 运行确认通过并提交**

```bash
cd frontend && bun run test
```

Expected: 全部 PASS（env 5 + network 10）。

```bash
git add frontend/src/desktop/network.ts frontend/src/desktop/network.test.ts
git commit -m "feat(desktop): rewrite relative/misdirected fetch and websocket urls to sidecar"
```

---

## Task 4: portConfig 扩展 + AuthGuard local 直通

**Files:**
- Modify: `frontend/src/utils/portConfig.ts:101-125`
- Modify: `frontend/src/components/AuthGuard.tsx`

- [ ] **Step 1: 修改 getApiBaseUrl 与 getWebSocketUrl**

在 `frontend/src/utils/portConfig.ts` 顶部 import：

```ts
import { getDesktopRuntime, isTauri } from '@/desktop/env';
```

`getApiBaseUrl` 函数开头（`const config = ...` 之前）插入：

```ts
  // 桌面壳：base 由 Tauri 主进程分配的动态端口/用户填的 remote 地址决定，
  // 优先于 Web 版的端口探测逻辑
  if (isTauri()) {
    const desktopBase = getDesktopRuntime().baseUrl;
    if (desktopBase) return desktopBase;
  }
```

`getWebSocketUrl` 在 `const config = ...` 之后、现有 host/port 推导之前插入：

```ts
  if (isTauri()) {
    const desktopBase = getDesktopRuntime().baseUrl;
    if (desktopBase) {
      const wsBase = desktopBase.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
      return `${wsBase}${path}`;
    }
  }
```

- [ ] **Step 2: 修改 AuthGuard.tsx**

整个文件替换为：

```tsx
import { Navigate } from 'react-router-dom';
import { desktopBypassAuth, isTauri } from '@/desktop/env';

const isAuthenticated = (): boolean => {
  // 桌面 local 模式：sidecar 由本应用自启并绑定 127.0.0.1，后端已豁免鉴权
  if (isTauri() && desktopBypassAuth()) return true;
  const token = localStorage.getItem('access_token');
  return !!token && token !== 'null' && token !== 'undefined';
};

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  if (!isAuthenticated()) {
    sessionStorage.setItem('redirect_after_login', window.location.pathname);
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
```

（`isTauri()` 已包含在 `desktopBypassAuth()` 内，保留显式调用仅为可读性，二者短路一致。）

- [ ] **Step 3: 构建门禁**

```bash
cd frontend && bun run build
```

Expected: 构建成功，无 TS 错误。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/utils/portConfig.ts frontend/src/components/AuthGuard.tsx
git commit -m "feat(desktop): route axios/ws baseurl through desktop runtime and bypass auth in local mode"
```

---

## Task 5: Splash + CrashMask + bootstrap + main.tsx 接入

**Files:**
- Create: `frontend/src/desktop/splash.ts`
- Create: `frontend/src/desktop/CrashMask.tsx`
- Create: `frontend/src/desktop/bootstrap.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: 创建 splash.ts（原生 DOM，不依赖 React bundle）**

```ts
// 冷启动遮罩：sidecar onefile 自解压约 1 分钟，需在 React 业务 bundle
// 渲染前给用户反馈。直接操作 DOM，避免被懒加载/异常波及。

const SPLASH_ID = '__qc_desktop_splash__';

const STYLE = `
#${SPLASH_ID} {
  position: fixed; inset: 0; z-index: 99999;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 18px; background: #0b1220; color: #e5e7eb;
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
#${SPLASH_ID} .qc-spin {
  width: 36px; height: 36px; border: 3px solid rgba(255,255,255,.18);
  border-top-color: #3b82f6; border-radius: 50%; animation: qc-rot .9s linear infinite;
}
#${SPLASH_ID} .qc-title { font-size: 20px; font-weight: 600; letter-spacing: .04em; }
#${SPLASH_ID} .qc-msg { font-size: 13px; color: #94a3b8; max-width: 420px; text-align: center; line-height: 1.6; }
#${SPLASH_ID} button {
  margin-top: 8px; padding: 6px 18px; border-radius: 8px; border: none;
  background: #2563eb; color: #fff; font-size: 13px; cursor: pointer;
}
@keyframes qc-rot { to { transform: rotate(360deg); } }
`;

export function showSplash(message: string): void {
  if (!document.getElementById(SPLASH_ID)) {
    const style = document.createElement('style');
    style.textContent = STYLE;
    document.head.appendChild(style);
    const el = document.createElement('div');
    el.id = SPLASH_ID;
    document.body.appendChild(el);
  }
  updateSplash(message);
}

export function updateSplash(message: string, withSpinner = true): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.innerHTML =
    (withSpinner ? '<div class="qc-spin"></div>' : '') +
    '<div class="qc-title">QuantCell</div>' +
    `<div class="qc-msg">${message}</div>`;
}

export function showSplashError(message: string, actionLabel: string, onAction: () => void): void {
  const el = document.getElementById(SPLASH_ID);
  if (!el) return;
  el.innerHTML =
    '<div class="qc-title">QuantCell</div>' +
    `<div class="qc-msg">${message}</div>`;
  const btn = document.createElement('button');
  btn.textContent = actionLabel;
  btn.onclick = onAction;
  el.appendChild(btn);
}

export function hideSplash(): void {
  document.getElementById(SPLASH_ID)?.remove();
}
```

- [ ] **Step 2: 创建 CrashMask.tsx**

```tsx
import { useEffect, useState } from 'react';
import { onBackendEvent, restartBackend, type BackendEvent } from './bridge';
import { getDesktopRuntime } from './env';
import { updateSplash, showSplash } from './splash';

/**
 * 全局崩溃守护：local 模式下 sidecar 非正常退出时显示遮罩并允许重启。
 * 重启成功后整页 reload——业务页面持有多条 WS/SSE 连接，整页重载比逐个
 * 重连更简单可靠，且会重新走一遍 bootstrap 拿到新端口。
 */
export default function CrashMask() {
  const [crashed, setCrashed] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void onBackendEvent((event: BackendEvent) => {
      if (event.status === 'crashed' && getDesktopRuntime().mode === 'local') {
        setCrashed(true);
      }
    }).then((fn) => {
      unlisten = fn;
    });
    return () => unlisten?.();
  }, []);

  if (!crashed) return null;

  const handleRestart = async () => {
    setBusy(true);
    showSplash('正在重启本机后端…');
    try {
      const cfg = await restartBackend();
      const base = cfg.baseUrl;
      if (base) {
        // 等新实例健康（冷启约 1 分钟）
        for (let i = 0; i < 90; i++) {
          try {
            const res = await fetch(`${base}/health`);
            if (res.ok) {
              window.location.reload();
              return;
            }
          } catch {
            // 尚未就绪
          }
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
      throw new Error('重启超时');
    } catch (e) {
      updateSplash(`后端重启失败：${e instanceof Error ? e.message : String(e)}`, false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 99998,
        background: 'rgba(11,18,32,.92)',
        color: '#fee2e2',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 16,
        fontFamily: '-apple-system, "PingFang SC", sans-serif',
      }}
    >
      <div style={{ fontSize: 18, fontWeight: 600 }}>本机后端已退出（非正常停止）</div>
      <button
        type="button"
        disabled={busy}
        onClick={handleRestart}
        style={{
          padding: '8px 22px',
          borderRadius: 8,
          border: 'none',
          background: busy ? '#64748b' : '#dc2626',
          color: '#fff',
          fontSize: 14,
          cursor: busy ? 'default' : 'pointer',
        }}
      >
        {busy ? '重启中…' : '重启后端'}
      </button>
    </div>
  );
}
```

- [ ] **Step 3: 创建 bootstrap.ts**

```ts
import {
  type BackendConfig,
  getBackendConfig,
  onBackendEvent,
  startBackend,
} from './bridge';
import { setDesktopRuntime } from './env';
import { installNetworkBridge } from './network';
import { hideSplash, showSplash, showSplashError, updateSplash } from './splash';

const HEALTH_TIMEOUTS = 90; // 秒；onefile 冷启自解压实测约 1 分钟

async function waitHealth(baseUrl: string, label: string): Promise<void> {
  updateSplash(`${label}，首次启动约需 1 分钟…`);
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
```

- [ ] **Step 4: 修改 main.tsx**

整个文件替换为：

```tsx
import React from 'react'
import * as ReactDOMAll from 'react-dom'
import * as ReactDOMClient from 'react-dom/client'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import { isTauri } from './desktop/env'
import { bootstrapDesktop } from './desktop/bootstrap'

// 暴露 React/ReactDOM 全局变量，供插件前端 bundle 动态加载时使用
const win = window as unknown as Record<string, unknown>
win.React = React
win.ReactJSX = { jsx, jsxs, Fragment }
win.ReactDOM = { ...ReactDOMAll, ...ReactDOMClient }

async function main() {
  // 桌面壳：先完成 sidecar 引导与网络注入，再渲染业务 bundle；Web 版直接渲染
  if (isTauri()) {
    await bootstrapDesktop()
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void main()
```

- [ ] **Step 5: 把 CrashMask 挂到 App 顶层**

在 `frontend/src/App.tsx` 中，`import { DynamicRouter } from './router/DynamicRouter';` 下方加：

```tsx
import CrashMask from './desktop/CrashMask';
import { isTauri } from './desktop/env';
```

在该组件返回的 JSX 最外层（与现有最外层 Fragment/容器同级，定位在 `DynamicRouter` 渲染处旁）插入：

```tsx
{isTauri() && <CrashMask />}
```

若 App return 的是单个元素（如 `<BrowserRouter>`），将 `CrashMask` 放在其内部紧邻 `DynamicRouter` 之后，保证它在 Router 之外不影响路由。实现时读取实际 JSX 结构放置，确保条件渲染且不破坏现有层级。

- [ ] **Step 6: 测试与构建**

```bash
cd frontend && bun run test && bun run build
```

Expected: vitest 全过；构建成功。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/desktop/splash.ts frontend/src/desktop/CrashMask.tsx frontend/src/desktop/bootstrap.ts frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(desktop): bootstrap with splash/crash mask before rendering web bundle"
```

---

## Task 6: 设置页「桌面后端」卡片

**Files:**
- Create: `frontend/src/desktop/DesktopBackendSettings.tsx`
- Modify: `frontend/src/pages/setting/Setting.tsx`
- Modify: `frontend/src/router/DynamicRouter.tsx`

- [ ] **Step 1: 创建 DesktopBackendSettings.tsx**

```tsx
import { useEffect, useState } from 'react';
import { Button, Card, Input, Radio, Space, Tag, message } from 'antd';
import {
  type BackendMode,
  getBackendConfig,
  setBackendMode,
  startBackend,
  stopBackend,
} from './bridge';
import { showSplash } from './splash';

type Health = 'unknown' | 'ok' | 'down';

async function probe(baseUrl: string): Promise<Health> {
  try {
    const res = await fetch(`${baseUrl}/health`);
    return res.ok ? 'ok' : 'down';
  } catch {
    return 'down';
  }
}

/** 仅 Tauri 环境由设置页挂载：local/remote 切换，保存后整页重载重走引导 */
export default function DesktopBackendSettings() {
  const [mode, setMode] = useState<BackendMode>('local');
  const [remoteUrl, setRemoteUrl] = useState('');
  const [endpoint, setEndpoint] = useState<string | null>(null);
  const [health, setHealth] = useState<Health>('unknown');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getBackendConfig().then((cfg) => {
      setMode(cfg.mode);
      setRemoteUrl(cfg.remoteUrl ?? '');
      setEndpoint(cfg.baseUrl);
    });
  }, []);

  useEffect(() => {
    if (!endpoint) {
      setHealth('unknown');
      return;
    }
    let alive = true;
    void probe(endpoint).then((h) => alive && setHealth(h));
    return () => {
      alive = false;
    };
  }, [endpoint]);

  const handleSave = async () => {
    const url = remoteUrl.trim().replace(/\/+$/, '');
    if (mode === 'remote') {
      if (!/^https?:\/\/.+/.test(url)) {
        message.error('远程地址须以 http:// 或 https:// 开头');
        return;
      }
      const h = await probe(url);
      if (h !== 'ok') {
        message.error('无法连接该远程后端（/health 不通）');
        return;
      }
    }
    setBusy(true);
    try {
      await setBackendMode(mode, mode === 'remote' ? url : undefined);
      if (mode === 'local') {
        showSplash('正在启动本机后端…');
        await startBackend();
      } else {
        // 切 remote 必须停掉本机 sidecar，避免残留进程
        await stopBackend();
      }
      // 整页重载：网络重写基址、鉴权、各 WS/SSE 全部按新模式重新初始化
      window.location.reload();
    } catch (e) {
      setBusy(false);
      message.error(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Card title="桌面后端" style={{ maxWidth: 640 }}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Radio.Group
          value={mode}
          onChange={(e) => setMode(e.target.value as BackendMode)}
          options={[
            { label: '本机后端（应用自启 sidecar，免登录）', value: 'local' },
            { label: '远程后端（走登录鉴权）', value: 'remote' },
          ]}
        />
        <Input
          placeholder="https://your-quantcell-host"
          value={remoteUrl}
          disabled={mode !== 'remote'}
          onChange={(e) => setRemoteUrl(e.target.value)}
        />
        <Space>
          {endpoint && <span>当前地址：{endpoint}</span>}
          {health === 'ok' && <Tag color="success">在线</Tag>}
          {health === 'down' && <Tag color="error">不可用</Tag>}
          {health === 'unknown' && <Tag>未知</Tag>}
        </Space>
        <Button type="primary" loading={busy} onClick={handleSave}>
          保存并切换
        </Button>
        <span style={{ color: '#94a3b8', fontSize: 12 }}>
          切换将重启界面。本机模式数据保存在应用私有数据目录。
        </span>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 2: Setting.tsx 条件插入菜单项**

import 区加：

```tsx
import { IconDeviceDesktop } from "@tabler/icons-react";
import { isTauri } from "@/desktop/env";
```

把 `const menus = [ ... ] satisfies ...` 整段替换为：

```tsx
  const menus = [
    ["general", t("general_settings") || "通用设置", <IconPalette size="1em" />],
    ["env", t("env_variables") || "环境变量", <IconVariable size="1em" />],
    ["exchange", t("exchange_settings") || "交易所设置", <IconBuildingBank size="1em" />],
    ["notifications", t("notification_settings") || "通知设置", <IconBell size="1em" />],
    ["model", t("model_settings") || "模型设置", <IconRobot size="1em" />],
    ["info", t("system_info") || "系统信息", <IconInfoCircle size="1em" />],
    ["plugins", t("plugin_management") || "插件管理", <IconPuzzle size="1em" />],
    // 仅桌面壳显示；Web 版无此入口
    ...(isTauri()
      ? ([["desktop-backend", "桌面后端", <IconDeviceDesktop size="1em" />]] satisfies [
          string,
          string,
          React.ReactElement,
        ][])
      : []),
  ] satisfies [string, string, React.ReactElement][];
```

- [ ] **Step 3: DynamicRouter.tsx 加路由**

在其他 setting 懒加载旁加：

```tsx
const DesktopBackendSettings = lazy(() => import('@/desktop/DesktopBackendSettings'));
```

在 `/setting` children 中 `plugins` 项之后加：

```tsx
            { path: 'desktop-backend', element: <DesktopBackendSettings /> },
```

- [ ] **Step 4: 构建门禁并提交**

```bash
cd frontend && bun run build
```

Expected: 成功。

```bash
git add frontend/src/desktop/DesktopBackendSettings.tsx frontend/src/pages/setting/Setting.tsx frontend/src/router/DynamicRouter.tsx
git commit -m "feat(desktop): add desktop backend mode card to settings page"
```

---

## Task 7: Tauri 配置切到 frontend + dev 联调

**Files:**
- Modify: `desktop/src-tauri/tauri.conf.json`
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: 修改 tauri.conf.json 的 build 段**

将 `build` 对象替换为：

```json
  "build": {
    "frontendDist": "../../frontend/dist",
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": "bun run --cwd ../../frontend dev",
    "beforeBuildCommand": "bun install --cwd ../../frontend && bun run --cwd ../../frontend build"
  },
```

（路径相对 `desktop/src-tauri/`；其余字段不动，CSP 保持 null。）

- [ ] **Step 2: vite.config.ts 加 strictPort**

`server` 对象中加 `strictPort: true`：

```ts
  server: {
    host,
    port,
    strictPort: true,
    allowedHosts: true,
    proxy: {
```

- [ ] **Step 3: dev 联调验证（手动）**

确保无其他 sidecar/应用残留：

```bash
pgrep -fl quantcell-backend || echo "clean"
```

启动 dev：

```bash
cd desktop && ./ui/node_modules/.bin/tauri dev
```

（此阶段 desktop/ui 仍存在，借用其本地 @tauri-apps/cli；Task 8 废弃后改用 `bunx --bun @tauri-apps/cli dev` 或在 frontend 装 CLI。）

预期：Vite 5173 起、Tauri 窗口出、Splash 显示、约 1 分钟内 sidecar 就绪、**免登录直达 /chart**，无登录跳转。DevTools Console 无 `/api` 404。

- [ ] **Step 4: 提交**

```bash
git add desktop/src-tauri/tauri.conf.json frontend/vite.config.ts
git commit -m "build(desktop): point tauri shell at frontend dev/build outputs"
```

---

## Task 8: 废弃 desktop/ui + 更新 README

**Files:**
- Move: `desktop/ui/` → 临时隔离目录
- Modify: `desktop/README.md`

- [ ] **Step 1: 隔离废弃目录（按项目规范用 mv，禁止 rm）**

```bash
Q="/tmp/qc-desktop-ui-deprecated-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$Q"
mv desktop/ui "$Q/"
echo "desktop/ui 已移至: $Q"
```

- [ ] **Step 2: 确认 tauri dev/build 不再依赖 desktop/ui**

`tauri.conf.json` 的 command 与 dist 均指向 `../../frontend`；Rust 构建不引用 `../ui`。全局检索确认无残留引用：

```bash
grep -rn "ui/dist\|localhost:1420" desktop/src-tauri/ || echo "无残留引用"
```

Expected: 仅可能出现在注释/文档；配置文件无命中。

CLI 调用方式统一改为在 `desktop/` 下用 npx/bunx（frontend 不装 CLI 时）：

```bash
cd desktop && bunx @tauri-apps/cli dev
```

在 `desktop/README.md` 中更新「开发/构建」章节为：

```markdown
## 开发

前端复用仓库根目录的 `frontend/` 工程（Web/桌面单一代码库）：

```bash
# 终端 1：前端 dev（Vite 5173，strictPort）
cd frontend && bun run dev
# 终端 2：Tauri 壳（自动拉起 sidecar）
cd desktop && bunx @tauri-apps/cli dev
```

或直接 `cd desktop && bunx @tauri-apps/cli dev`（beforeDevCommand 会自动起前端）。

## 打包

```bash
bash desktop/scripts/build-backend.sh   # 先打 sidecar（约 3-5 分钟）
cd desktop && bunx @tauri-apps/cli build
```

产物：`desktop/src-tauri/target/release/bundle/dmg/QuantCell_0.1.0_aarch64.dmg`
```

- [ ] **Step 3: 提交**

```bash
git add -A desktop/README.md desktop/ui
git commit -m "chore(desktop): retire desktop/ui, shell now reuses frontend app"
```

（`git add -A desktop/ui` 会记录删除；文件实体在隔离目录可恢复。）

---

## Task 9: 全量门禁

- [ ] **Step 1: 后端单测**

```bash
cd backend && .venv/bin/python -m pytest tests/unit/test_desktop_entry.py tests/unit/test_desktop_auth.py -v
```

Expected: 全 PASS。

- [ ] **Step 2: 前端单测 + 类型/构建**

```bash
cd frontend && bun run test && bun run build
```

Expected: vitest 全 PASS（env 5 + network 10）；`tsc -b && vite build` 成功，无 TS/打包错误。

- [ ] **Step 3: Rust 测试**

```bash
cd desktop/src-tauri && cargo test
```

Expected: 6 个用例全 PASS（M1 既有用例不受影响）。

- [ ] **Step 4: Web 版回归（确保适配层零污染）**

```bash
cd frontend && bun run build
```

确认产物中适配模块被打入但注册逻辑全部以 `isTauri()` 为前置（代码走查 main.tsx/network.ts/AuthGuard，Web 下不安装补丁、不放行鉴权）。Web 冒烟可选手动：`bun run dev` + uvicorn :8000，登录与图表正常。

- [ ] **Step 5: 若以上有红项，修复后重跑对应步骤；全绿后进入 Task 10**

---

## Task 10: release 打包 + E2E 冒烟（macOS）

**Files:** 无新增代码；产出 dmg 与手动验收记录。

- [ ] **Step 1: 重新打 sidecar（含 Task 1 的 env 注入）**

```bash
bash desktop/scripts/build-backend.sh
```

Expected: `desktop/src-tauri/binaries/quantcell-backend-aarch64-apple-darwin` 更新。

- [ ] **Step 2: 打 release 包**

```bash
cd desktop && bunx @tauri-apps/cli build
```

Expected: 产出新的 `QuantCell.app` 与 `QuantCell_0.1.0_aarch64.dmg`。

- [ ] **Step 3: 启动并执行 8 项冒烟清单**

```bash
open desktop/src-tauri/target/release/bundle/macos/QuantCell.app
```

逐项验收（记录通过/问题）：

1. Splash 约 1 分钟 → 免登录直达图表页，K 线渲染
2. 9 个主菜单 + 回测列表/详情/配置/回放 + 设置各子页逐页打开，无白屏、Console 无 /api 404
3. 策略智能体 SSE 流式对话可发送并收到流式回复（验证 fetch 重写）
4. 策略任务 Worker 日志面板与回测进度 WebSocket 连通（验证 WS 重写）
5. 设置 → 插件管理可打开；已装插件菜单可见可进入
6. 设置 → 桌面后端：remote 填非法地址报错；填有效地址后本机 sidecar 被停止（`pgrep -fl quantcell-backend` 为空）且出现登录要求；切回 local 免登录、sidecar 重启、地址跟随新端口
7. `kill -9` Python 子进程 → CrashMask 弹出 → 点重启 → 自动 reload 恢复在线
8. Cmd+Q 与红点关窗后 2 秒内 `pgrep -fl quantcell-backend` 为空

- [ ] **Step 4: 修复冒烟中发现的问题（每个问题独立提交），重打并重验受影响项**

- [ ] **Step 5: 全部通过后，汇总 M2 交付报告（提交、产物、已知限制），更新总体进度**

---

## 自审记录（写计划时已核对）

- **Spec 覆盖**：§2 架构→Task 2/5/7；§3.1 引导→Task 5；§3.2 网络重写（16 fetch + 3 WS 两类规则）→Task 3+4；§3.3 免登录→Task 1+4；§3.4 崩溃/模式→Task 5+6；§4 配置/CSP/federation→Task 7（federation chunk 在 Task 10 第 2 项专项验收）；§5 文件结构→各 Task；§6 测试→Task 1/2/3/9；§7 风险→Task 3/10；§8 验收→Task 9/10。无遗漏。
- **类型一致性**：`BackendMode`/`DesktopRuntime` 定义于 env.ts，bridge.ts/network.ts/bootstrap/CrashMask/Settings 全部引用同一来源；Rust DTO 字段 `baseUrl`/`remoteUrl`/`status` 与 bridge.ts 接口一致（已核对 backend.rs:74-103）。
- **关键事实核对**：Rust `setup` 不自动起 sidecar（bootstrap 必须在 local+stopped 时调 startBackend，已写入 Task 5）；DTO local 的 baseUrl 为 `http://127.0.0.1:{port}`；WS 流路径以 `/api/v1` 与 `/ws` 起始（重写前缀两者都覆盖）；命令 cwd 为 src-tauri，frontend 相对路径是 `../../frontend`。
