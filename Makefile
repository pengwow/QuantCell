# QuantCell 统一构建入口
# GNU Make，macOS 自带。用法：`make <target>`

SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

# ============================================================
# 后端（Python / uv）
# ============================================================

.PHONY: backend-install backend-test backend-lint backend-fmt backend-typecheck

backend-install:
	cd backend && uv sync

backend-test:
	cd backend && uv run pytest tests/ -v

backend-lint:
	cd backend && uv run ruff check .

backend-fmt:
	cd backend && uv run ruff format .

backend-typecheck:
	cd backend && uv run ruff check --fix . && uv run ruff format .

# ============================================================
# 前端（bun + vite）
# ============================================================

.PHONY: frontend-install frontend-build frontend-test frontend-lint frontend-dev

frontend-install:
	cd frontend && bun install

frontend-build:
	cd frontend && bun run build

frontend-test:
	cd frontend && bun run test

frontend-lint:
	cd frontend && bun run lint

frontend-dev:
	cd frontend && bun run dev

# ============================================================
# 桌面端（Tauri 2 / Rust）
# ============================================================

DESKTOP_DIR := desktop
APP_BUNDLE := $(DESKTOP_DIR)/src-tauri/target/release/bundle/macos/QuantCell.app

.PHONY: desktop-kill desktop-clean desktop-build desktop-run desktop

desktop-kill:
	# 杀掉残留进程，避免 port 占用或文件锁
	pkill -f "quantcell-desktop" 2>/dev/null || true
	pkill -f "quantcell-backend" 2>/dev/null || true
	sleep 1

desktop-clean: desktop-kill
	rm -rf $(DESKTOP_DIR)/src-tauri/target/release
	rm -rf frontend/dist frontend/node_modules/.vite

desktop-build:
	cd $(DESKTOP_DIR) && bunx @tauri-apps/cli build
	@echo ""
	@echo "=== 构建产物 ==="
	@echo "APP:  $(APP_BUNDLE)"
	@test -d $(APP_BUNDLE) || { echo "ERROR: .app 未生成"; exit 1; }

desktop-run:
	open $(APP_BUNDLE)

# 日常最常用：clean → build → run
desktop: desktop-clean desktop-build desktop-run

# ============================================================
# 开发服务（后端 uvicorn + 前端 vite 后台驻留，委托给 scripts/install.sh）
# ============================================================

.PHONY: dev-start dev-stop dev-status dev-restart

dev-start:
	./scripts/install.sh --start

dev-stop:
	./scripts/install.sh --stop

dev-status:
	./scripts/install.sh --status

dev-restart:
	./scripts/install.sh --restart

# ============================================================
# 全链路
# ============================================================

.PHONY: all clean test lint

all: backend-install frontend-install desktop-build

test: backend-test frontend-test

lint: backend-lint frontend-lint

clean:
	rm -rf backend/.venv
	rm -rf frontend/dist frontend/node_modules/.vite
	rm -rf $(DESKTOP_DIR)/src-tauri/target

# ============================================================
# 帮助
# ============================================================

.PHONY: help
help:
	@echo "QuantCell Makefile 可用 target:"
	@echo "	=== 后端 (backend)==="
	@echo "  make backend-install     uv sync"
	@echo "  make backend-test        pytest"
	@echo "  make backend-lint        ruff check"
	@echo "  make backend-fmt         ruff format"
	@echo "  make backend-typecheck   ruff check --fix + format"
	@echo "	=== 前端 (frontend)==="
	@echo "  make frontend-install    bun install"
	@echo "  make frontend-build      tsc -b && vite build"
	@echo "  make frontend-test       vitest run"
	@echo "  make frontend-lint       eslint"
	@echo "  make frontend-dev        vite dev server"
	@echo "	=== 桌面端 (desktop)==="
	@echo "  make desktop-kill        停止桌面端残留进程"
	@echo "  make desktop-clean       kill + 清 Rust target/release + 前端缓存"
	@echo "  make desktop-build       Tauri release build（含前端自动构建）"
	@echo "  make desktop-run         open .app"
	@echo "  make desktop             clean → build → run（最常用）"
	@echo "	=== 开发服务 (dev)==="
	@echo "  make dev-start           启动后端 uvicorn + 前端 vite（后台驻留）"
	@echo "  make dev-stop            停止开发服务"
	@echo "  make dev-status          查看开发服务状态"
	@echo "  make dev-restart         重启开发服务"
	@echo "	=== 全链路 (all)==="
	@echo "  make all                 backend-install + frontend-install + desktop-build"
	@echo "  make test                backend-test + frontend-test"
	@echo "  make lint                backend-lint + frontend-lint"
	@echo "  make clean               清所有缓存（.venv / dist / target）"
