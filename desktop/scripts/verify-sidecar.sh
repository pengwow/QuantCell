#!/usr/bin/env bash
# 打包产物自检：sidecar 落位后，把「运行时会读包内文件」的端点真打一遍。
#
# 为什么需要：PyInstaller 只保证 import 不炸（模块字节码进 PYZ 归档），不保证
# spec.origin / __file__ 指向的源文件在包里。这类缺口运行时才爆（案例 2026-11-25：
# strategy/templates/*.py 漏打，_scan_template_list 读 spec.origin 直接 500，
# 策略编辑器模板列表全挂），静态构建日志看不出任何异常。
#
# 机制：以 local 模式冷启动打包产物（与 .app 内同一二进制），逐条 curl 自检清单，
# 任一非 2xx 即以非零码退出。build-backend.sh 末尾会调用本脚本，CI 的
# desktop-build.yml 调 build-backend.sh，因此本地与 CI 打包都会红在这。
#
# 维护规则：新增「运行时 open 包内文件」的端点时，往 CHECKS 里补一行。
# 用法: bash desktop/scripts/verify-sidecar.sh [sidecar目录]（缺省为 src-tauri/binaries/backend）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${1:-$SCRIPT_DIR/../src-tauri/binaries/backend}"

SIDECAR="$BIN_DIR/quantcell-backend"
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == CYGWIN* ]]; then
  SIDECAR="$BIN_DIR/quantcell-backend.exe"
fi
if [[ ! -x "$SIDECAR" ]]; then
  echo ">> selfcheck: sidecar 不存在: $SIDECAR" >&2
  exit 1
fi

# 随机空闲端口，避免与开发者本机 8000/19999 撞车（无 python3 的环境退回固定端口）
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()' 2>/dev/null || echo 19991)"
DATA_DIR="$(mktemp -d)"
LOG="$DATA_DIR/selfcheck.log"
BASE="http://127.0.0.1:$PORT"

QUANTCELL_DESKTOP_LOCAL=1 "$SIDECAR" --host 127.0.0.1 --port "$PORT" --data-dir "$DATA_DIR" >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; rm -rf "$DATA_DIR"' EXIT

# 健康等待：onedir 冷启动首跑要 import 全量路由 + 三方库（外部盘 1-2 分钟内属正常）
READY=0
for _ in $(seq 1 90); do
  if curl -sf -o /dev/null --max-time 2 "$BASE/health"; then READY=1; break; fi
  sleep 2
done
if [[ "$READY" != 1 ]]; then
  echo ">> selfcheck FAIL: sidecar 180s 未就绪" >&2
  tail -30 "$LOG" >&2
  exit 1
fi

FAIL=0
check() {
  local method="$1" path="$2" code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 -X "$method" "$BASE$path")"
  if [[ "$code" == 2* ]]; then
    echo ">> selfcheck ok   $method $path -> $code"
  else
    echo ">> selfcheck FAIL $method $path -> $code"
    FAIL=1
  fi
}

# —— 自检清单：凡「运行时会 open 包内文件」的端点都要登记（新增时同步补）——
# strategy/templates/*.py 经 spec.origin 读源码提取模板参数表单（_scan_template_list）
check GET /api/v1/ai-models/strategy/templates

if [[ "$FAIL" -ne 0 ]]; then
  echo ">> selfcheck: 存在失败项，sidecar 日志尾部：" >&2
  tail -40 "$LOG" >&2
else
  echo ">> selfcheck: 全部通过"
fi
exit "$FAIL"
