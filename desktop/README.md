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
