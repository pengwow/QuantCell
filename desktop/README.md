# QuantCell Desktop (Tauri)

桌面客户端：Rust 壳 + React UI + PyInstaller 打包的 FastAPI sidecar。

## 环境要求

- Rust 工具链（stable）、Xcode Command Line Tools
- bun
- backend/.venv（在仓库 backend/ 下执行过 `uv sync`）

## 开发

1. 构建 sidecar：`bash desktop/scripts/build-backend.sh`
2. 安装依赖：`cd desktop/ui && bun install`
3. 启动：`cd desktop && ./ui/node_modules/.bin/tauri dev`
   （tauri CLI 只在 cwd 及浅子目录发现 src-tauri，而本项目 src-tauri 与 ui 是兄弟目录；beforeDevCommand 仍会在 ui 目录执行。）

## 打包

`cd desktop && ./ui/node_modules/.bin/tauri build`
产物：`src-tauri/target/release/bundle/`（dmg / .app）。

## 后端模式

- local（默认）：应用自动在 127.0.0.1 临时端口拉起 sidecar，数据写入
  `~/Library/Application Support/top.quantcell.desktop/`。
- remote：设置中填入远程 API 地址，应用不再启动本机进程。

已知限制：窗口关闭与正常退出（Cmd+Q）均会同步灭杀 sidecar 进程树；SIGKILL/掉电等无法走退出流程的场景仍可能留孤儿，后续通过 sidecar 父进程探活兜底。
