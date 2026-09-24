# QuantCell Desktop (Tauri)

桌面客户端：Rust 壳 + 复用仓库 `frontend/` 的 React 应用 + PyInstaller 打包的 FastAPI sidecar。

Web 版与桌面版共用 `frontend/` 同一份代码，仅在 Tauri 壳内激活 `frontend/src/desktop/` 薄适配层
（sidecar 引导、动态端口网络重写、local 免登录、崩溃遮罩、后端模式设置）。

## 环境要求

- Rust 工具链（stable）、Xcode Command Line Tools
- bun
- backend/.venv（在仓库 backend/ 下执行过 `uv sync`）

## 开发

前端复用仓库根目录的 `frontend/` 工程（Vite 固定 5173，strictPort）：

```bash
# 一条命令即可：beforeDevCommand 会自动在 frontend 目录起 Vite dev server
cd desktop && bunx @tauri-apps/cli dev
```

也可分两个终端：`cd frontend && bun run dev`，再 `cd desktop && bunx @tauri-apps/cli dev`。

## CI 打包与发布

`.github/workflows/desktop-build.yml` 一键构建 macOS / Windows / Linux 三平台安装包。

**触发**：手动（GitHub → Actions → desktop-build → Run workflow）或打版本 tag：

```bash
git tag v0.1.0 && git push origin v0.1.0
```

**产物**：tag / 手动触发后进入 Actions 运行页 → Artifacts → `quantcell-desktop-*`，含
macOS `.dmg`、Windows `.msi`+`.exe`（nsis）、Linux `.deb`+`.AppImage`。

**按架构选择**：macOS 分 Apple 芯片（aarch64）与 Intel（x86_64）两个独立 job，各出一份 dmg；
Windows / Linux 均为 x86_64。CPU 型号（如 Intel/AMD、M1/M2）无需区分——同一指令集下所有型号
可运行同一安装包；PyInstaller 无法交叉编译，故各架构包在对应架构的 runner 上分别构建。

**未签名说明**（暂未配置代码签名 / 公证）：
- macOS：首次打开提示「无法验证开发者」→ 右键应用 →「打开」；或 `xattr -dr com.apple.quarantine` 后双击
- Windows：SmartScreen 提示 →「更多信息」→「仍要运行」
- 签名 / 公证为后续待办，需 workflow secrets 配置 Apple Developer / Windows 证书

**CI 内构建流程**：checkout → Linux 系统依赖（仅 ubuntu）→ rust/bun/uv 工具链 →
四层缓存（cargo / uv / pyinstaller / sidecar 产物）→ `bash desktop/scripts/build-backend.sh <triple>`
→ `bunx @tauri-apps/cli build`（自动执行 beforeBuildCommand `cd ../frontend && bun install && bun run build`）
→ upload artifact。sidecar 二进制命中缓存（key: backend/uv.lock + pyproject.toml + build 脚本 hash）时跳过 PyInstaller。

## 打包

```bash
bash desktop/scripts/build-backend.sh          # 先打 sidecar（约 3-5 分钟）
cd desktop && bunx @tauri-apps/cli build       # 自动 bun install + build frontend
```

产物：`src-tauri/target/release/bundle/`（dmg / .app）。

## 后端模式

- local（默认）：应用自动在 127.0.0.1 临时端口拉起 sidecar，local 模式免登录，
  数据写入 `~/Library/Application Support/top.quantcell.desktop/`。
- remote：设置（设置页 →「桌面后端」，仅桌面壳内可见）填入远程 API 地址后，
  应用停止本机 sidecar，界面走正常登录鉴权。

已知限制：onefile sidecar 首次冷启动自解压约 1 分钟（torch 被静态打入，待瘦身）；
窗口关闭与正常退出（Cmd+Q）均会同步灭杀 sidecar 进程树；SIGKILL/掉电等无法走退出
流程的场景仍可能留孤儿，后续通过 sidecar 父进程探活兜底。
