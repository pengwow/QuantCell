---
title: 桌面客户端
description: Tauri 2 + PyInstaller sidecar 桌面端 — 安装包、运行模式与打包
---

# 桌面客户端

## 架构

桌面端由两层组成：

- **Tauri 2 壳**：复用仓库同一套 `frontend/` React 代码，跨平台窗口与系统托盘
- **backend sidecar**：本地 `backend`（FastAPI + Rust 内核）通过 PyInstaller 打包为
  单文件二进制，随桌面端自动拉起与关闭

```
QuantCell.app
├── Tauri 壳（React 前端）
└── quantcell-backend（sidecar 二进制，PyInstaller onefile）
        └── 内嵌 FastAPI + Rust 内核 + DuckDB
```

## 运行模式

| 模式 | 说明 |
|------|------|
| `local` | 使用内嵌 sidecar 后端，免登录，数据全在本地 |
| `remote` | 连接远端 QuantCell 服务，适合部署在云服务器的团队场景 |

## 安装包

| 平台 | 架构 | 安装包 |
|------|------|--------|
| macOS（Apple 芯片） | aarch64 | `QuantCell_<ver>_aarch64.dmg` |
| macOS（Intel） | x86_64 | `QuantCell_<ver>_x64.dmg` |
| Windows | x86_64 | `QuantCell_<ver>_x64.msi` / `.exe` |
| Linux | x86_64 | `quantcell_<ver>_amd64.deb` / `.AppImage` |

**下载位置**：GitHub Actions artifacts（`quantcell-desktop-*`），tag `v*` 触发时自动生成。

**未签名提示**：

- macOS 首次打开：右键 → 打开
- Windows：提示未知发布者时点击「仍要运行」

## 本地开发

```bash
make desktop-build   # Tauri release build（自动先构建前端）
make desktop-run     # 打开 .app
make desktop         # clean → build → run（最常用）
make desktop-kill    # 停止桌面端残留进程
make desktop-clean   # kill + 清 Rust target + 前端缓存
```

桌面端开发需要 Rust 工具链（Tauri 2）。详细说明见仓库
[desktop/README.md](https://github.com/pengwow/quantcell/blob/main/desktop/README.md)。

构建细节（sidecar 打包、externalBin 配置）由以下文件驱动：

- `desktop/scripts/build-backend.sh` —— PyInstaller 打包 backend
- `desktop/src-tauri/tauri.conf.json` —— sidecar 声明与打包配置
- `.github/workflows/desktop-build.yml` —— CI 打包（workflow_dispatch / v* tag 触发）
