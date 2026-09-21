#!/usr/bin/env bash
# 把 backend/ 打包成 Tauri sidecar 单文件可执行，并按 target triple 落位到
# desktop/src-tauri/binaries/quantcell-backend-<triple>（Tauri externalBin 约定）。
# 用法: bash desktop/scripts/build-backend.sh [target-triple]
set -euo pipefail

TRIPLE="${1:-$(rustc -vV | sed -n 's/host: //p')}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
BIN_DIR="$REPO_ROOT/desktop/src-tauri/binaries"

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo ">> backend/.venv 不存在，先执行 uv sync" >&2
  exit 1
fi

cd "$BACKEND_DIR"

# pyinstaller 用 uv --with 临时引入，不写入 backend/pyproject.toml
# 注意：torch 虽在业务代码中懒加载，但经 axon_quant 依赖链被静态打入，
# 当前 onefile 产物约 430MB、冷启动自解压约 1 分钟；瘦身（--exclude-module
# torch/stable_baselines3 或改 onedir+resources）作为后续优化任务
# backend 以 PEP 660 editable 方式安装（__editable__ finder 绝对路径映射），
# PyInstaller 的 modulegraph 无法透过该 finder 解析本地包，必须显式把 backend
# 目录（即当前目录）加入模块搜索路径，否则冻结产物运行时 ModuleNotFoundError
uv run --with pyinstaller pyinstaller \
  --noconfirm --clean --onefile --name quantcell-backend \
  --paths . \
  --add-data "alembic:alembic" \
  --add-data "ai_model:ai_model" \
  --collect-all axon_quant \
  --collect-all duckdb \
  --collect-all pyarrow \
  --collect-all zmq \
  --collect-all ccxt \
  --collect-all statsmodels \
  --collect-all gymnasium \
  --collect-submodules uvicorn \
  `# 这 5 个模型模块由 collector.db.database._import_all_models 用 importlib.import_module 动态导入，静态分析不可见，需显式收集` \
  --hidden-import strategy.models \
  --hidden-import worker.models \
  --hidden-import collector.db.models \
  --hidden-import indicators.models \
  --hidden-import share.models \
  `# tomli / mypy / charset_normalizer 在 py3.14 wheel 中以 mypyc 编译，运行时支撑模块是顶层 <hash>__mypyc.so（so 内生成 import，静态分析扫不到）；hash 随这些包版本变化，升级 uv.lock 后需同步更新` \
  --hidden-import ddc459050edb75a05942__mypyc \
  --hidden-import 08ae81f72d5a2b5fa9e0__mypyc \
  --hidden-import 81d243bd2c585b0f4821__mypyc \
  desktop_entry.py
# 注意：--collect-all 每次只接受一个包名，必须逐包重复该 flag

mkdir -p "$BIN_DIR"
mv -f "$BACKEND_DIR/dist/quantcell-backend" "$BIN_DIR/quantcell-backend-$TRIPLE"
chmod +x "$BIN_DIR/quantcell-backend-$TRIPLE"
echo ">> sidecar 已生成: $BIN_DIR/quantcell-backend-$TRIPLE"
