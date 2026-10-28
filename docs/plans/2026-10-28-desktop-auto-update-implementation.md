# 桌面端自动升级 实施计划

> **For agentic workers:** 本计划按任务逐条执行，每个任务结束都有可运行的验证命令。在本仓库中对应两种执行方式：Task 工具逐任务派发（推荐）或在当前会话按顺序内联执行。步骤使用 checkbox（`- [ ]`）跟踪。
>
> 每个任务结束必须提交一次（任务内已给出 commit 命令）。

**Goal:** 为 QuantCell 桌面端（Tauri 2 壳）构建整包自动升级能力：双渠道更新源（官方 GitHub Release + 可选镜像）、24h 节流静默检查、下载进度可视、安装后自动重启、版本号全局单源（git tag → 前后端一致）。

**Architecture:** 升级完全落在 Tauri 壳：Rust 侧 `update.rs` 用 `tauri-plugin-updater` 做 check/install，双渠道 endpoints 由「持久化镜像基址 + 官方常量」在运行时组装；`Update` 对象暂存在 Rust 侧状态槽，前端只拿可序列化的 DTO；镜像基址复用现有 `desktop-config.json`。前端状态收敛到 zustand `updateStore`，UI 落在「桌面后端设置页的软件更新卡 + 侧边栏设置菜单红点」。CI 在 v* tag 构建时用 `--config` 写入版本号、签名 updater 产物，并由 typer 脚本聚合出 `latest.json` / `latest-mirror.json` 随 Release 发布。后端只做一件事：把版本号收敛到 `get_settings().app_version`（兜底 `dev`），桌面端由 Rust spawn sidecar 时注入 `QUANTCELL_VERSION`。

**Tech Stack:** tauri-plugin-updater v2 / tauri-plugin-process v2（Rust）、React 19 + zustand 5 + antd 6（前端）、FastAPI + pydantic-settings（后端）、uv / bun / cargo。

**设计依据:** `docs/plans/2026-10-28-desktop-auto-update-design.md`（commit `7ed9c60d`）

---

## 全局约定（执行者必读）

- 仓库根：`/Users/liupeng/workspace/quant/QuantCell`，下文相对路径均以此为准。
- 后端只在 `backend/` 下用 `uv run ...`；前端只在 `frontend/` 下用 `bun`，验证一律 `bun run build`（前端 dev server 可能正在跑，禁止 `bun run dev`）；Rust 在 `desktop/src-tauri/` 下用 `cargo`。
- 删除文件必须 `mv` 到临时目录，禁止 `rm`。
- antd v6 组件间距：`<Space orientation="vertical" size="middle" style={{ display: 'flex' }}>`（`direction` 已废弃；禁止 `space-y-*`）。
- Rust command 风格对齐 `desktop/src-tauri/src/backend.rs`：错误统一 `Result<T, String>`，锁绝不跨 `.await`。
- Python import 一律文件顶部（`config.settings` 无循环依赖，可安全顶部导入）。
- 本计划文档位于 `docs/plans/`，`docs/*` 被 `.gitignore` 忽略，提交时用 `git add -f docs/plans/xxx.md`。

## 文件结构

| 动作 | 路径 | 职责 |
|------|------|------|
| Modify | `backend/config/settings.py` | `app_version` 兜底 `"dev"` |
| Modify | `backend/main.py` | FastAPI `version` 读 settings |
| Modify | `backend/settings/services.py` | `system_version` 读 settings |
| Modify | `backend/collector/services/system_service.py` | `system_version` 读 settings |
| Modify | `backend/plugins/plugin_manager.py` | 兼容校验读 settings（含 dev 短路） |
| Create | `backend/tests/unit/test_app_version.py` | env 覆盖 / dev 兜底测试 |
| Modify | `backend/tests/unit/test_plugin_manager.py` | 兼容测试固定语义版本 |
| Modify | `backend/tests/unit/test_plugins.py` | 同上 |
| Modify | `desktop/src-tauri/Cargo.toml` | 加 updater / process 插件依赖 |
| Modify | `desktop/src-tauri/capabilities/default.json` | 加 updater / process 权限 |
| Modify | `desktop/src-tauri/tauri.conf.json` | updater 配置 + updater 产物开关 |
| Modify | `desktop/src-tauri/src/config.rs` | 加 `mirror_base_url` 字段 |
| Create | `desktop/src-tauri/src/update.rs` | 升级核心（endpoints / check / install） |
| Modify | `desktop/src-tauri/src/lib.rs` | 注册插件、状态、命令 |
| Modify | `desktop/src-tauri/src/backend.rs` | spawn sidecar 注入 `QUANTCELL_VERSION` |
| Create | `frontend/src/desktop/updateBridge.ts` | Tauri command / event 封装 |
| Create | `frontend/src/desktop/updateStore.ts` | zustand 更新状态 |
| Create | `frontend/src/desktop/useUpdater.ts` | 节流调度 + check / install 动作 |
| Create | `frontend/src/desktop/useUpdater.test.ts` | `shouldCheck` 纯函数测试 |
| Create | `frontend/src/pages/setting/SoftwareUpdateCard.tsx` | 更新卡片 UI（仅桌面端渲染） |
| Modify | `frontend/src/pages/setting/GeneralSettingsPage.tsx` | 挂载更新卡（`isTauri()` 守卫） |
| Modify | `frontend/src/layouts/ConsoleLayout.tsx` | 设置菜单红点 + 静默检查 |
| Modify | `i18n/zh-CN.json`、`i18n/en-US.json` | `update_*` 文案 |
| Create | `desktop/scripts/aggregate_updater_manifest.py` | 发布 manifest 聚合（typer） |
| Modify | `.github/workflows/desktop-build.yml` | 签名注入 + 版本 patch + Release job |

---

### Task 0: 生成本地签名密钥（人工步骤，阻塞后续发布相关验证）

Tauri 的更新包必须用 minisign 私钥签名，公钥内联进 `tauri.conf.json`。密钥只生成一次。

- [ ] **Step 1: 生成密钥对**

```bash
cd desktop && bunx @tauri-apps/cli signer generate -w ~/.tauri/quantcell.key
```

交互中设置密码（记下来，后面 CI 要用）。产物：
- `~/.tauri/quantcell.key`（私钥，绝不入库）
- `~/.tauri/quantcell.key.pub`（公钥，两行文本）

- [ ] **Step 2: 记录公钥内容**

```bash
cat ~/.tauri/quantcell.key.pub
```

Expected: 第一行 `untrusted comment: minisign public key ...`，第二行 base64（`RW...` 开头）。Task 3 会把它填进 `tauri.conf.json`（两行用 `\n` 连接成一个 JSON 字符串）。

---

### Task 1: 后端版本号单源

**Files:**
- Modify: `backend/config/settings.py:34`
- Modify: `backend/main.py:23-25, 59-65`
- Modify: `backend/settings/services.py:8, 33-37`
- Modify: `backend/collector/services/system_service.py:8, 171-175`
- Modify: `backend/plugins/plugin_manager.py:10, 29-31, 242-250, 258-261`
- Create: `backend/tests/unit/test_app_version.py`
- Modify: `backend/tests/unit/test_plugin_manager.py:127`
- Modify: `backend/tests/unit/test_plugins.py:170`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/unit/test_app_version.py`：

```python
"""app_version 单源测试：QUANTCELL_VERSION 环境变量覆盖与 dev 兜底。"""

import pytest

from config.settings import get_settings
from settings.services import SystemService


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """get_settings 是 lru_cache 单例，每个用例前后清缓存，保证 env 变更生效"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_fallback_dev_when_env_missing(monkeypatch):
    """未注入 QUANTCELL_VERSION（源码直跑 / CI 单测）时兜底 dev"""
    monkeypatch.delenv("QUANTCELL_VERSION", raising=False)
    assert get_settings().app_version == "dev"


def test_env_override_from_desktop_shell(monkeypatch):
    """桌面端 Rust spawn_sidecar 会注入 QUANTCELL_VERSION，settings 必须读到"""
    monkeypatch.setenv("QUANTCELL_VERSION", "9.9.9")
    assert get_settings().app_version == "9.9.9"


def test_settings_service_reports_same_version(monkeypatch):
    """settings 服务的 system_version 必须引用 settings，而不是硬编码字符串"""
    monkeypatch.setenv("QUANTCELL_VERSION", "8.8.8")
    result = SystemService().get_system_info()
    assert result["success"] is True
    assert result["system_info"]["version"]["system_version"] == "8.8.8"
```

Run: `cd backend && uv run pytest tests/unit/test_app_version.py -q`
Expected: 1 passed, 2 failed（fallback 用例：默认值仍是 `"1.0.0"`；service 用例：仍硬编码 `"1.0.0"`）

- [ ] **Step 2: settings.py 兜底改为 dev**

`backend/config/settings.py` L33-34：

```python
    app_name: str = "QuantCell API"
    # 版本单源：桌面端由 tauri 壳 spawn sidecar 时注入 QUANTCELL_VERSION（值 = git tag），
    # 其余场景（本地源码、CI 单测）兜底 dev
    app_version: str = "dev"
```

Run: `cd backend && uv run pytest tests/unit/test_app_version.py -q`
Expected: 2 passed, 1 failed（service 用例仍失败，第 3 步才改业务代码）

- [ ] **Step 3: 三处硬编码改读 settings**

3a. `backend/main.py` — 在「导入核心模块」注释块（L22-25）内加一行：

```python
# 导入核心模块
from config.settings import get_settings
from core import lifespan
from core.port_manager import PortAllocationError, port_manager
from utils.logger import LogType, get_logger
```

L59-65 改为：

```python
# 创建FastAPI应用实例（version 走 settings 单源，OpenAPI 与桌面端展示一致）
app = FastAPI(
    title="QuantCell API",
    description="量化交易系统API",
    version=get_settings().app_version,
    lifespan=lifespan,
)
```

（L68 原有的 `from config.settings import get_cors_origin_list` 保留不动。）

3b. `backend/settings/services.py` — 在 `from utils.logger import ...`（L8）之前加：

```python
from config.settings import get_settings
```

L33-37 改为：

```python
            # 获取版本信息
            version_info = {
                "system_version": get_settings().app_version,
                "python_version": platform.python_version(),
                "build_date": "2025-11-30",  # 构建日期，可从环境变量或配置文件获取
            }
```

3c. `backend/collector/services/system_service.py` — 同样在 `from utils.logger import ...`（L8）之前加：

```python
from config.settings import get_settings
```

L171-175 改为与 3b 完全一致的 `version_info`（collector 侧改动与 settings 侧完全相同，不新增单测，由既有 collector 测试与 Step 4 的整轮回归覆盖）。

Run: `cd backend && uv run pytest tests/unit/test_app_version.py -q`
Expected: 3 passed

- [ ] **Step 4: plugin_manager 版本兼容读 settings**

`backend/plugins/plugin_manager.py`：

4a. 顶部 import（L10 之后）加：

```python
from config.settings import get_settings
```

4b. 删除 L31 的 `SYSTEM_VERSION = "1.0.0"` 整个常量（下面两处使用点都改掉后不再需要）：

```python
logger = get_logger(__name__, LogType.APPLICATION)
```

（即 `SYSTEM_VERSION` 那一行删掉，与 logger 行之间保留一个空行。）

4c. L242-250 `_check_version_compatibility` 替换为：

```python
    def _check_version_compatibility(self, manifest: dict) -> bool:
        min_version = manifest.get("min_system_version")
        if not min_version:
            return True
        system_version = get_settings().app_version
        if system_version == "dev":
            # 开发版没有语义化版本可比，视为满足任意插件的最低版本要求
            return True
        try:
            return _parse_version(system_version) >= _parse_version(min_version)
        except (ValueError, TypeError):
            # 原写法 `except ValueError, TypeError:` 是 Python 2 语法（3.14 解析为元组捕获，
            # 属历史遗留），这里规范化为标准元组形式，捕获语义不变
            logger.warning(f"版本号解析失败: min_system_version={min_version}")
            return False
```

4d. L260 日志行改为：

```python
            logger.error(
                f"插件要求系统最低版本 {min_ver}，当前系统版本 {get_settings().app_version}"
            )
```

- [ ] **Step 5: 适配两个既有版本兼容测试**

dev 短路会让原测试的 `is False` 断言全部失效，必须在用例内固定一个语义版本。

5a. `backend/tests/unit/test_plugin_manager.py` — 类内 fixture 区（L12 之后、`temp_dir` 之前）加：

```python
    @pytest.fixture(autouse=True)
    def _clear_settings_cache(self):
        """版本兼容用例会 monkeypatch QUANTCELL_VERSION，前后清掉 settings 缓存"""
        from config.settings import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()
```

L127 方法改为：

```python
    def test_check_version_compatibility(self, plugin_manager, monkeypatch):
        """测试检查版本兼容性（固定语义版本，避免 dev 兜底短路比较）"""
        monkeypatch.setenv("QUANTCELL_VERSION", "1.0.0")

        # 没有要求最低版本
        manifest = {"name": "test", "version": "1.0.0", "main": "main.py"}
        assert plugin_manager._check_version_compatibility(manifest) is True

        # 要求低于当前版本
        manifest["min_system_version"] = "0.1.0"
        assert plugin_manager._check_version_compatibility(manifest) is True

        # 要求高于当前版本
        manifest["min_system_version"] = "999.999.999"
        assert plugin_manager._check_version_compatibility(manifest) is False

        # 无效版本格式错误
        manifest["min_system_version"] = "invalid"
        assert plugin_manager._check_version_compatibility(manifest) is False
```

5b. `backend/tests/unit/test_plugins.py` — 在 `import pytest` 之后（L9 后）加模块级 autouse fixture：

```python
@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """版本兼容用例会 monkeypatch QUANTCELL_VERSION，前后清掉 settings 缓存"""
    from config.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
```

L170 方法改为：

```python
    def test_check_version_compatibility(self, monkeypatch):
        """测试 _check_version_compatibility 方法（固定语义版本，避免 dev 兜底短路比较）"""
        monkeypatch.setenv("QUANTCELL_VERSION", "1.0.0")

        from plugins.plugin_manager import PluginManager

        pm = PluginManager()

        # 无最低版本要求
        manifest = {}
        assert pm._check_version_compatibility(manifest) is True

        # 当前版本 >= 最低版本
        manifest = {"min_system_version": "0.9.0"}
        assert pm._check_version_compatibility(manifest) is True

        # 当前版本 < 最低版本
        manifest = {"min_system_version": "2.0.0"}
        assert pm._check_version_compatibility(manifest) is False

        # 无效版本号
        manifest = {"min_system_version": "invalid"}
        assert pm._check_version_compatibility(manifest) is False
```

- [ ] **Step 6: 跑测试**

Run:

```bash
cd backend && uv run pytest tests/unit/test_app_version.py tests/unit/test_plugin_manager.py tests/unit/test_plugins.py -q
```

Expected: 全部 passed。若 `test_plugins.py` 因自身 mock 结构报错，先单独跑 `uv run pytest tests/unit/test_plugins.py -q` 确认是否为既有问题（`git stash` 后复跑对照），既有问题不要在本任务顺手修。

- [ ] **Step 7: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/config/settings.py backend/main.py backend/settings/services.py \
  backend/collector/services/system_service.py backend/plugins/plugin_manager.py \
  backend/tests/unit/test_app_version.py backend/tests/unit/test_plugin_manager.py \
  backend/tests/unit/test_plugins.py
git commit -m "feat(backend): 版本号收敛到 QUANTCELL_VERSION 单源，兜底 dev"
```

---

### Task 2: 桌面壳依赖与权限

**Files:**
- Modify: `desktop/src-tauri/Cargo.toml:19-25`
- Modify: `desktop/src-tauri/capabilities/default.json:6`
- Modify: `desktop/src-tauri/tauri.conf.json:27-39`

- [ ] **Step 1: Cargo.toml 加依赖**

`desktop/src-tauri/Cargo.toml`，在 `tauri-plugin-shell = "2"` 之后加两行：

```toml
tauri = { version = "2", features = [] }
tauri-plugin-shell = "2"
# 自动升级：检查/下载/安装更新包
tauri-plugin-updater = "2"
# 安装完成后重启进程（Rust 侧 app.process().restart()）
tauri-plugin-process = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

Run: `cd desktop/src-tauri && cargo check`
Expected: 编译通过；首次会拉取 updater / process 依赖（耗时较长）。**此时 lib.rs 还没注册插件，`cargo check` 只要依赖能编译就通过。**

- [ ] **Step 2: capabilities 加权限**

`desktop/src-tauri/capabilities/default.json` 全文改为：

```json
{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "QuantCell 桌面端默认权限：核心能力 + 事件监听 + 更新器/重启；sidecar 从 Rust 侧 spawn，不需要 shell 前端权限",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "core:event:default",
    "core:event:allow-listen",
    "updater:default",
    "process:allow-restart"
  ]
}
```

- [ ] **Step 3: tauri.conf.json 加 updater 配置**

`desktop/src-tauri/tauri.conf.json`：`bundle` 段加 `createUpdaterArtifacts`，顶层加 `plugins` 段。

`bundle` 改为（其余字段不动）：

```json
  "bundle": {
    "active": true,
    "targets": "all",
    "createUpdaterArtifacts": true,
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ],
    "externalBin": ["binaries/quantcell-backend"],
    "resources": ["resources/uv/*"]
  },
```

文件末尾（`"bundle"` 段之后）加：

```json
  "plugins": {
    "updater": {
      "pubkey": "untrusted comment: minisign public key ...\nRW...",
      "endpoints": [
        "https://github.com/pengwow/QuantCell/releases/latest/download/latest.json"
      ],
      "windows": {
        "installMode": "passive"
      }
    }
  }
```

`pubkey` 的值填 Task 0 生成的 `~/.tauri/quantcell.key.pub` 全文（两行，用 `\n` 连接）。注意：**Rust 侧运行时始终用 `UpdaterBuilder::endpoints()` 覆盖这里的 endpoints**，此处保留只为让配置自解释；真正的双渠道逻辑在 `update.rs::endpoints_for`。

- [ ] **Step 4: 校验配置合法**

Run:

```bash
cd desktop/src-tauri && cargo check && python3 -c "import json;json.load(open('tauri.conf.json'));json.load(open('capabilities/default.json'));print('json ok')"
```

Expected: `json ok`，且 `cargo check` 通过。

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add desktop/src-tauri/Cargo.toml desktop/src-tauri/Cargo.lock \
  desktop/src-tauri/capabilities/default.json desktop/src-tauri/tauri.conf.json
git commit -m "feat(desktop): 接入 tauri-plugin-updater/process 与签名产物配置"
```

---

### Task 3: 持久化镜像基址

**Files:**
- Modify: `desktop/src-tauri/src/config.rs:23-38, 91-101`
- Test: `desktop/src-tauri/src/config.rs`（同文件 `#[cfg(test)]` 模块，仓库现有惯例）

- [ ] **Step 1: 写失败测试**

`desktop/src-tauri/src/config.rs` 的 `tests` 模块里，`remote_mode_round_trip` 之后加：

```rust
    #[test]
    fn mirror_base_url_round_trip() {
        let dir = unique_tmp_dir();
        let cfg = PersistedConfig {
            mode: BackendMode::Local,
            remote_url: None,
            mirror_base_url: Some("https://mirror.example.com/quantcell".into()),
        };
        save(&dir, &cfg).unwrap();
        assert_eq!(load(&dir), cfg);
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn legacy_config_without_mirror_loads() {
        // 老版本 desktop-config.json 没有 mirrorBaseUrl 字段，必须回退 None
        let dir = unique_tmp_dir();
        fs::write(config_path(&dir), r#"{"mode":"local","remoteUrl":null}"#).unwrap();
        assert_eq!(load(&dir).mirror_base_url, None);
        let _ = fs::remove_dir_all(&dir);
    }
```

Run: `cd desktop/src-tauri && cargo test config::`
Expected: 编译失败（`PersistedConfig` 没有 `mirror_base_url` 字段 / 缺字段构造报错）

- [ ] **Step 2: 加字段**

`desktop/src-tauri/src/config.rs`，`PersistedConfig` 改为：

```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PersistedConfig {
    #[serde(default)]
    pub mode: BackendMode,
    #[serde(default, rename = "remoteUrl")]
    pub remote_url: Option<String>,
    /// 自定义更新镜像基址（如 https://mirror.example.com/quantcell）；None 表示只用官方源
    #[serde(default, rename = "mirrorBaseUrl")]
    pub mirror_base_url: Option<String>,
}

impl Default for PersistedConfig {
    fn default() -> Self {
        Self {
            mode: BackendMode::Local,
            remote_url: None,
            mirror_base_url: None,
        }
    }
}
```

同时把既有测试 `remote_mode_round_trip` 里的字面量补上新字段：

```rust
        let cfg = PersistedConfig {
            mode: BackendMode::Remote,
            remote_url: Some("https://api.example.com".into()),
            mirror_base_url: None,
        };
```

- [ ] **Step 3: 跑测试**

Run: `cd desktop/src-tauri && cargo test config::`
Expected: 5 passed（3 个既有 + 2 个新增）

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add desktop/src-tauri/src/config.rs
git commit -m "feat(desktop): 持久化更新镜像基址字段"
```

### Task 4: 升级核心模块 `update.rs`

**Files:**
- Create: `desktop/src-tauri/src/update.rs`
- Modify: `desktop/src-tauri/src/backend.rs:158-166`（spawn 注入版本）

本任务只写模块本身；把插件注册进 app 放在 Task 5。为了让 `cargo check` 能编译到新文件，本任务同时把 `mod update;` 加进 `lib.rs`（只加声明，不动插件与 handler）。

- [ ] **Step 1: 新建 update.rs**

创建 `desktop/src-tauri/src/update.rs`：

```rust
//! 自动升级：封装 tauri-plugin-updater。
//!
//! 双渠道：镜像 manifest（用户可选配置）优先，官方 GitHub Release 兜底。
//! 前端不直连 updater 的 JS API —— Updater/Update 在 Rust 侧创建并暂存，
//! 前端只拿可序列化 DTO，进度也只从一条事件出口推送，避免状态漂移。

use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State, Url};
use tauri_plugin_process::ProcessExt;
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::backend::PersistedState;
use crate::config;

/// 官方更新源：GitHub Release 的 latest 固定下载地址
pub const OFFICIAL_ENDPOINT: &str =
    "https://github.com/pengwow/QuantCell/releases/latest/download/latest.json";

/// 下载进度事件名（前端 updateBridge 订阅）
pub const PROGRESS_EVENT: &str = "update://progress";

/// 检查到的待安装更新。check 存入、install 取出；锁绝不跨 await。
#[derive(Default)]
pub struct SharedUpdate(pub Mutex<Option<Update>>);

/// 前端可见的更新信息（updater 的 Update 不可序列化，故单独出 DTO）
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    pub current_version: String,
    pub version: String,
    pub notes: Option<String>,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct ProgressPayload {
    downloaded: u64,
    total: Option<u64>,
}

/// 组装更新源：配置了镜像则镜像在前（更快），官方始终兜底。
/// 镜像基址允许带路径前缀，统一拼 `/latest-mirror.json`。
pub fn endpoints_for(mirror_base: Option<&str>) -> Result<Vec<Url>, String> {
    let mut urls = Vec::new();
    if let Some(base) = mirror_base.map(str::trim).filter(|s| !s.is_empty()) {
        let mirror = format!("{}/latest-mirror.json", base.trim_end_matches('/'));
        urls.push(Url::parse(&mirror).map_err(|e| format!("镜像地址无效: {e}"))?);
    }
    // 常量自身合法；解析失败只可能是改坏了常量，直接 expect
    urls.push(Url::parse(OFFICIAL_ENDPOINT).expect("官方 endpoint 常量必须合法"));
    Ok(urls)
}

/// 读取当前镜像基址（未配置返回 None）
#[tauri::command]
pub fn update_get_mirror(persisted: State<'_, PersistedState>) -> Option<String> {
    persisted.0.lock().unwrap().mirror_base_url.clone()
}

/// 保存镜像基址；传 null 或空串表示恢复「仅官方源」。
#[tauri::command]
pub fn update_set_mirror(
    app: AppHandle,
    persisted: State<'_, PersistedState>,
    mirror_base_url: Option<String>,
) -> Result<(), String> {
    let normalized = mirror_base_url
        .map(|s| s.trim().trim_end_matches('/').to_string())
        .filter(|s| !s.is_empty());
    // 先校验再落盘：坏地址持久化后每次检查都失败，用户很难自查
    endpoints_for(normalized.as_deref())?;

    let data_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let mut guard = persisted.0.lock().unwrap();
    let mut new_cfg = guard.clone();
    new_cfg.mirror_base_url = normalized;
    config::save(&data_dir, &new_cfg).map_err(|e| e.to_string())?;
    *guard = new_cfg;
    Ok(())
}

/// 检查更新：命中则暂存 Update 并返回信息，无更新返回 None。
#[tauri::command]
pub async fn update_check(
    app: AppHandle,
    slot: State<'_, SharedUpdate>,
) -> Result<Option<UpdateInfo>, String> {
    let mirror = {
        // 单独作用域：锁在 await 之前释放
        let persisted = app.state::<PersistedState>();
        let guard = persisted.0.lock().unwrap();
        guard.mirror_base_url.clone()
    };
    let endpoints = endpoints_for(mirror.as_deref())?;

    let updater = app
        .updater_builder()
        .endpoints(endpoints)
        .map_err(|e| format!("更新源配置失败: {e}"))?
        .build()
        .map_err(|e| format!("更新器初始化失败: {e}"))?;

    let found = updater
        .check()
        .await
        .map_err(|e| format!("检查更新失败: {e}"))?;

    let info = match found {
        Some(update) => {
            let info = UpdateInfo {
                current_version: update.current_version.clone(),
                version: update.version.clone(),
                notes: update.body.clone(),
            };
            *slot.0.lock().unwrap() = Some(update);
            Some(info)
        }
        None => {
            *slot.0.lock().unwrap() = None;
            None
        }
    };
    Ok(info)
}

/// 下载并静默安装已暂存的更新，完成后重启应用。
/// 进度按累计字节推送到 `update://progress`。
#[tauri::command]
pub async fn update_install(app: AppHandle, slot: State<'_, SharedUpdate>) -> Result<(), String> {
    // 锁不跨 await：先把 Update 取出来，再下载
    let update = slot
        .0
        .lock()
        .unwrap()
        .take()
        .ok_or("没有待安装的更新，请先检查更新")?;

    let emitter = app.clone();
    let mut downloaded: u64 = 0;
    update
        .download_and_install(
            move |chunk_len, total| {
                downloaded += chunk_len as u64;
                let _ = emitter.emit(PROGRESS_EVENT, ProgressPayload { downloaded, total });
            },
            || {},
        )
        .await
        .map_err(|e| format!("下载安装失败: {e}"))?;

    // 安装完成后必须重启才会加载新版本；Windows 的 passive 安装器会自行接管进程退出
    app.process().restart();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn endpoints_without_mirror_is_official_only() {
        let urls = endpoints_for(None).expect("官方源常量必须可解析");
        assert_eq!(urls.len(), 1);
        assert_eq!(urls[0].as_str(), OFFICIAL_ENDPOINT);
    }

    #[test]
    fn endpoints_with_mirror_puts_mirror_first() {
        let urls = endpoints_for(Some("https://mirror.example.com/qc/")).expect("镜像地址可解析");
        assert_eq!(urls.len(), 2);
        assert_eq!(
            urls[0].as_str(),
            "https://mirror.example.com/qc/latest-mirror.json"
        );
        assert_eq!(urls[1].as_str(), OFFICIAL_ENDPOINT);
    }

    #[test]
    fn endpoints_reject_invalid_mirror_and_ignore_blank() {
        assert!(endpoints_for(Some("not a url")).is_err());
        // 空白镜像基址等同「未配置」，只保留官方源
        assert_eq!(endpoints_for(Some("   ")).expect("空白按未配置处理").len(), 1);
    }
}
```

- [ ] **Step 2: lib.rs 加模块声明**

`desktop/src-tauri/src/lib.rs` L1-3 改为：

```rust
mod backend;
mod config;
mod port;
mod update;
```

- [ ] **Step 3: 编译校验**

Run: `cd desktop/src-tauri && cargo check && cargo test update::`
Expected: 编译通过，`update::tests` 3 passed。可能出现的两类报错及处置：

1. `Url` 不在 `tauri` 根导出 → 在 `Cargo.toml` 加 `url = "2"`，并把 `use tauri::{... Url}` 改成 `use url::Url;`（前者正常则不添加，保持零新增依赖）。
2. `Update` 不是 `Send` → 说明暂存方案不成立，改为暂存 `(Updater, Update)` 也无济于事，此时把 `SharedUpdate` 换成 `Mutex<Option<UpdateInfo>>` 并在 install 时重新 `check()`（多一次网络请求，但语义正确）；此分支需在提交信息里说明。

- [ ] **Step 4: spawn sidecar 注入版本**

`desktop/src-tauri/src/backend.rs` L158-162，在 CORS env 之后加一行：

```rust
            .env("CORS_ORIGINS", CORS_ORIGINS)
            // 版本单源：tauri.conf.json 的 version（CI 由 tag patch）→ 子进程 env →
            // 后端 pydantic-settings 的 app_version，避免后端再维护一份版本号
            .env("QUANTCELL_VERSION", app.package_info().version.to_string())
            // 此处 env 只在 exec 后对子进程生效，挡不住 fork() 后 exec() 前的那次
            // ObjC fork-safety abort；权威设置在 lib::run() 最开头（让本进程及 fork
            // 子进程继承）。这里再写一遍仅为防御 sidecar 自身派生后代进程的场景。
            .env("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES");
```

- [ ] **Step 5: 再校验**

Run: `cd desktop/src-tauri && cargo check && cargo test config::`
Expected: 通过（`package_info()` 需要 `Manager` trait，backend.rs L9 已导入）。

- [ ] **Step 6: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add desktop/src-tauri/src/update.rs desktop/src-tauri/src/lib.rs desktop/src-tauri/src/backend.rs
git commit -m "feat(desktop): 新增升级核心模块并向 sidecar 注入应用版本"
```

---

### Task 5: 注册插件、状态与命令

**Files:**
- Modify: `desktop/src-tauri/src/lib.rs:19-43`

- [ ] **Step 1: 注册**

`desktop/src-tauri/src/lib.rs` 的 builder 链改为：

```rust
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            let persisted = config::load(&data_dir);
            app.manage(backend::PersistedState(std::sync::Mutex::new(persisted)));
            app.manage(backend::SharedRuntime::default());
            app.manage(update::SharedUpdate::default());
            Ok(())
        })
        .on_window_event(|window, event| {
            // 关窗即回收 sidecar（Cmd+Q 路径由 RunEvent::Exit 兜底，两处都幂等）
            if let tauri::WindowEvent::Destroyed = event {
                let _ = backend::signal_stop(window.app_handle());
            }
        })
        .invoke_handler(tauri::generate_handler![
            backend::backend_start,
            backend::backend_stop,
            backend::backend_restart,
            backend::backend_status,
            backend::get_backend_config,
            backend::set_backend_mode,
            update::update_get_mirror,
            update::update_set_mirror,
            update::update_check,
            update::update_install,
        ])
        .build(tauri::generate_context!())
        .expect("启动 QuantCell 桌面端失败");
```

- [ ] **Step 2: 编译校验**

Run: `cd desktop/src-tauri && cargo check`
Expected: 通过，无 warning（`PROGRESS_EVENT` 若报 dead_code，说明 Step 1 漏加 `update::` 命令注册）。

- [ ] **Step 3: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add desktop/src-tauri/src/lib.rs
git commit -m "feat(desktop): 注册升级插件与命令"
```

---

### Task 6: 前端 bridge 与状态 store

**Files:**
- Create: `frontend/src/desktop/updateBridge.ts`
- Create: `frontend/src/desktop/updateStore.ts`

- [ ] **Step 1: 写 updateBridge.ts**

创建 `frontend/src/desktop/updateBridge.ts`（风格对齐同目录 `bridge.ts`）：

```ts
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
```

- [ ] **Step 2: 写 updateStore.ts**

创建 `frontend/src/desktop/updateStore.ts`：

```ts
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
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && bun run build`
Expected: 构建成功（此时还没人引用这两个文件，只验证 TS 与 lint 无问题）。

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/desktop/updateBridge.ts frontend/src/desktop/updateStore.ts
git commit -m "feat(desktop-ui): 新增更新桥接与状态 store"
```

### Task 7: 静默检查调度与更新动作

**Files:**
- Create: `frontend/src/desktop/useUpdater.ts`
- Test: `frontend/src/desktop/useUpdater.test.ts`

- [ ] **Step 1: 写失败测试**

创建 `frontend/src/desktop/useUpdater.test.ts`（同目录平铺，与既有 `env.test.ts` 惯例一致）：

```ts
import { describe, expect, it } from 'vitest';
import { CHECK_INTERVAL_MS, shouldCheck } from './useUpdater';

describe('shouldCheck', () => {
  const now = 1_700_000_000_000;

  it('无历史记录（首次运行）需要检查', () => {
    expect(shouldCheck(0, now)).toBe(true);
  });

  it('距上次检查不足 24h 跳过', () => {
    expect(shouldCheck(now - CHECK_INTERVAL_MS + 1, now)).toBe(false);
  });

  it('距上次检查达到 24h 需要检查', () => {
    expect(shouldCheck(now - CHECK_INTERVAL_MS, now)).toBe(true);
  });

  it('非法时间戳视为需要检查', () => {
    expect(shouldCheck(Number.NaN, now)).toBe(true);
  });
});
```

Run: `cd frontend && bunx vitest run src/desktop/useUpdater.test.ts`
Expected: 失败（`Failed to resolve import './useUpdater'`）

- [ ] **Step 2: 实现 useUpdater.ts**

创建 `frontend/src/desktop/useUpdater.ts`：

```ts
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
```

- [ ] **Step 3: 跑测试**

Run: `cd frontend && bunx vitest run src/desktop/useUpdater.test.ts`
Expected: 4 passed（已实测 `antd` / `@tauri-apps/api` / `i18n/config` 在无 DOM 的 node 环境可正常加载；若仍报模块加载失败，把 `shouldCheck` 与 `CHECK_INTERVAL_MS` 原样移到 `updateStore.ts`，由 `useUpdater.ts` 再导出，测试改从 `./updateStore` 导入）

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/desktop/useUpdater.ts frontend/src/desktop/useUpdater.test.ts
git commit -m "feat(desktop-ui): 24h 节流静默检查与更新动作"
```

---

### Task 8: 软件更新卡片（通用设置页）

**Files:**
- Create: `frontend/src/pages/setting/SoftwareUpdateCard.tsx`
- Modify: `frontend/src/pages/setting/GeneralSettingsPage.tsx:8, 232-256`

- [ ] **Step 1: 新建卡片组件**

创建 `frontend/src/pages/setting/SoftwareUpdateCard.tsx`：

```tsx
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Card, Input, Modal, Progress, Space, Tag, Typography, message } from 'antd';
import { getVersion } from '@tauri-apps/api/app';
import { getUpdateMirror, setUpdateMirror } from '../../desktop/updateBridge';
import { useUpdateStore } from '../../desktop/updateStore';
import { runCheck, runInstall } from '../../desktop/useUpdater';

/** 通用设置页的「软件更新」卡（仅桌面端渲染，调用方负责 isTauri 守卫） */
export default function SoftwareUpdateCard() {
  const { t } = useTranslation();
  const status = useUpdateStore((s) => s.status);
  const info = useUpdateStore((s) => s.info);
  const downloaded = useUpdateStore((s) => s.downloaded);
  const total = useUpdateStore((s) => s.total);
  const error = useUpdateStore((s) => s.error);

  const [currentVersion, setCurrentVersion] = useState('');
  const [mirror, setMirror] = useState('');
  const [savingMirror, setSavingMirror] = useState(false);

  useEffect(() => {
    void getVersion().then(setCurrentVersion);
    void getUpdateMirror().then((value) => setMirror(value ?? ''));
  }, []);

  const handleSaveMirror = async () => {
    setSavingMirror(true);
    try {
      await setUpdateMirror(mirror.trim() || null);
      message.success(t('update_mirror_saved') || '镜像源已保存');
    } catch (e) {
      message.error(e instanceof Error ? e.message : String(e));
    } finally {
      setSavingMirror(false);
    }
  };

  // 有运行中策略时二次确认：安装后应用会重启，策略会被中断
  const handleInstall = () => {
    void runInstall({
      confirm: (running) =>
        new Promise<boolean>((resolve) => {
          Modal.confirm({
            title: t('update_running_confirm_title') || '升级会中断运行中的策略',
            content:
              t('update_running_confirm_content', { count: running }) ||
              `当前有 ${running} 个策略正在运行，升级并重启后将全部中断。确定继续？`,
            okText: t('update_confirm_ok') || '继续升级',
            cancelText: t('update_confirm_cancel') || '取消',
            onOk: () => resolve(true),
            onCancel: () => resolve(false),
          });
        }),
    });
  };

  const percent = total ? Math.min(100, Math.floor((downloaded / total) * 100)) : 0;
  const busy = status === 'checking' || status === 'downloading';

  return (
    <Card title={t('update_title') || '软件更新'} style={{ maxWidth: 640 }}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
        <Space size="small" wrap>
          <span>
            {t('update_current_version') || '当前版本'}：{currentVersion || '-'}
          </span>
          {status === 'idle' && <Tag color="success">{t('update_latest') || '已是最新版本'}</Tag>}
          {status === 'checking' && <Tag>{t('update_checking') || '正在检查更新…'}</Tag>}
          {status === 'available' && info && (
            <Tag color="processing">
              {t('update_available', { version: info.version }) || `发现新版本 ${info.version}`}
            </Tag>
          )}
          {status === 'downloading' && (
            <Tag color="processing">{t('update_downloading') || '正在下载更新'}</Tag>
          )}
          {status === 'error' && <Tag color="error">{t('update_failed') || '更新失败'}</Tag>}
        </Space>

        {status === 'error' && error && <Typography.Text type="danger">{error}</Typography.Text>}

        {status === 'downloading' && <Progress percent={percent} status="active" />}

        {status === 'available' && info?.notes && (
          <Typography.Paragraph
            type="secondary"
            style={{ whiteSpace: 'pre-wrap', marginBottom: 0, maxHeight: 120, overflow: 'auto' }}
          >
            {t('update_notes') || '更新说明'}
            {'\n'}
            {info.notes}
          </Typography.Paragraph>
        )}

        <Space size="small">
          <Button loading={status === 'checking'} disabled={busy} onClick={() => void runCheck()}>
            {t('update_check') || '检查更新'}
          </Button>
          <Button
            type="primary"
            loading={status === 'downloading'}
            disabled={status !== 'available'}
            onClick={handleInstall}
          >
            {t('update_install') || '立即更新'}
          </Button>
        </Space>

        {status === 'available' && (
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            {t('update_restart_hint') || '安装完成后应用将自动重启'}
          </span>
        )}

        <Space.Compact style={{ width: '100%' }}>
          <Input
            placeholder={t('update_mirror_placeholder') || 'https://mirror.example.com/quantcell'}
            value={mirror}
            onChange={(e) => setMirror(e.target.value)}
          />
          <Button loading={savingMirror} onClick={() => void handleSaveMirror()}>
            {t('update_mirror_save') || '保存镜像源'}
          </Button>
        </Space.Compact>
        <span style={{ color: '#94a3b8', fontSize: 12 }}>
          {t('update_mirror_label') || '更新镜像源（可选，留空仅使用官方源）'}
        </span>
      </Space>
    </Card>
  );
}
```

- [ ] **Step 2: 挂载到通用设置页（仅桌面端）**

`frontend/src/pages/setting/GeneralSettingsPage.tsx`：

L8 的 antd 导入保持不变；L9 `import { useSettings } ...` 之后加两行：

```tsx
import { useSettings } from './SettingsContext';
import { useGuestRestriction } from '../../hooks/useGuestRestriction';
import { isTauri } from '../../desktop/env';
import SoftwareUpdateCard from './SoftwareUpdateCard';
```

L253-256（时区区块结束 `</div>` 与「操作按钮」区块之间）改为：

```tsx
        <Divider />

        {/* 软件更新：仅桌面端渲染，Web 模式没有升级能力 */}
        {isTauri() && (
          <>
            <SoftwareUpdateCard />
            <Divider />
          </>
        )}

        {/* 操作按钮 */}
        <div className="flex justify-end gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
```

（原来的 `<Divider />` 保留在时区块之后；卡片下方再补一个 Divider，保证 Web 模式下不会出现连续两条分隔线。）

- [ ] **Step 3: 构建校验**

Run: `cd frontend && bun run build`
Expected: 构建成功。

- [ ] **Step 4: 间距自查**

对照组件树确认：时区区块 → `<Divider />` → 更新卡 → `<Divider />` → 操作按钮；卡片内部相邻元素全部由 `<Space orientation="vertical" size="middle">` 提供 16px 间距，没有新增内联 `margin`。

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/pages/setting/SoftwareUpdateCard.tsx frontend/src/pages/setting/GeneralSettingsPage.tsx
git commit -m "feat(desktop-ui): 通用设置页新增软件更新卡片"
```

---

### Task 9: 侧边栏设置红点

**Files:**
- Modify: `frontend/src/layouts/ConsoleLayout.tsx:24, 31-33, 47-49, 86-95`

- [ ] **Step 1: 引入 store 与调度 hook**

`frontend/src/layouts/ConsoleLayout.tsx`：

L24 antd 导入改为（加 `Badge`）：

```tsx
import { Badge, Button, Drawer, Layout, Menu, type MenuProps, theme } from "antd";
```

L31（`import { pluginRegistry } ...`）之后加：

```tsx
import { useUpdateStore } from "@/desktop/updateStore";
import { useUpdater } from "@/desktop/useUpdater";
```

- [ ] **Step 2: 组件体内取状态并触发静默调度**

L47-49（`const navigate = useNavigate();` 之后）加：

```tsx
  const navigate = useNavigate();

  // 有可用更新时设置菜单显示红点；useUpdater 顺带触发启动后静默检查（全局只调度一次）
  const updateAvailable = useUpdateStore((s) => s.status) === 'available';
  useUpdater();
```

- [ ] **Step 3: 设置菜单项加红点**

L86-95 的 `/setting` 菜单项 `label` 改为：

```tsx
                {
                  key: "/setting",
                  icon: (
                    <span className="anticon" role="img">
                      <IconSettings size="1em" />
                    </span>
                  ),
                  label: (
                    <span className="flex items-center gap-2">
                      {t('setting') || "设置"}
                      {updateAvailable && <Badge status="error" />}
                    </span>
                  ),
                  onClick: () => navigate("/setting"),
                },
```

- [ ] **Step 4: 构建校验**

Run: `cd frontend && bun run build && bun run test`
Expected: 构建成功，既有 vitest 全绿（含新增 4 个用例）。

- [ ] **Step 5: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add frontend/src/layouts/ConsoleLayout.tsx
git commit -m "feat(desktop-ui): 侧边栏设置菜单展示更新红点"
```

---

### Task 10: 中英文案

**Files:**
- Modify: `i18n/zh-CN.json`（末行）
- Modify: `i18n/en-US.json`（末行）

- [ ] **Step 1: 中文文案**

`i18n/zh-CN.json` 末尾把

```json
  "factor_mining_toast_run_deleted": "记录已删除"
}
```

替换为：

```json
  "factor_mining_toast_run_deleted": "记录已删除",
  "update_title": "软件更新",
  "update_current_version": "当前版本",
  "update_latest": "已是最新版本",
  "update_available": "发现新版本 {{version}}",
  "update_checking": "正在检查更新…",
  "update_downloading": "正在下载更新",
  "update_failed": "更新失败",
  "update_check": "检查更新",
  "update_install": "立即更新",
  "update_restart_hint": "安装完成后应用将自动重启",
  "update_notes": "更新说明",
  "update_mirror_label": "更新镜像源（可选，留空仅使用官方源）",
  "update_mirror_placeholder": "https://mirror.example.com/quantcell",
  "update_mirror_save": "保存镜像源",
  "update_mirror_saved": "镜像源已保存",
  "update_notification_hint": "前往 设置 → 通用设置 查看并安装",
  "update_running_confirm_title": "升级会中断运行中的策略",
  "update_running_confirm_content": "当前有 {{count}} 个策略正在运行，升级并重启后将全部中断。确定继续？",
  "update_confirm_ok": "继续升级",
  "update_confirm_cancel": "取消"
}
```

- [ ] **Step 2: 英文文案**

`i18n/en-US.json` 末尾把

```json
  "factor_mining_toast_run_deleted": "Mining run deleted"
}
```

替换为：

```json
  "factor_mining_toast_run_deleted": "Mining run deleted",
  "update_title": "Software Update",
  "update_current_version": "Current version",
  "update_latest": "You're on the latest version",
  "update_available": "New version {{version}} available",
  "update_checking": "Checking for updates…",
  "update_downloading": "Downloading update",
  "update_failed": "Update failed",
  "update_check": "Check for updates",
  "update_install": "Update now",
  "update_restart_hint": "The app restarts automatically after installation",
  "update_notes": "Release notes",
  "update_mirror_label": "Update mirror (optional; leave empty for the official source only)",
  "update_mirror_placeholder": "https://mirror.example.com/quantcell",
  "update_mirror_save": "Save mirror",
  "update_mirror_saved": "Mirror saved",
  "update_notification_hint": "Open Settings → General to review and install",
  "update_running_confirm_title": "Upgrading will interrupt running strategies",
  "update_running_confirm_content": "{{count}} strategies are running and will be interrupted by the restart. Continue?",
  "update_confirm_ok": "Continue",
  "update_confirm_cancel": "Cancel"
}
```

- [ ] **Step 3: 校验 JSON 与构建**

Run:

```bash
cd /Users/liupeng/workspace/quant/QuantCell && python3 -c "import json;[json.load(open(f'i18n/{n}.json')) for n in ('zh-CN','en-US')];print('i18n ok')" && cd frontend && bun run build
```

Expected: `i18n ok`，构建成功。

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add i18n/zh-CN.json i18n/en-US.json
git commit -m "feat(i18n): 补充软件更新中英文案"
```

### Task 11: 发布 manifest 聚合脚本

**Files:**
- Create: `desktop/scripts/aggregate_updater_manifest.py`

- [ ] **Step 1: 写脚本**

创建 `desktop/scripts/aggregate_updater_manifest.py`：

```python
"""聚合各平台 Tauri 更新产物，生成 updater manifest（latest.json / latest-mirror.json）。

用法：
    uv run --with typer python desktop/scripts/aggregate_updater_manifest.py \
        --version 0.2.0 --tag v0.2.0 \
        --input dist --output dist/manifest \
        --mirror-base https://mirror.example.com/quantcell

manifest 结构（Tauri updater v2）：
    {"version": ..., "notes": ..., "pub_date": ..., "platforms": {"<target>": {"signature": ..., "url": ...}}}

镜像版仅把 url 前缀换成 `<mirror-base>/<tag>/`，其余字段与官方版一致。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

REPO_SLUG = "pengwow/QuantCell"

# target -> CI upload-artifact 的 name（download-artifact 不加 merge 时就是目录名）
DEFAULT_PLATFORMS = {
    "darwin-aarch64": "quantcell-desktop-macos-aarch64",
    "darwin-x86_64": "quantcell-desktop-macos-x86_64",
    "windows-x86_64": "quantcell-desktop-windows-x86_64",
    "linux-x86_64": "quantcell-desktop-linux-x86_64",
}

# target -> 候选产物后缀（按优先级）；签名文件固定为「产物同名 + .sig」
ARTIFACT_SUFFIXES = {
    "darwin-aarch64": [".app.tar.gz"],
    "darwin-x86_64": [".app.tar.gz"],
    "windows-x86_64": ["-setup.exe", ".msi"],
    "linux-x86_64": [".AppImage.tar.gz"],
}


def _find_signed_artifact(platform_dir: Path, suffixes: list[str]) -> tuple[Path, Path] | None:
    """按后缀优先级找「产物 + 同名 .sig」，找不到返回 None"""
    for suffix in suffixes:
        for sig in sorted(platform_dir.rglob(f"*{suffix}.sig")):
            artifact = Path(str(sig)[: -len(".sig")])
            if artifact.is_file():
                return artifact, sig
    return None


app = typer.Typer(add_completion=False)


@app.command()
def main(
    version: str = typer.Option(..., help="语义版本号，如 0.2.0"),
    tag: str = typer.Option(..., help="git tag，如 v0.2.0"),
    input_dir: Path = typer.Option(..., help="各平台产物解压根目录"),
    output_dir: Path = typer.Option(..., help="manifest 输出目录"),
    notes: str = typer.Option("", help="更新说明，写入 manifest.notes"),
    mirror_base: str = typer.Option("", help="镜像基址；非空才生成 latest-mirror.json"),
) -> None:
    platforms: dict[str, dict] = {}
    missing: list[str] = []

    for target, dir_name in DEFAULT_PLATFORMS.items():
        platform_dir = input_dir / dir_name
        found = (
            _find_signed_artifact(platform_dir, ARTIFACT_SUFFIXES[target])
            if platform_dir.is_dir()
            else None
        )
        if found is None:
            missing.append(target)
            continue
        artifact, sig = found
        platforms[target] = {
            "signature": sig.read_text(encoding="utf-8").strip(),
            "url": f"https://github.com/{REPO_SLUG}/releases/download/{tag}/{artifact.name}",
        }
        typer.echo(f"[ok] {target}: {artifact.name}")

    if missing:
        typer.echo(f"[error] 缺少平台产物: {', '.join(missing)}", err=True)
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)
    base_manifest = {
        "version": version,
        "notes": notes,
        "pub_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    official_path = output_dir / "latest.json"
    official_path.write_text(
        json.dumps(base_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    typer.echo(f"[ok] 写出 {official_path}")

    if mirror_base.strip():
        mirror_root = f"{mirror_base.strip().rstrip('/')}/{tag}"
        mirror_manifest = json.loads(json.dumps(base_manifest))
        for entry in mirror_manifest["platforms"].values():
            entry["url"] = entry["url"].replace(
                f"https://github.com/{REPO_SLUG}/releases/download/{tag}/",
                f"{mirror_root}/",
            )
        mirror_path = output_dir / "latest-mirror.json"
        mirror_path.write_text(
            json.dumps(mirror_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        typer.echo(f"[ok] 写出 {mirror_path}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: 本地验证脚本（用假产物目录）**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
T=/tmp/qc-manifest-test
mkdir -p "$T"/quantcell-desktop-macos-aarch64/macos "$T"/quantcell-desktop-macos-x86_64/macos \
         "$T"/quantcell-desktop-windows-x86_64/nsis "$T"/quantcell-desktop-linux-x86_64/appimage
touch "$T"/quantcell-desktop-macos-aarch64/macos/QuantCell.app.tar.gz \
      "$T"/quantcell-desktop-macos-x86_64/macos/QuantCell.app.tar.gz \
      "$T"/quantcell-desktop-windows-x86_64/nsis/QuantCell_0.2.0_x64-setup.exe \
      "$T"/quantcell-desktop-linux-x86_64/appimage/QuantCell_0.2.0_amd64.AppImage.tar.gz
printf 'SIG_A' > "$T"/quantcell-desktop-macos-aarch64/macos/QuantCell.app.tar.gz.sig
printf 'SIG_B' > "$T"/quantcell-desktop-macos-x86_64/macos/QuantCell.app.tar.gz.sig
printf 'SIG_W' > "$T"/quantcell-desktop-windows-x86_64/nsis/QuantCell_0.2.0_x64-setup.exe.sig
printf 'SIG_L' > "$T"/quantcell-desktop-linux-x86_64/appimage/QuantCell_0.2.0_amd64.AppImage.tar.gz.sig
uv run --no-project --with typer python desktop/scripts/aggregate_updater_manifest.py \
  --version 0.2.0 --tag v0.2.0 --input "$T" --output "$T/out" \
  --mirror-base https://mirror.example.com/quantcell
python3 -c "import json;m=json.load(open('$T/out/latest-mirror.json'));print(sorted(m['platforms']));print(m['platforms']['windows-x86_64']['url'])"
```

Expected: 输出 4 行 `[ok]`，`latest.json` / `latest-mirror.json` 均生成；末行打印
`['darwin-aarch64', 'darwin-x86_64', 'linux-x86_64', 'windows-x86_64']`
`https://mirror.example.com/quantcell/v0.2.0/QuantCell_0.2.0_x64-setup.exe`

验证完清理临时目录：`mkdir -p /tmp/qc-trash && mv /tmp/qc-manifest-test /tmp/qc-trash/`（仓库规则：不用 rm）。

- [ ] **Step 3: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add desktop/scripts/aggregate_updater_manifest.py
git commit -m "feat(release): 新增 updater manifest 聚合脚本"
```

---

### Task 12: CI 签名、版本 patch 与发布 job

**Files:**
- Modify: `.github/workflows/desktop-build.yml:130-141`

- [ ] **Step 1: 改造打包步骤（版本 patch + 签名）**

把 `Build desktop app (Tauri)` 步骤（L130-133）替换为：

```yaml
      - name: Build desktop app (Tauri)
        shell: bash
        env:
          # 私钥与密码来自仓库 Secrets；未配置时 tauri 会因缺少签名密钥直接失败
          TAURI_SIGNING_PRIVATE_KEY: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}
          TAURI_SIGNING_PRIVATE_KEY_PASSWORD: ${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}
        run: |
          cd desktop
          if [ "${GITHUB_REF_TYPE}" = "tag" ]; then
            VERSION="${GITHUB_REF_NAME#v}"
            echo "打包版本 $VERSION（来自 tag ${GITHUB_REF_NAME}）"
            # --config 内联 JSON 覆盖 tauri.conf.json 的 version，保证 tag 是版本唯一事实源
            bunx @tauri-apps/cli build --config "{\"version\":\"$VERSION\"}"
          else
            # 手动触发：沿用仓库里的 version（用于冒烟，不走发布）
            bunx @tauri-apps/cli build
          fi
```

说明：Windows runner 默认 `pwsh`，该步骤必须显式 `shell: bash`，否则 `${GITHUB_REF_NAME#v}` 语法无效。

- [ ] **Step 2: 新增 release job**

在文件末尾（`build` job 之后）追加：

```yaml
  # 发布：仅 tag 触发；四个平台产物 + updater manifest 一起发到 GitHub Release
  release:
    needs: build
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # 不 merge：保留下载目录名（= artifact name），聚合脚本按平台目录定位产物
      - uses: actions/download-artifact@v4
        with:
          path: dist
          pattern: quantcell-desktop-*

      - name: Setup uv
        uses: astral-sh/setup-uv@v5

      - name: Aggregate updater manifest
        env:
          MIRROR_BASE_URL: ${{ vars.UPDATE_MIRROR_BASE_URL }}
        run: |
          uv run --no-project --with typer python desktop/scripts/aggregate_updater_manifest.py \
            --version "${GITHUB_REF_NAME#v}" \
            --tag "${GITHUB_REF_NAME}" \
            --input dist \
            --output dist/manifest \
            --notes "QuantCell ${GITHUB_REF_NAME}" \
            --mirror-base "$MIRROR_BASE_URL"

      - name: Publish release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ github.ref_name }}
          generate_release_notes: true
          files: |
            dist/**/*.dmg
            dist/**/*.app.tar.gz
            dist/**/*.app.tar.gz.sig
            dist/**/*-setup.exe
            dist/**/*-setup.exe.sig
            dist/**/*.msi
            dist/**/*.msi.sig
            dist/**/*.deb
            dist/**/*.AppImage
            dist/**/*.AppImage.tar.gz
            dist/**/*.AppImage.tar.gz.sig
            dist/manifest/latest.json
            dist/manifest/latest-mirror.json
```

`MIRROR_BASE_URL` 为空时脚本只出 `latest.json`；`softprops/action-gh-release` 默认 `fail_on_unmatched_files: false`，缺 `latest-mirror.json` 只告警不失败。

- [ ] **Step 3: 语法校验**

Run:

```bash
cd /Users/liupeng/workspace/quant/QuantCell && python3 -c "import yaml,sys;d=yaml.safe_load(open('.github/workflows/desktop-build.yml'));print(sorted(d['jobs']))"
```

Expected: `['build', 'ci-checks', 'release']`。若本机无 pyyaml，用 `uv run --with pyyaml python -c "..."` 重跑同一条命令。

- [ ] **Step 4: 提交**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add .github/workflows/desktop-build.yml
git commit -m "ci(release): tag 构建注入版本号并发布 updater manifest"
```

---

### Task 13: 端到端冒烟与全量验证

**Files:** 无代码改动（仅验证）

- [ ] **Step 1: 后端全量相关单测**

Run:

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend && uv run pytest tests/unit/test_app_version.py tests/unit/test_plugin_manager.py tests/unit/test_plugins.py -q
```

Expected: 全 passed。

- [ ] **Step 2: Rust 单测**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/desktop/src-tauri && cargo test`
Expected: 全 passed（config 模块 5 个用例 + 既有）。

- [ ] **Step 3: 前端测试与构建**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/frontend && bun run test && bun run build`
Expected: vitest 全绿，`tsc -b && vite build` 成功。

- [ ] **Step 4: 本地双版本冒烟（macOS Apple Silicon 示例）**

前提：Task 0 的密钥已生成；release 构建**拒绝** http endpoint（`InsecureTransportProtocol`），所以冒烟必须用 `--debug`。

```bash
# 版本 A：0.1.0（旧版，充当被升级方）
cd /Users/liupeng/workspace/quant/QuantCell/desktop
export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.tauri/quantcell.key)"
export TAURI_SIGNING_PRIVATE_KEY_PASSWORD='<Task 0 设置的密码>'
bunx @tauri-apps/cli build --debug --config '{"version":"0.1.0"}'
mkdir -p /tmp/qc-update-e2e/v1
cp -R src-tauri/target/debug/bundle/macos/QuantCell.app /tmp/qc-update-e2e/v1/

# 版本 B：0.2.0（新版，充当更新源）
bunx @tauri-apps/cli build --debug --config '{"version":"0.2.0"}'
mkdir -p /tmp/qc-update-e2e/mirror/v0.2.0
cp src-tauri/target/debug/bundle/macos/QuantCell.app.tar.gz \
   src-tauri/target/debug/bundle/macos/QuantCell.app.tar.gz.sig \
   /tmp/qc-update-e2e/mirror/v0.2.0/
```

生成假镜像 manifest 并起静态服务：

```bash
python3 -c "import json,pathlib;r=pathlib.Path('/tmp/qc-update-e2e/mirror');sig=(r/'v0.2.0/QuantCell.app.tar.gz.sig').read_text().strip();json.dump({'version':'0.2.0','notes':'e2e smoke','pub_date':'2026-10-28T00:00:00Z','platforms':{'darwin-aarch64':{'signature':sig,'url':'http://127.0.0.1:8787/v0.2.0/QuantCell.app.tar.gz'}}},open(r/'latest-mirror.json','w'),ensure_ascii=False,indent=2);print('manifest written')"
cd /tmp/qc-update-e2e/mirror && python3 -m http.server 8787
```

另开终端，把旧版放到可写位置并启动（macOS 会原地替换 .app，放 `/tmp` 可能被 Gatekeeper 拦，放用户目录更稳）：

```bash
cp -R /tmp/qc-update-e2e/v1/QuantCell.app ~/Desktop/QuantCell-e2e.app && open ~/Desktop/QuantCell-e2e.app
```

操作期待结果：

1. 打开「设置 → 通用设置」，软件更新卡显示当前版本 `0.1.0`。
2. 镜像源填 `http://127.0.0.1:8787`，保存成功。
3. 点「检查更新」→ 出现 `发现新版本 0.2.0`，右侧「立即更新」由禁用变可用。
4. 点「立即更新」→ 进度条推进 → 应用自动重启。
5. 重启后回到同一页面：当前版本为 `0.2.0`，状态回到「已是最新版本」。

负向验证（同一套环境，逐条改完再点检查）：

6. **验签失败不破坏旧版**：把 `latest-mirror.json` 里 `signature` 的末位字符改掉 → 检查仍能命中 0.2.0（manifest 本身不验签）→ 点「立即更新」→ 提示「下载安装失败」，应用仍是 0.1.0 且可正常使用。
7. **镜像不可达回落官方源**：镜像改填 `http://127.0.0.1:9`（无服务）→ 点检查不报「更新器初始化失败」，而是落到官方源（有网时可能查到线上最新版；断网时提示检查失败）。
8. **24h 节流生效**：在 devtools 删除 localStorage 的 `update_last_check_ms` → 重启应用 → 8s 后自动检查并把该 key 写回时间戳；再次重启 → 8s 后不再自动请求。

冒烟结束清理：`mkdir -p /tmp/qc-trash && mv ~/Desktop/QuantCell-e2e.app /tmp/qc-trash/ && mv /tmp/qc-update-e2e /tmp/qc-trash/`。

- [ ] **Step 5: 提交（若冒烟过程中改过代码）**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git status   # 期望 clean；有改动则按实际改动内容单独提交，不要混入无关文件
```

---

## 与设计文档的差异（落地取舍，执行时以本表为准）

| # | 设计文档（`2026-10-28-desktop-auto-update-design.md`） | 本计划 | 原因 |
|---|--------------------------------------------------------|--------|------|
| 1 | `build-backend.sh` 注入 `QUANTCELL_VERSION` 打进 PyInstaller 包 | Rust `spawn_sidecar` 运行时注入 env | 环境变量是**运行时**读取，构建期注入不会写进二进制；运行时注入天然覆盖桌面端所有启动路径，且 CI 无需改 sidecar 打包脚本 |
| 2 | 3 个 command：`update_endpoints` / `update_check` / `update_install` | 4 个：`update_get_mirror` / `update_set_mirror` / `update_check` / `update_install` | 镜像基址要可读可写（设计里只说了读）；不做渠道可达性探测——检查失败的报错信息已足以定位是网络还是镜像配置问题 |
| 3 | 更新卡片落在 `GeneralSettingsPage.tsx`（主入口） | 卡片位置相同；组件在 `pages/setting/SoftwareUpdateCard.tsx`，bridge/store/hook 在 `src/desktop/` | 与设计的主入口一致；`src/desktop/` 已是桌面专属模块聚集地（`bridge.ts` / `env.ts` / `splash.ts`），比新建 `src/api/updateApi.ts` 更贴合现状 |
| 4 | 安装完成后由前端 prompt 重启 | Rust 安装成功后直接 `app.process().restart()` | 少一次交互。重启走现有退出链路（`RunEvent::Exit` → `backend::signal_stop` 杀 sidecar 进程树），不会残留后端；中断风险由安装前的运行中策略二次确认兜住 |
| 5 | 前端补 `SoftwareUpdateCard` 渲染/状态测试（mock invoke） | 只测 `shouldCheck` 纯函数，卡片状态流转由 E2E 冒烟覆盖 | vitest 当前是 `environment: 'node'`，组件测试需引入 jsdom + @testing-library 两个新 devDependency，成本与收益不匹配（ponytail/YAGNI） |
| 6 | manifest `notes` 取自 tag 的 Release body | `--notes "QuantCell ${tag}"` | tag push 时还没有 Release 对象可读；正文更新说明由 `generate_release_notes` 生成在 Release 页面，manifest 的 notes 只作标题性提示 |

---

## 仓库外手动步骤（发布前必须完成，不属于代码任务）

1. **签名密钥**：Task 0 已生成 `~/.tauri/quantcell.key` / `.key.pub`，私钥**绝不入库**、不提交到任何仓库。
2. **GitHub Secrets**（Settings → Secrets and variables → Actions）：
   - `TAURI_SIGNING_PRIVATE_KEY`：`~/.tauri/quantcell.key` 文件全文（含 `untrusted comment:` 行）。
   - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`：生成密钥时设置的密码。
3. **GitHub Variable**（可选）：`UPDATE_MIRROR_BASE_URL`，如 `https://mirror.example.com/quantcell`。镜像站目录约定：
   - `{base}/latest-mirror.json` —— Rust 侧固定拼这个文件名；
   - `{base}/{tag}/<安装包与 .sig>` —— manifest 里的 url 指向这里。
4. **本地打包**：任何时候在本机跑 `bunx @tauri-apps/cli build` 都必须先导出
   `TAURI_SIGNING_PRIVATE_KEY` 与 `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`，否则 `createUpdaterArtifacts` 会因缺密钥失败。
5. **镜像同步**：发布后把 `latest.json` 的 `platforms` 条目与对应安装包、`.sig` 同步到镜像站；镜像站不可达时 Rust 会落到官方源（endpoints 顺序保证），不会阻断升级。

## 已知边界（执行时不要试图"顺手解决"）

- 本方案只覆盖 **stable** 通道：官方 manifest 固定取 `releases/latest/download/latest.json`，预发布版本不会命中。
- 只做**整包更新**：不涉及 sidecar 增量、uv 依赖热更新。
- 升级不可回滚：装完即替换安装包；如需回滚只能重装旧版（本计划不实现）。
- **首次发布冷启动**：已安装的旧版（不含 updater 的 v0.1.0）必须手动下载新版安装一次，之后才进入自动升级轨道。
- **平台热更能力**：Windows 用 NSIS（`-setup.exe`），MSI 不参与热更；Linux 用 `.AppImage.tar.gz`，deb 包用户需手动下载新版本。
- `dev` 版本（源码直跑）走插件兼容校验时一律放行，这是有意为之（开发版没有语义版本）。
- 升级期间不并发保护 sidecar 正在执行的回测：安装前只检查「运行中策略数」，不检查回测队列。
