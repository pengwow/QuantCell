#!/usr/bin/env bash
# 下载 uv 单文件二进制到 desktop/src-tauri/resources/uv/（Tauri bundle resource）。
# 二进制不入库（src-tauri/.gitignore 忽略），CI 与本机打包前现现下。
# 用法: bash desktop/scripts/fetch-uv.sh [target-triple] [uv-version]
set -euo pipefail

TRIPLE="${1:-$(rustc -vV | sed -n 's/host: //p')}"
UV_VERSION="${2:-latest}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="$REPO_ROOT/desktop/src-tauri/resources/uv"

# uv release asset 三元组与 rustc 一致；Windows 分发包为 zip，其余为 tar.gz
if [[ "$TRIPLE" == *windows* ]]; then
  ASSET="uv-$TRIPLE.zip"
  UV_EXE="uv.exe"
else
  ASSET="uv-$TRIPLE.tar.gz"
  UV_EXE="uv"
fi

if [[ "$UV_VERSION" == "latest" ]]; then
  URL="https://github.com/astral-sh/uv/releases/latest/download/$ASSET"
else
  URL="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$ASSET"
fi
echo ">> 下载 $URL"

mkdir -p "$OUT_DIR"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fL "$URL" -o "$TMP/$ASSET"
mkdir -p "$TMP/extract"
if [[ "$ASSET" == *.zip ]]; then
  # GitHub Windows runner 与 Git for Windows 均自带 unzip
  unzip -q "$TMP/$ASSET" -d "$TMP/extract"
else
  tar -xzf "$TMP/$ASSET" -C "$TMP/extract"
fi
# 归档内顶层目录为 uv-<triple>/，同时含 uv 与 uvx，只取 uv
find "$TMP/extract" -name "$UV_EXE" -type f -exec mv -f {} "$OUT_DIR/$UV_EXE" \;
chmod +x "$OUT_DIR/$UV_EXE"  # Windows 下 chmod 无害
"$OUT_DIR/$UV_EXE" --version
echo ">> uv 已就位: $OUT_DIR/$UV_EXE"
