# QuantCell 桌面端自动升级功能设计

日期：2026-10-28
状态：已评审通过（方案 A：Tauri 原生 updater 承载升级）

## 1. 背景与目标

QuantCell 桌面端已具备 CI 打包分发能力（Tauri 2 + PyInstaller sidecar，tag `v*` 触发出三平台五架构包），但产物仅存于 Actions Artifacts，无发布渠道、无更新器。本设计为桌面端补齐「检查更新 → 下载 → 验签 → 安装 → 重启」的完整升级链路，支撑后续分发推广与产品迭代。

**已确认的约束**：

- **更新渠道**：双渠道。GitHub Releases 为主渠道，镜像源地址可配置（应对国内下载慢）。
- **升级粒度**：整包更新。Rust 壳 + 内嵌前端 + sidecar 后端打成一个安装包整体替换（Tauri 官方标准方式）。
- **覆盖范围**：仅桌面端。Web / remote 部署形态本期不纳入自动升级。
- **发布通道**：仅 stable 单通道。
- **签名现状**：无 OS 级代码签名。Tauri updater 使用 minisign 签名（内建于插件，不依赖 Apple / Windows 证书），与现状兼容。

**非目标（明确不做）**：

- 不做分模块 / 热更新；
- 不做 beta 灰度通道；
- 不做强制更新（stable 交易软件，升级提示可关闭）；
- 后端 sidecar 不承载任何升级执行逻辑（sidecar 无法可靠自替换，Windows 文件锁 + 进程编排风险，业内无先例）。

## 2. 方案选型（已定）

| 方案 | 描述 | 结论 |
|------|------|------|
| A. Tauri updater 承载升级 | 官方 `tauri-plugin-updater` 完成检查/下载/验证/安装，前端薄 UI，后端仅提供真实版本号 | **采用** |
| B. 后端 FastAPI 自研升级服务 | sidecar 自身负责下载安装 | 否决：运行中 exe 无法自替换，需 helper 进程编排，风险高 |
| C. updater 下载 + 后端版本决策 | 后端维护版本元数据，前端先问后端再升级 | 否决：stable 单通道下无增量价值，过度设计 |

## 3. 版本号单源管理

**原则：git tag 是唯一版本事实源，其余位置全部派生。**

| 位置 | 现状 | 改为 |
|------|------|------|
| 版本事实源 | backend `0.18.0` / Tauri `0.1.0` / FastAPI `1.0.0` / settings 硬编码 `1.0.0` | git tag `vX.Y.Z`，CI 提取 `APP_VERSION` |
| `desktop/src-tauri/tauri.conf.json` version | `0.1.0` 写死 | CI 出包脚本写入 tag 版本（jq/sed 替换） |
| 后端 sidecar | `settings/services.py`、`collector/services/system_service.py` 硬编码 `"1.0.0"` | `desktop/scripts/build-backend.sh` 注入 `QUANTCELL_VERSION` 环境变量 → PyInstaller 打入；`config/settings.py` 的 `app_version` 优先读该变量，两处 service 改为引用 settings；本地 dev 兜底 `"dev"` |
| 前端 | `package.json` version `0.0.0` 自存 | 前端不再维护发布版本号，运行时经 `getVersion()`（`@tauri-apps/api/app`）从 Tauri 壳读取 |
| FastAPI `main.py` app version | `"1.0.0"` | 从 settings `app_version` 读取 |

## 4. 发布流水线（扩展 `desktop-build.yml`）

1. **触发**：tag `v*` push（现有逻辑保留；PR / push 仍只跑 ci-checks 不出包）。
2. **签名密钥**：一次性 `bunx tauri signer generate` 生成 minisign 密钥对；私钥+口令入 GitHub Secrets（`TAURI_SIGNING_PRIVATE_KEY` / `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`），公钥写入 `tauri.conf.json` 的 `plugins.updater.pubkey`。
3. **构建**：现有矩阵（macos-14/aarch64、macos-13/x86_64、windows、ubuntu）不变；构建步骤增加 `TAURI_SIGNING_PRIVATE_KEY` 环境变量后，`tauri build` 自动产出更新产物：
   - macOS：`.app.tar.gz` + `.app.tar.gz.sig`
   - Windows：NSIS `.exe` + `.exe.sig`（updater 使用 NSIS 产物）
   - Linux：`.AppImage.tar.gz` + `.sig`
4. **聚合发布 job**（新增，依赖 5 个构建 job）。实现方式：**不引入 tauri-action**（其会接管 `tauri build` 编排，与现有自定义缓存 / PyInstaller 流程冲突），改用 `softprops/action-gh-release` 创建 Release + 仓库内小脚本聚合生成两份 manifest：
   - 创建 GitHub Release（tag 对应）；
   - 上传全部安装包 + `.sig`；
   - 生成并上传 `latest.json`（platforms 键：`darwin-aarch64` / `darwin-x86_64` / `windows-x86_64` / `linux-x86_64`，各含 `signature` 与 `url`，url 指向本 Release 资产）；
   - 生成并上传 `latest-mirror.json`：同结构，安装包 `url` 重写为镜像地址前缀（如 gh-proxy 类代理前缀 + 原始 Release 资产 URL）。
5. `latest.json` 可通过固定 URL 访问：`https://github.com/<owner>/<repo>/releases/latest/download/latest.json`。

`latest.json` 结构示例：

```json
{
  "version": "0.19.0",
  "notes": "Release notes 摘要（取自 tag 的 release body）",
  "pub_date": "2026-10-28T08:00:00Z",
  "platforms": {
    "darwin-aarch64": { "signature": "<minisign sig>", "url": "https://github.com/.../QuantCell_0.19.0_aarch64.app.tar.gz" },
    "windows-x86_64": { "signature": "<minisign sig>", "url": "https://github.com/.../QuantCell_0.19.0_x64-setup.exe" }
  }
}
```

## 5. 运行时升级架构（桌面端）

### 5.1 Rust 壳层（升级执行者）

- `desktop/src-tauri/Cargo.toml` 新增依赖：`tauri-plugin-updater = "2"`、`tauri-plugin-process = "2"`。
- `desktop/src-tauri/src/config.rs`：持久化配置新增可选字段 `mirror_base_url: Option<String>`（镜像源基地址，None = 仅 GitHub 渠道）。
- `lib.rs` 注册两个插件，并暴露 3 个自定义 command：

| command | 职责 |
|---------|------|
| `update_endpoints()` | 构造 endpoints 数组：GitHub `latest.json` 固定首位 + `{mirror_base_url}/latest-mirror.json`（若配置镜像）。返回给前端展示渠道状态 |
| `update_check()` | 用 `updater::UpdateBuilder` 显式传入 endpoints 按序请求（首个成功响应的 manifest 生效），返回新版信息（version/notes/当前版本）或 null（已是最新） |
| `update_install()` | `download`（分块回调，进度经 `update://progress` 事件推送前端：`{received, total}`）→ 插件强制 minisign 验签 → `install` → `process.relaunch` |

- minisign 公钥写死在 `tauri.conf.json` `plugins.updater.pubkey`（防篡改，随应用分发）。

### 5.2 双渠道语义

- 检查：endpoints 数组按序请求，GitHub 失败自动落到镜像 manifest。
- 下载：**URL 来自命中的那份 manifest**。镜像 manifest 中的安装包 URL 已由 CI 重写为镜像地址，因此走镜像检查成功的大包下载同样不经过 GitHub——这是配置镜像的意义所在。
- 镜像 manifest 本身（`latest-mirror.json`）可托管在任意静态存储/代理；运营侧只需发布时上传两份清单，用户侧只需填一个镜像基地址。

### 5.3 升级流程与数据安全

```
应用启动 → 延迟 8s 静默 update_check（localStorage 节流：每 24h 至多一次自动检查）
  无新版 → 结束
  有新版 → antd Notification 提示一次 + 侧边栏小红点徽标（不弹窗打断）
       → 用户进入设置页「软件更新」卡片查看 Release notes
       → 点击「下载并安装」：
           1. 调后端 engine_status 检查运行中策略/任务
           2. 有任务运行 → 弹二次确认（列出将中断的任务，明确告知会终止）
              空闲 → 直接继续
           3. update_install：进度条展示下载进度
           4. 安装完成后 prompt 重启（relaunch 会杀整棵 sidecar 树，复用现有退出链路）
  任何失败 → endpoints 依次回退后仍失败 → 提示检查网络/镜像配置
           → 安装失败由 updater 保留旧版完整应用 → UI 提供手动下载 Release 安装包链接兜底
```

- **不做强制更新**；Web/remote 模式（浏览器内）不渲染任何更新入口。
- 下载验签失败 / 版本回退攻击由 minisign 校验拦截（旧版本签名的包无法通过 pubkey 校验，updater 同样拒绝降级安装）。

## 6. 前端设计

### 6.1 入口与位置

1. **设置 → 通用设置页（`GeneralSettingsPage.tsx`）新增「软件更新」卡片**（主入口）：
   - 当前版本（`getVersion()` 读取，桌面壳内；Web 模式隐藏整卡）；
   - 渠道状态（主渠道可达性、镜像是否配置）；
   - 「检查更新」按钮 → 有新版时展示版本号 + Release notes + 「下载并安装」按钮；
   - 下载进度条（`downloadAndInstall` 期间）→ 完成后「重启应用」按钮。
2. **轻量提醒**：启动静默检查发现新版 → 一次性 Notification + 侧边栏小红点，点击跳转设置页更新卡片。
3. **镜像配置**：更新卡片内提供镜像基地址输入（可折叠高级项），保存写入桌面 config（复用 `set_backend_config` 同类持久化机制，经 Rust command 落 `config.rs`）。

### 6.2 代码组织

- `frontend/src/api/updateApi.ts`：封装 `update_endpoints` / `update_check` / `update_install` 三个 invoke 与 `update://progress` 事件监听。
- `frontend/src/hooks/useUpdater.ts`：检查节流（启动 8s 后首次 + 24h 周期 + 手动触发绕过节流）、进度状态、二次确认所需的 engine 状态查询编排。
- 更新卡片组件：`frontend/src/pages/setting/` 下新增 `SoftwareUpdateCard.tsx`。
- i18n：`i18n/zh-CN.json` / `en-US.json` 新增 `update.*` 文案段。

## 7. 后端设计（改动极小）

后端**不承载升级执行**，仅修复版本号可见性（服务第 3 节版本单源）：

- `config/settings.py`：`app_version` 字段默认值改为读 `QUANTCELL_VERSION` 环境变量（pydantic-settings 原生支持），兜底 `"dev"`。
- `settings/services.py` 与 `collector/services/system_service.py`：`system_version` 硬编码改为引用 `get_settings().app_version`。
- `main.py` FastAPI `version` 参数引用同一 settings 值。
- 升级确认所需的运行中任务查询复用现有 `worker.strategy_manager.engine_status()`（`/health` 已暴露），不新增接口。

## 8. 测试策略

| 层 | 测试 |
|----|------|
| Rust | `update_endpoints` 构造单测：无镜像（单元素数组）/ 有镜像（两元素、路径正确） |
| 后端 | `app_version` 环境变量注入/兜底单测；两处 service 的 system_version 引用 settings 单测 |
| 前端 | `useUpdater` 节流逻辑（24h 窗口、手动绕过）vitest；`SoftwareUpdateCard` 渲染与状态流转测试（mock invoke） |
| E2E（手动/CI 可选） | 本地静态服务器托管假 `latest.json` + 精简签名包，dev 应用镜像指向 localhost，走通 检查→下载→验签失败→回退→重试 全链路 |
| 流水线 | workflow_dispatch 干跑构建（不发布）；首次真实 tag 发布后人工验证 Release 资产与 latest.json 签名可用 |

## 9. 风险与已知限制

- **updater 平台覆盖**：Windows 更新产物为 NSIS（MSI 不参与热更）；Linux 为 AppImage（deb 用户需手动下载新 deb）——发布说明中注明。
- **首次发布冷启动问题**：已装旧版（无 updater 的 v0.1.0 包）需手动下载新版安装一次，之后才进入自动升级轨道。
- **镜像可用性**：镜像 manifest 与安装包的同步依赖发布纪律（两份清单同一 job 生成，原子性由 CI 保证）。
- **onefile sidecar 冷启动 1 分钟**等既有问题与升级功能正交，不在本设计范围。
