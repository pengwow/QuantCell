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
# torch / stable_baselines3 在后端为函数内懒加载，M1 不打入，控制体积
uv run --with pyinstaller pyinstaller \
  --noconfirm --clean --onefile --name quantcell-backend \
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
  desktop_entry.py
# 注意：--collect-all 每次只接受一个包名，必须逐包重复该 flag

mkdir -p "$BIN_DIR"
mv -f "$BACKEND_DIR/dist/quantcell-backend" "$BIN_DIR/quantcell-backend-$TRIPLE"
chmod +x "$BIN_DIR/quantcell-backend-$TRIPLE"
echo ">> sidecar 已生成: $BIN_DIR/quantcell-backend-$TRIPLE"
