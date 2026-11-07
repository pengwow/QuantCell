#!/bin/bash
# ==============================================================================
# 本地决策模型（System 1 · Laya）启动脚本
# ==============================================================================
# 用法：
#   ./start_laya.sh [start|stop|status|restart]
#
# 启动 laya_serve_local.py（lagxee /v1/decide 适配层），供设置页
# 「System 1 决策模型」的 api_host 指向（默认 http://127.0.0.1:8010）。
# 模型/端口/鉴权通过环境变量透传：LAYA_MODEL / LAYA_HOST / LAYA_PORT / LAYA_API_KEY
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER="$SCRIPT_DIR/laya_serve_local.py"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)/logs"
LOG_FILE="$LOG_DIR/laya.log"
PID_FILE="$LOG_DIR/laya.pid"
PORT="${LAYA_PORT:-8010}"

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

# 独立 venv 不存在或依赖缺失时自动补装（正常情况直接跳过）
ensure_venv() {
    if "$VENV/bin/python" -c "import laya_mlx, uvicorn" 2>/dev/null; then
        return
    fi
    echo "[INFO] 初始化独立 venv 并安装依赖（与 backend 环境隔离）..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
}

do_start() {
    if is_running; then
        echo "[INFO] 决策模型已在运行 (pid $(cat "$PID_FILE"))，无需重复启动"
        return 0
    fi
    rm -f "$PID_FILE"
    mkdir -p "$LOG_DIR"
    ensure_venv
    echo "[INFO] 启动决策模型服务，日志: $LOG_FILE"
    nohup "$VENV/bin/python" "$SERVER" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    # 首次启动需加载/下载 checkpoint，可能较久；这里只等 300s 超时后引导看日志
    for _ in $(seq 1 150); do
        if curl -sf "http://127.0.0.1:$PORT/health" > /dev/null 2>&1; then
            echo "[SUCCESS] 决策模型已就绪: http://127.0.0.1:$PORT (设置页 api_host 填 http://127.0.0.1:$PORT)"
            return 0
        fi
        kill -0 "$(cat "$PID_FILE")" 2>/dev/null || {
            echo "[ERROR] 服务进程退出，最近日志:"; tail -20 "$LOG_FILE"; return 1; }
        sleep 2
    done
    echo "[WARN] ${PORT} 端口 300s 内未就绪（首次运行可能仍在下载 checkpoint），请查看 $LOG_FILE"
}

do_stop() {
    if is_running; then
        local pid
        pid=$(cat "$PID_FILE")
        kill "$pid" 2>/dev/null || true
        # uvicorn 优雅退出需要时间，等进程真正退出，超时后强杀兜底
        for _ in $(seq 1 15); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        echo "[SUCCESS] 已停止决策模型 (pid $pid)"
    else
        echo "[INFO] 决策模型未在运行"
    fi
    rm -f "$PID_FILE"
}

do_status() {
    if is_running; then
        if curl -sf "http://127.0.0.1:$PORT/health" 2>/dev/null; then
            echo ""
            echo "[SUCCESS] 决策模型运行中 (pid $(cat "$PID_FILE"))"
        else
            echo "[WARN] 进程在运行 (pid $(cat "$PID_FILE")) 但 /health 未就绪（可能正在加载模型），日志: $LOG_FILE"
        fi
    else
        echo "[INFO] 决策模型未在运行"
    fi
}

case "${1:-start}" in
    start)   do_start ;;
    stop)    do_stop ;;
    status)  do_status ;;
    restart) do_stop; do_start ;;
    *) echo "用法: $0 [start|stop|status|restart]"; exit 1 ;;
esac
