# Tauri 桌面客户端 M2：整套 Web 前端移植设计

日期：2026-09-22
状态：已批准（对话内分节确认）
前置：[2026-09-21-tauri-desktop-client-design.md](./2026-09-21-tauri-desktop-client-design.md)、[M1 实施计划](../plans/2026-09-21-tauri-desktop-m1-skeleton.md)

## 1. 目标与范围

M1 已交付：Tauri 壳 + PyInstaller sidecar + 动态端口 + local/remote 模式 + 健康探活/崩溃重启/进程回收，桌面 UI 仅一个占位页。

M2 目标：**让现有 Web 前端 `frontend/` 的全部页面在桌面壳内运行**，单一代码库，Web 版行为不变。

范围内：

- 9 个主菜单页面全部进壳：图表、策略智能体、策略管理、策略任务、数据管理、RL 训练、模型注册、集成、风控；以及回测、因子分析、模型管理、K 线回放、设置等全部子路由
- 动态插件系统（PluginRegistry、插件菜单、PluginPage）原样保留
- local 模式免登录；remote 模式保留登录页与 token 流程
- 冷启动 Splash、崩溃遮罩、模式切换设置项
- macOS 本机 dev 与 release(dmg) 验证

范围外（沿用原设计）：三平台 CI（M3）、代码签名公证、sidecar 瘦身（torch 导致的 430MB/冷启约 1 分钟，单开优化任务）、单实例锁与父进程探活兜底。

### 关键决策（用户已确认）

1. 整套移植 Web 前端（非只做核心 4-5 页）
2. 工程方案：Tauri 壳直接加载 `frontend/` 工程，不复制源码、不做 monorepo 抽包
3. local 免登录，remote 走登录
4. 插件系统保留

## 2. 总体架构

```
┌────────────────────────────────────────────────────────┐
│  Tauri 壳 desktop/src-tauri（M1 已建成，Rust 基本不动）    │
│  · sidecar 生命周期 / 动态端口 / 模式持久化 / 崩溃事件      │
│  · frontendDist → ../../frontend/dist                    │
│  · devUrl       → http://localhost:5173                  │
└───────────────────────┬────────────────────────────────┘
                        │ tauri invoke / backend:event
┌───────────────────────▼────────────────────────────────┐
│  现有 frontend/（单一代码库，bun + Vite + React18）        │
│  ┌──────────────────────────────────────────────────┐  │
│  │ src/desktop/ 新增薄适配层（仅 Tauri 环境激活）      │  │
│  │  · env.ts        环境探测 / 桌面运行时状态           │  │
│  │  · bridge.ts     invoke 封装与类型                  │  │
│  │  · bootstrap.ts  启动引导（拿配置/等健康/注入）      │  │
│  │  · network.ts    全局 fetch/WebSocket 重写          │  │
│  │  · DesktopSplash 冷启动遮罩                         │  │
│  │  · CrashMask     崩溃遮罩 + 重启                    │  │
│  │  · DesktopBackendSettings 模式设置卡片              │  │
│  └──────────────────────────────────────────────────┘  │
│  9 个业务页面 + 插件 + 登录页：零改动在壳内运行             │
└────────────────────────────────────────────────────────┘
```

环境探测：新增依赖 `@tauri-apps/api`，以 `'__TAURI_INTERNALS__' in window` 判定。适配层仅在 Tauri 环境动态激活；Web 版构建不注册任何全局补丁，行为与现状完全一致。

M1 的 `desktop/ui/` 废弃（按项目规范 mv 到临时隔离目录，不直接 rm）；其已验证的健康轮询、崩溃事件、模式切换交互迁移进 `src/desktop/`。Rust 侧 commands（get_backend_config / backend_restart / backend_stop / set_backend_mode 等）全部保留。

## 3. 适配层详细设计

### 3.1 启动引导 bootstrap.ts

在 `main.tsx` 的 `createRoot().render()` 之前：

```ts
if (isTauri()) {
  await bootstrapDesktop()  // Web 版直接跳过
}
```

bootstrapDesktop 流程：

1. 挂载 `DesktopSplash`（独立于 React，直接渲染到 #root，避免依赖未就绪的业务 bundle）
2. `invoke<BackendConfig>('get_backend_config')` → `{ mode, port | remoteUrl }`
3. local 模式：以 1s 间隔轮询 `http://127.0.0.1:<port>/health`，显示「后端启动中…」（冷启约 1 分钟）；就绪后进入注入
4. remote 模式：校验 remoteUrl 的 `/health`（超时 3s）；不通则显示错误页并提供「前往设置修改地址」（允许停在设置，不卡死）
5. 注入网络层（3.2）、写桌面运行时状态、注册 `backend:event` 监听
6. 卸载 Splash，渲染 App

### 3.2 网络注入（核心，含实测风险）

现状盘点：

- axios 实例（[api/index.ts](../../../frontend/src/api/index.ts)）已支持动态 baseURL，经 `getApiBaseUrl()`（[portConfig.ts](../../../frontend/src/utils/portConfig.ts)）派生；WebSocket 经 `getWebSocketUrl()` 派生
- **实测有 16 处绕过 axios 直接用相对路径 `fetch('/api/v1/...')`**（agent SSE 流式对话、指标 execute/ai-generate、logout、sessions 等）。在 Tauri 内页面 origin 是 `tauri://localhost`（Windows 为 `http://tauri.localhost`），相对路径会打到壳自身而非 sidecar，必然 404
- **另有 3 处 WebSocket 手工用 `window.location.host` 拼接**（[backtest.ts:54-56](../../../frontend/src/api/backtest.ts#L54-L56)、agentApi.ts:446、workerApi.ts:442）：Tauri 下 location.host 是无端口的 `localhost`/`tauri.localhost`，拼出的 `ws://localhost/api/...` 不含 sidecar 动态端口，连不上。它们不走 `getWebSocketUrl()`，无法仅靠扩展该函数覆盖

采用**单点全局重写**而非逐点修改 19 个调用点（未来新增调用也不会漏）。`network.ts` 在 Tauri 环境保存原始 `window.fetch` 与 `window.WebSocket` 后替换，统一重写判定（设页面 origin host 为 P = `window.location.host`，后端 base 为 B）：

1. 相对路径且以 `/api`、`/ws` 起始 → `${B}${path}`
2. 绝对 URL 但其 host 等于 P（即误指向壳自身的 `http(s)://localhost`、`ws(s)://localhost`、`tauri.localhost`）且路径以 `/api`、`/ws` 起始 → 用 B 替换其 origin（WebSocket 按 B 的 http/https 同步取 ws/wss），保留路径与 query
3. 其余 URL（真实第三方、插件远程资源、已指向 B 的地址）原样透传

- 扩展 `getApiBaseUrl()`/`getWebSocketUrl()`：Tauri 环境优先读桌面运行时注入的 base（`http://127.0.0.1:<port>` 或 remoteUrl），使 axios 调用与 SSE 的 query token 链接管同一地址
- Authorization 头：透传调用方传入的 headers；local 免登录下后端豁免，不强制注入

边界与风险：

- 全局补丁仅在 `isTauri()` 时注册一次；幂等（保存原始引用并加标记，重复 bootstrap 不嵌套包装）
- 重写只认「相对路径 /api、/ws」与「host 等于页面自身 P 且路径 /api、/ws」两类，绝不触碰其他完整 URL，避免误伤第三方请求
- 已知有意为之的折中标注 `ponytail:` 注释：比逐点修改侵入小但属于猴子补丁，升级 Vite/Tauri 大版本时需回归网络用例

### 3.3 local 免登录

前端：

- [AuthGuard.tsx](../../../frontend/src/components/AuthGuard.tsx) 增加分支：`isTauri() && desktopRuntime.mode === 'local'` 时直接放行（不看 access_token）
- remote 模式维持现状（无 token 跳 /login）
- 模式切换 local→remote：清除可能存在的本地直通标记，由路由守卫自然导向登录；remote→local：直接放行

后端：

- [desktop_entry.py](../../../backend/desktop_entry.py) 启动时注入环境变量 `QUANTCELL_DESKTOP_LOCAL=1`
- [auth.py](../../../backend/utils/auth.py) 的 `_auth_disabled()` 增加一条：该变量为 `1/true/yes` 时豁免鉴权。写法与现有 debug 旁路一致，且复用其「APP_ENV=production/prod 时强制不豁免」的安全闸门——sidecar 常规不带生产环境变量；若将来以生产环境变量跑 sidecar，豁免自动失效（fail-closed）
- 常规 `uvicorn main:app` 启动不设置该变量，鉴权完全不受影响

安全边界：豁免仅存在于监听 127.0.0.1 的本机 sidecar 进程内，不产生长期令牌，应用数据目录保持用户私有权限。remote 模式连接的远端服务鉴权策略不变。

### 3.4 崩溃遮罩与模式切换

- 监听 M1 已有的 `backend:event`：`terminated` 且 `status=crashed` 时显示 `CrashMask`（全屏，红色提示 + 「重启后端」按钮，调用 invoke('backend_restart')）；重启期间复用 Splash
- 重启成功后 bootstrap 重新注入新端口（M2 修复了 M1 验收中观察到的并发重启互斥，已在 `971fa29`/`262c0da` 落地）
- 设置：现有 Setting 左侧菜单在 Tauri 环境新增「桌面后端」项，卡片含 local/remote 单选、remote 地址输入、当前 endpoint 与健康徽章、保存后 invoke('set_backend_mode') 并按模式 start/stop sidecar、重新引导网络层。Web 版不显示该项

## 4. 工程配置

### tauri.conf.json（desktop/src-tauri）

- `build.frontendDist`：`../ui/dist` → `../../frontend/dist`
- `build.devUrl`：`http://localhost:1420` → `http://localhost:5173`
- `beforeDevCommand`：`bun run --cwd ../../frontend dev`（命令 cwd 为 src-tauri/；frontend Vite 已默认 5173；增加 `server.strictPort: true` 防止端口漂移导致 devUrl 失配）
- `beforeBuildCommand`：`bun install --cwd ../../frontend && bun run --cwd ../../frontend build`
- CSP：M1 为 `null`。M2 前端资源变复杂（monaco webworker、插件 bundle、动态图表），评估两条路线：
  - 首选：维持 `csp: null`（Tauri 2 下即不注入 CSP 限制），M2 不为 CSP 调优投入；安全模型依赖 sidecar 绑定 127.0.0.1 与应用沙箱
  - 若加固：`connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:* http://* https://*`、`worker-src 'self' blob:`、`script-src 'self' 'unsafe-eval'`（monaco/联邦插件需要 eval）。remote 任意地址需求使 connect-src 实际退化为放行所有 http(s)，加固收益有限，故首选维持 null 并在文档标注
- capabilities：M1 的 core/shell/event/opener 权限已够；HTTP 走 WebView 直连，不引 tauri http 插件
- bundle.externalBin、图标、identifier 不变

### 模块联邦注意

frontend 使用 `@originjs/vite-plugin-federation`（仅 host，未配 remotes，无运行时远程依赖），产物为 ESM。Tauri 2 现代 WebView 支持；其动态 import 的 chunk 路径在 tauri origin 下按根相对加载。M2 验收需专门打开「图表 + 智能体 + 回测回放」三页确认联邦 shared chunk 与懒加载 chunk 在自定义协议下无 404。若出现 chunk 路径问题，设置 `base: './'` 或 Tauri 推荐的绝对路径（实施时以实测二选一，不预先改）。

### 依赖

- frontend 新增运行时依赖：`@tauri-apps/api@^2`
- frontend 新增 devDependency：`vitest`（仅用于适配层纯函数单测）
- desktop/ui 的 React/antd 等依赖随目录废弃；desktop 下不再需要独立 UI 工程的 node_modules

## 5. 文件结构（M2 完成后）

```
frontend/src/
├── desktop/                    # 新增，桌面适配层
│   ├── env.ts                  # isTauri / 运行时模式与 base
│   ├── bridge.ts               # invoke 封装 + BackendConfig 类型
│   ├── bootstrap.ts            # 启动引导
│   ├── network.ts              # fetch/WebSocket 全局重写
│   ├── DesktopSplash.tsx
│   ├── CrashMask.tsx
│   └── DesktopBackendSettings.tsx
├── main.tsx                    # 改造：render 前条件 await bootstrap
├── components/AuthGuard.tsx    # 改造：local 直通分支
├── utils/portConfig.ts         # 改造：Tauri 环境读桌面 base
└── pages/setting/              # 改造：菜单条件挂「桌面后端」
desktop/
├── scripts/build-backend.sh    # 不变
└── src-tauri/                  # Rust/配置：tauri.conf.json 指向 frontend
backend/
├── desktop_entry.py            # 改造：注入 QUANTCELL_DESKTOP_LOCAL=1
└── utils/auth.py               # 改造：豁免分支 + 生产 fail-closed
```

## 6. 测试策略

- 后端 pytest：新增 `QUANTCELL_DESKTOP_LOCAL` 用例——变量开启时豁免、关闭时 401、`APP_ENV=production` 时即使开启也不豁免；沿用现有 auth 测试风格，TDD
- 前端 vitest：仅覆盖适配层纯逻辑——isTauri 判定、URL 重写规则（相对 /api、/ws 命中；host=页面自身的绝对 ws URL 替换 origin；第三方绝对 URL 透传；幂等不二次包装）、AuthGuard local 直通判定。不新增页面测试（页面零改动）
- 前端构建门禁：`cd frontend && bun run build` 必须通过（项目规范，不用 dev 验收）
- Rust：M1 测试保持不动（cargo test 6 个用例）
- E2E 手动冒烟（macOS dmg）：
  1. 双击应用 → Splash 约 1 分钟 → 免登录直达图表页，K 线正常
  2. 9 个主菜单 + 回测列表/详情/配置/回放 + 设置各子页逐页打开无白屏/console 404
  3. 策略智能体 SSE 流式对话可发送（验证 fetch 重写）
  4. Worker 日志面板 WebSocket 连通（验证 WS 重写）
  5. 插件管理页可打开，已装插件菜单可见可进
  6. 设置切 remote（填无效地址报错；填有效地址出现登录要求且本机 sidecar 停止）；切回 local 直通且 sidecar 重启、baseURL 跟随新端口
  7. kill -9 Python 子进程 → CrashMask → 重启恢复
  8. Cmd+Q 与红点关窗后 pgrep 无 sidecar 残留

## 7. 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 19 处相对路径 fetch/WS 在 tauri origin 失效 | 单点全局重写（3.2）；E2E 第 3、4 项专项验证；vitest 固化重写规则 |
| 模块联邦/懒加载 chunk 在 tauri 自定义协议下 404 | E2E 专项三页验证；以实测决定 base 配置，不预先改动 |
| 免登录豁免被误带到生产/常规 uvicorn | 仅 sidecar 注入环境变量；复用 production fail-closed 闸门；pytest 三态覆盖 |
| 全局 fetch 补丁误伤第三方/插件请求 | 只重写 /api、/ws、/health 前缀的相对路径，绝对 URL 透传；幂等；仅 Tauri 注册 |
| monaco/echarts 等大依赖进入壳进一步拖慢 | JS 体积相对 430MB sidecar 可忽略；懒加载 chunk 已拆分；瘦身独立任务 |
| Web 版被适配层污染 | 所有补丁以 isTauri() 为前置；Web 构建不注册；bun run build 双形态验证（实际无独立桌面构建，同一份产物，靠运行时探测） |
| remote 模式 CORS | M1 已在 sidecar 注入 CORS_ORIGINS；remote 连远端沿用后端现有 CORS 配置 |

## 8. 验收标准

- `cd frontend && bun run build`、`cd desktop/src-tauri && cargo test`、后端新增 pytest 三态、前端 vitest 全绿
- macOS release 产物 dmg 重新生成，E2E 冒烟 8 项全部通过（留用户手动验收记录）
- Web 版（`bun run dev` + uvicorn）登录、各页面、SSE、WS 行为与 M2 前一致
- `desktop/ui/` 已隔离废弃，仓库内不存在两套桌面 UI
