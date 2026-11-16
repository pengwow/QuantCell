---
title: Installation
description: QuantCell installation guide — prerequisites, one-click and manual setup
---

# Installation

## Prerequisites

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.14 | backend runtime |
| uv | latest | Python package manager (replaces pip) |
| bun | latest | frontend package manager (replaces npm) |
| Rust toolchain | stable | only for desktop development (Tauri 2) |
| Git | latest | source checkout |

## One-click install & start

```bash
git clone https://github.com/pengwow/quantcell.git
cd quantcell
bash scripts/install.sh --minimal
```

`scripts/install.sh` supports three modes:

| Mode | Description |
|------|-------------|
| `--minimal` | minimal dependencies, ready to run |
| `--full` | full dependency set (RL training, research, and all optional components) |
| `--extra <pkg>` | additionally install a named optional dependency group |

The script installs the uv / bun toolchains, backend and frontend dependencies,
and then starts both services.

You can also manage dev services via the Makefile:

```bash
make dev-start      # start backend uvicorn + frontend vite (daemonized)
make dev-status     # check running status
make dev-stop       # stop services
make dev-restart    # restart services
```

## Manual installation

### Backend

```bash
cd backend
uv sync                          # install deps and generate the quantcell CLI entry
uv run python init_db.py         # initialize the database
```

> `uv sync` generates the `quantcell` executable in the Python environment's
> bin directory (e.g. `backend/.venv/bin/`); it can then be used from any directory.

### Frontend

```bash
cd frontend
bun install
```

## Start services

### Backend

```bash
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

Once running:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **Health check**: `http://localhost:8000/health`

### Frontend

```bash
cd frontend
bun run dev
```

In dev mode the frontend proxies automatically to the backend on port `8000`.

!!! note "Production"
    For production builds use `make frontend-build` (runs `tsc -b && vite build`)
    and deploy the artifacts to any static server, or use the desktop client
    (see [Desktop client](../user-guide/desktop.md)).

## Desktop

The desktop build ships its own backend (PyInstaller sidecar) and needs no
local Python environment. Download installers from GitHub Actions artifacts
(see [Desktop client](../user-guide/desktop.md)).

## Upgrade

```bash
git pull
cd backend && uv sync          # update backend deps
cd frontend && bun install     # update frontend deps
uv run python init_db.py       # migrates automatically if the schema changed
```

Database schema upgrades can also be run explicitly:

```bash
quantcell migrate -y           # SQLite schema upgrade (auto-confirm)
```
