#!/usr/bin/env bash
# 把 backend/ 打包成 Tauri bundle resource（PyInstaller --onedir 整目录），并落位到
# desktop/src-tauri/binaries/backend/（可执行 + _internal/），由 tauri.conf.json 的
# bundle.resources 映射为 .app/Contents/Resources/backend/。
# onedir 取代 onefile：省掉每次启动对 ~250MB 二进制的自解压（实测 10-15s）。
# 用法: bash desktop/scripts/build-backend.sh [target-triple]
set -euo pipefail

TRIPLE="${1:-$(rustc -vV | sed -n 's/host: //p')}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
BIN_DIR="$REPO_ROOT/desktop/src-tauri/binaries"

# PyInstaller --onedir 产物是目录 dist/quantcell-backend/（内含可执行与 _internal/）；
# 落位目标同为整目录，跨平台只差可执行文件名（.exe 后缀）
PYINSTALLER_OUT_DIR="$BACKEND_DIR/dist/quantcell-backend"
SIDECAR_DIR="$BIN_DIR/backend"
if [[ "$TRIPLE" == *windows* ]]; then
  BACKEND_EXE="quantcell-backend.exe"
else
  BACKEND_EXE="quantcell-backend"
fi

if [ ! -d "$BACKEND_DIR/.venv" ]; then
  echo ">> backend/.venv 不存在，先执行 uv sync" >&2
  exit 1
fi

cd "$BACKEND_DIR"

# pyinstaller 用 uv --with 临时引入，不写入 backend/pyproject.toml
# torch / stable_baselines3 / gymnasium / onnx 链体积巨大（onefile 约 430MB），
# 业务代码全部懒加载，故排除出最小包，由桌面端「扩展能力」用随包 uv 按需安装：
# docs/superpowers/specs/2026-09-24-desktop-optional-extensions-design.md
# backend 以 PEP 660 editable 方式安装（__editable__ finder 绝对路径映射），
# PyInstaller 的 modulegraph 无法透过该 finder 解析本地包，必须显式把 backend
# 目录（即当前目录）加入模块搜索路径，否则冻结产物运行时 ModuleNotFoundError
uv run --with pyinstaller pyinstaller \
  --noconfirm --clean --onedir --name quantcell-backend \
  --paths . \
  --add-data "alembic:alembic" \
  `# ai/strategy/prompts/templates 含提示词 .txt 与思维链 .toml，运行时按
  # Path(__file__).parent/templates 相对定位（manager.py），漏打会在 AI 生成时
  # 报"模板分类 'strategy_generation' 不存在或未加载"` \
  --add-data "ai/strategy/prompts/templates:ai/strategy/prompts/templates" \
  `# strategy/templates/*.py 是运行时按 spec.origin 读源码的（ai/strategy/routes_strategy.py
  # _scan_template_list 提取模板参数表单），PyInstaller 只把模块编译进 PYZ、源文件不存在，
  # 漏打会让策略编辑器模板列表 500（No such file or directory .../strategy/templates/xxx.py）` \
  --add-data "strategy/templates:strategy/templates" \
  --collect-all axon_quant \
  --collect-all duckdb \
  --collect-all pyarrow \
  --collect-all ccxt \
  --collect-all statsmodels \
  --collect-submodules uvicorn \
  `# factor/__init__ 与 agent/tools/__init__ 用 PEP 562 __getattr__ 懒加载，
  # PyInstaller modulegraph 无法跟随 import_module，必须显式收集全部子模块，
  # 否则每次新增懒加载子模块（如 factor.routes）都会在冻结产物里 ModuleNotFoundError` \
  --collect-submodules factor \
  --collect-submodules agent.tools \
  `# 可选扩展依赖：不打入归档；未安装时业务侧保持既有"缺少 RL 训练依赖"降级提示` \
  --exclude-module torch \
  --exclude-module stable_baselines3 \
  --exclude-module gymnasium \
  --exclude-module onnx \
  --exclude-module onnxruntime \
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
# 整目录替换（不残留上一版 _internal/ 里的旧 .so）
rm -rf "$SIDECAR_DIR"
mv -f "$PYINSTALLER_OUT_DIR" "$SIDECAR_DIR"
# 清掉 onefile 时代的历史单文件产物，避免误拷旧 250MB 二进制
rm -f "$BIN_DIR/quantcell-backend-$TRIPLE" "$BIN_DIR/quantcell-backend-$TRIPLE.exe"
# Windows 不需要 chmod（git-bash 下 chmod 无效但无害，跳过以避免误解）
if [[ "$TRIPLE" != *windows* ]]; then
  chmod +x "$SIDECAR_DIR/$BACKEND_EXE"
fi
echo ">> backend onedir 已生成: $SIDECAR_DIR/$BACKEND_EXE"
echo ">> 目录大小: $(du -sh "$SIDECAR_DIR" | cut -f1)，文件数: $(find "$SIDECAR_DIR" -type f | wc -l | tr -d ' ')"

# 打包后自检：把「运行时会读包内文件」的端点真打一遍。PyInstaller 只保证 import
# 不炸（字节码进 PYZ），spec.origin/__file__ 指向的源文件缺失只能冷启动探测出来
# （案例 2026-11-25：strategy/templates/*.py 漏打 → 策略编辑器模板列表 500）。
# CI 的 desktop-build.yml 调本脚本，缺口在打包阶段直接红，不再漏到运行时。
bash "$(dirname "$0")/verify-sidecar.sh" "$SIDECAR_DIR"
