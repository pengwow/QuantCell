#!/usr/bin/env bash
# 一条命令把「打包产物」跑进浏览器（零安装，替代 .app 冒烟的手工步骤）：
#   打包 sidecar（PyInstaller 二进制，与 .app 内字节相同）
#   + vite preview 伺服 frontend/dist（Tauri 壳内嵌的同一份资源）
#   + /api、/ws 反代到 sidecar（QC_PROXY_TARGET，见 vite.config.ts）
# 浏览器自动化可直接驱动 http://localhost:$FE_PORT；页面登录门免掉：
#   后端以 QUANTCELL_DESKTOP_LOCAL=1 启动（鉴权全豁免），只需向浏览器
#   localStorage 注入任意 token 过前端路由守卫（脚本启动后会打印注入片段）。
#
# 用法: bash desktop/scripts/preview-packaged.sh [--fresh] [--sidecar-port N] [--fe-port N] [--data-dir DIR]
#   --fresh            清空数据目录后启动（默认保留，便于保留 AI 提供商等配置）
#   --data-dir DIR     自定义数据目录（如指向真实 app 数据目录时，先退出 GUI 应用，
#                      避免两个进程并发写同一 SQLite）
# 详见 desktop/README.md「浏览器验证打包产物」。Tauri 壳专属能力（更新器、
# 崩溃遮罩、系统代理继承）不在浏览器链路内，仍需 .app 冒烟覆盖。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
TRIPLE="$(rustc -vV | sed -n 's/host: //p')"
SIDECAR="$REPO_ROOT/desktop/src-tauri/binaries/quantcell-backend-$TRIPLE"
VITE_BIN="$FRONTEND_DIR/node_modules/.bin/vite"

SIDECAR_PORT=19999
FE_PORT=4173
DATA_DIR="${TMPDIR:-/tmp}/quantcell-preview-data"
FRESH=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --fresh) FRESH=1; shift ;;
    --sidecar-port) SIDECAR_PORT="$2"; shift 2 ;;
    --fe-port) FE_PORT="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

[[ -x "$SIDECAR" ]] || { echo ">> sidecar 不存在: $SIDECAR（先跑 bash desktop/scripts/build-backend.sh）" >&2; exit 1; }
[[ -d "$FRONTEND_DIR/dist" ]] || { echo ">> frontend/dist 不存在（先跑 bun run build）" >&2; exit 1; }
[[ -x "$VITE_BIN" ]] || { echo ">> $VITE_BIN 不存在（frontend 下先装依赖）" >&2; exit 1; }
for p in "$SIDECAR_PORT" "$FE_PORT"; do
  if lsof -ti ":$p" >/dev/null 2>&1; then
    echo ">> 端口 $p 被占用（lsof -ti :$p 查看；或用 --sidecar-port/--fe-port 换口）" >&2
    exit 1
  fi
done

if [[ "$FRESH" == 1 && -d "$DATA_DIR" ]]; then
  rm -rf "$DATA_DIR"
fi
mkdir -p "$DATA_DIR"

echo ">> sidecar: $(basename "$SIDECAR") $(du -h "$SIDECAR" | cut -f1) mtime=$(stat -f '%Sm' "$SIDECAR")"
echo ">> 数据目录: $DATA_DIR"
echo ">> dist 构建时间: $(stat -f '%Sm' "$FRONTEND_DIR/dist/index.html")"

CORS_ORIGINS="tauri://localhost,http://tauri.localhost,http://localhost:$FE_PORT,http://127.0.0.1:$FE_PORT" \
QUANTCELL_DESKTOP_LOCAL=1 \
  "$SIDECAR" --host 127.0.0.1 --port "$SIDECAR_PORT" --data-dir "$DATA_DIR" \
  > "$DATA_DIR/sidecar.log" 2>&1 &
SIDECAR_PID=$!

cleanup() {
  kill "$SIDECAR_PID" "$VITE_PID" 2>/dev/null || true
}
# INT/TERM 也要触发：仅挂 EXIT 时，kill 掉脚本会漏杀 sidecar/preview
trap cleanup EXIT INT TERM

for _ in $(seq 1 40); do
  if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$SIDECAR_PORT/health"; then
    break
  fi
  # onefile 冷启动在外部盘可能要 1-2 分钟；等 failure 早点暴露
  if ! kill -0 "$SIDECAR_PID" 2>/dev/null; then
    echo ">> sidecar 启动即退，日志尾部：" >&2
    tail -20 "$DATA_DIR/sidecar.log" >&2
    exit 1
  fi
  sleep 3
done
curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$SIDECAR_PORT/health" || {
  echo ">> sidecar 健康检查超时，日志尾部：" >&2; tail -20 "$DATA_DIR/sidecar.log" >&2; exit 1;
}
echo ">> sidecar 就绪: http://127.0.0.1:$SIDECAR_PORT/health ✓"

cd "$FRONTEND_DIR"
QC_PROXY_TARGET="http://127.0.0.1:$SIDECAR_PORT" "$VITE_BIN" preview --port "$FE_PORT" --strictPort &
VITE_PID=$!

sleep 2
kill -0 "$VITE_PID" 2>/dev/null || { echo ">> vite preview 启动失败" >&2; exit 1; }

echo ""
echo "=========================================================="
echo "  打包产物浏览器预览（零安装，与 .app 同二进制同 dist）"
echo "  地址: http://localhost:$FE_PORT"
echo "  sidecar 日志: $DATA_DIR/sidecar.log"
echo "  数据目录:     $DATA_DIR"
echo "  免登录（二选一）:"
echo "    浏览器控制台执行（两个 key 都要：守卫读 access_token，请求头读 quantcell_jwt_token）:"
echo "      localStorage.setItem('quantcell_jwt_token', JSON.stringify({access_token:'desktop-local', refresh_token:'desktop-local'})); localStorage.setItem('access_token', 'desktop-local'); location.href='/'"
echo "    或注册/登录任意账号（local 模式后端不校验 token）"
echo "  Ctrl-C 退出并同时结束 sidecar 与 preview"
echo "=========================================================="
echo ""

wait "$VITE_PID"
