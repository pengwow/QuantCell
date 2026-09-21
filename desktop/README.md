# QuantCell Desktop (Tauri)

桌面客户端：Rust 壳 + React UI + PyInstaller 打包的 FastAPI sidecar。

## 环境要求

- Rust 工具链（stable）、Xcode Command Line Tools
- bun
- backend/.venv（在仓库 backend/ 下执行过 `uv sync`）

## 开发

1. 构建 sidecar：`bash desktop/scripts/build-backend.sh`
2. 启动：`cd desktop/ui && bun install && bun run tauri dev`

## 打包

`cd desktop/ui && bun run tauri build`
产物：`src-tauri/target/release/bundle/`（dmg / .app）。

## 后端模式

- local（默认）：应用自动在 127.0.0.1 临时端口拉起 sidecar，数据写入
  `~/Library/Application Support/top.quantcell.desktop/`。
- remote：设置中填入远程 API 地址，应用不再启动本机进程。

已知限制：SIGKILL/掉电等非正常退出时 sidecar 可能成为孤儿进程（窗口关闭与
正常退出均已保证回收）；后续版本通过父进程探活机制兜底。
