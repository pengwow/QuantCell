---
title: 安装
description: QuantCell 安装指南 — 环境要求、一键安装与手动安装
---

# 安装

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.14 | 后端运行时 |
| uv | latest | Python 包管理器（替代 pip） |
| bun | latest | 前端包管理器（替代 npm） |
| Rust 工具链 | stable | 仅桌面端开发需要（Tauri 2） |
| Git | latest | 源码获取 |

## 一键安装与启动

```bash
git clone https://github.com/pengwow/quantcell.git
cd quantcell
bash scripts/install.sh --minimal
```

`scripts/install.sh` 支持三种模式：

| 模式 | 说明 |
|------|------|
| `--minimal` | 最小化依赖，开箱即用 |
| `--full` | 完整依赖（含 RL 训练、研究等全部可选组件） |
| `--extra <pkg>` | 追加安装指定可选依赖组 |

脚本会自动安装 uv / bun 工具链、后端依赖、前端依赖，并启动前后端服务。

也可以通过 Makefile 管理 dev 服务：

```bash
make dev-start      # 启动后端 uvicorn + 前端 vite（后台驻留）
make dev-status     # 查看运行状态
make dev-stop       # 停止服务
make dev-restart    # 重启服务
```

## 手动安装

### 后端

```bash
cd backend
uv sync                          # 安装依赖并生成 quantcell CLI 入口
uv run python init_db.py         # 初始化数据库
```

> `uv sync` 会在 Python 环境的 bin 目录（如 `backend/.venv/bin/`）生成
> `quantcell` 可执行命令，之后可在任意目录直接使用。

### 前端

```bash
cd frontend
bun install
```

## 启动服务

### 后端

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

启动后访问：

- **Swagger UI**：`http://localhost:8000/docs`
- **ReDoc**：`http://localhost:8000/redoc`
- **健康检查**：`http://localhost:8000/health`

### 前端

```bash
cd frontend
bun run dev
```

开发模式下前端自动代理到后端 `8000` 端口。

!!! note "生产环境"
    生产构建请使用 `make frontend-build`（执行 `tsc -b && vite build`），
    产物部署到任意静态服务器或直接使用桌面端（见[桌面客户端](../user-guide/desktop.md)）。

## 桌面端

桌面版本地自带后端（PyInstaller sidecar），无需单独安装 Python 环境。安装包从
GitHub Actions artifacts 下载（见[桌面客户端](../user-guide/desktop.md)）。

## 升级

```bash
git pull
cd backend && uv sync          # 更新后端依赖
cd frontend && bun install     # 更新前端依赖
uv run python init_db.py       # 数据库 schema 如有升级，自动迁移
```

数据库结构变更也可通过内置命令完成：

```bash
quantcell migrate -y           # SQLite schema 升级（自动确认）
```
