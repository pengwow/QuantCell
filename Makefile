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

# CI 同款（只跑 CI 覆盖的三个目录，比全量快）
backend-ci-test:
	cd backend && uv run pytest tests/unit/backtest tests/conformance tests/integration -q

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
	# 全量清理：release + debug 两套 profile 缓存一起删
	rm -rf $(DESKTOP_DIR)/src-tauri/target
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

# 决策模型（System 1 · Laya）本地服务，委托给 scripts/local_model_servers/start_laya.sh
.PHONY: laya-start laya-stop laya-status laya-restart

laya-start:
	./scripts/local_model_servers/start_laya.sh start

laya-stop:
	./scripts/local_model_servers/start_laya.sh stop

laya-status:
	./scripts/local_model_servers/start_laya.sh status

laya-restart:
	./scripts/local_model_servers/start_laya.sh restart

# ============================================================
# 文档（mkdocs-material，中英双语 → site/zh + site/en + 根重定向）
# ============================================================

# 统一通过 uv 临时环境运行 mkdocs，不污染系统 Python，也无需单独的 docs venv
DOCS_RUN := uv run --no-project --with-requirements requirements-docs.txt

.PHONY: docs-install docs-serve docs-serve-en docs-build docs-build-en docs-build-all docs-validate docs-clean

# 预热文档依赖缓存（首次可跑一次，后续 serve/build 直接走缓存）
docs-install:
	$(DOCS_RUN) python -c "import mkdocs; print('mkdocs ready:', mkdocs.__version__)"

docs-serve:
	$(DOCS_RUN) python -m mkdocs serve

docs-serve-en:
	$(DOCS_RUN) python -m mkdocs serve -f mkdocs-en.yml -a 127.0.0.1:8001

docs-build:
	$(DOCS_RUN) python -m mkdocs build --strict

docs-build-en:
	$(DOCS_RUN) python -m mkdocs build -f mkdocs-en.yml --strict

# 顺序：zh → en → 根重定向页。mkdocs 只清理各自 site_dir（site/zh、site/en），
# 所以最后写 site/index.html 不会被清掉
docs-build-all: docs-build docs-build-en
	printf '%s\n' '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=zh/"><link rel="canonical" href="zh/"><title>QuantCell Docs</title></head><body>Redirecting to <a href="zh/">QuantCell 文档（中文）</a> / <a href="en/">QuantCell docs (English)</a></body></html>' > site/index.html

docs-validate: docs-build-all
	@echo "==> docs build passed (--strict, zh + en + root redirect)"

docs-clean:
	rm -rf site/

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
# 版本（VERSION 单源 + 一键体检 / 落位）
# ============================================================

.PHONY: version
version:
	uv run --no-project --with typer python scripts/sync_version.py $(if $(v),--set $(v))

# ============================================================
# 帮助
# ============================================================

.PHONY: help
help:
	@echo "QuantCell Makefile 可用 target:"
	@echo "	=== 后端 (backend)==="
	@echo "  make backend-install     uv sync"
	@echo "  make backend-test        pytest（全量 tests/）"
	@echo "  make backend-ci-test     pytest（CI 同款：backtest + conformance + integration）"
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
	@echo "  make desktop-clean       kill + 清整个 Rust target + 前端缓存"
	@echo "  make desktop-build       Tauri release build（含前端自动构建）"
	@echo "  make desktop-run         open .app"
	@echo "  make desktop             clean → build → run（最常用）"
	@echo "	=== 开发服务 (dev)==="
	@echo "  make dev-start           启动后端 uvicorn + 前端 vite（后台驻留）"
	@echo "  make dev-stop            停止开发服务"
	@echo "  make dev-status          查看开发服务状态"
	@echo "  make dev-restart         重启开发服务"
	@echo "	=== 决策模型 (laya)==="
	@echo "  make laya-start          启动本地决策模型服务（System 1，127.0.0.1:8010）"
	@echo "  make laya-stop           停止决策模型服务"
	@echo "  make laya-status         查看决策模型服务状态"
	@echo "  make laya-restart        重启决策模型服务"
	@echo "	=== 文档 (docs)==="
	@echo "  make docs-install        预热 mkdocs 依赖（uv 临时环境）"
	@echo "  make docs-serve          本地预览中文站 http://localhost:8000"
	@echo "  make docs-serve-en       本地预览英文站 http://127.0.0.1:8001"
	@echo "  make docs-build          构建中文站 → site/zh"
	@echo "  make docs-build-en       构建英文站 → site/en"
	@echo "  make docs-build-all      zh + en + 根重定向页 → site/"
	@echo "  make docs-validate       全量严格构建（--strict）"
	@echo "  make docs-clean          清理 site/"
	@echo "	=== 版本 (version)==="
	@echo "  make version             体检：VERSION 与各处版本声明是否一致（不一致 exit 1）"
	@echo "  make version v=0.0.1     落位：写 VERSION + 4 处声明 + 刷新 uv.lock / Cargo.lock"
	@echo "	=== 全链路 (all)==="
	@echo "  make all                 backend-install + frontend-install + desktop-build"
	@echo "  make test                backend-test + frontend-test"
	@echo "  make lint                backend-lint + frontend-lint"
	@echo "  make clean               清所有缓存（.venv / dist / target）"
