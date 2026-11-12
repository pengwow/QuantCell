"""指标定义与埋点辅助函数（P2-01）

指标选型对齐方案（完整版 §P2-01）：
- HTTP：请求计数 + 请求时长直方图（可算 p50/p95）+ 在途请求 gauge
- worker：泵轮耗时（轮询延迟）、成交落库/同步失败计数、重启收口计数、运行泵数 gauge

高基数防护：HTTP 全部用 route 模板（/workers/{id}）做 label，不用原始 path，
不加 request_id / user_id（request_id 只留给日志关联，见 core/middleware.py）。
worker_id label 由部署形态决定上限（个位数 worker），进程生命周期内单调但有限。
"""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

__all__ = [
    "CONTENT_TYPE_LATEST",
    "generate_latest",
    "inc_sync_failure",
    "inc_worker_restart",
    "metrics_enabled",
    "observe_pump_round",
    "render_metrics",
]

# ---------- HTTP 埋点（ObservabilityAPI 的 MetricsMiddleware 使用） ----------

HTTP_IN_PROGRESS = Gauge(
    "qc_http_in_progress",
    "当前在途 HTTP 请求数",
)
HTTP_REQUESTS = Counter(
    "qc_http_requests_total",
    "HTTP 请求总数（route 为模板路径，未匹配路由记 unmatched）",
    ["route", "method", "status"],
)
HTTP_DURATION = Histogram(
    "qc_http_request_duration_seconds",
    "HTTP 请求耗时（秒）",
    ["route", "method"],
)

# ---------- worker 埋点（strategy_manager 泵线程 / lifespan 启动收口使用） ----------

WORKER_PUMP_DURATION = Histogram(
    "qc_worker_pump_round_seconds",
    "worker 泵轮耗时（秒）：live=tick 节拍、paper=拉取喂单轮",
    ["worker_id", "pump"],
)
WORKER_SYNC_FAILURES = Counter(
    "qc_worker_sync_failures_total",
    "worker 成交落库/同步失败次数（仅异常路径，观测性不反噬交易循环）",
    ["worker_id", "kind"],
)
WORKER_RESTARTS = Counter(
    "qc_worker_restarts_total",
    "进程重启导致 running→interrupted 收口的 worker 次数",
    ["worker_id"],
)
# 队列深度口径说明：当前 worker 泵是每 worker 一线程的循环，没有独立任务队列
# （ponytail: 以「运行泵数」作为任务深度代理指标；若将来引入统一任务队列，
# 把下面 set_function 换成 queue.qsize() 即可，指标名不变）
WORKER_QUEUE_DEPTH = Gauge(
    "qc_worker_queue_depth",
    "运行中的 worker 泵数量（任务队列深度的代理口径，当前无独立任务队列）",
)


def _install_running_pumps_gauge() -> None:
    """注册运行中 worker 泵数 gauge（抓取时才取值，读数无漂移）"""

    def _count_running() -> float:
        # 函数内 import：worker.state 拉起 collector.db 重依赖链，延迟到抓取时刻
        # 首次加载（import 缓存后为零成本），避免 observability 被 main.py 外
        # 的轻量入口导入时连带初始化 DB
        from worker.state import strategy_registry

        return float(sum(1 for s in strategy_registry.list_all() if s.status == "running"))

    WORKER_QUEUE_DEPTH.set_function(_count_running)


_install_running_pumps_gauge()


# ---------- 埋点辅助（供 strategy_manager / lifespan 调用，一直可用不读开关） ----------


def observe_pump_round(worker_id: int, pump: str, started_at: float) -> None:
    """记录一次泵轮耗时；started_at 传 perf_counter() 起点"""
    WORKER_PUMP_DURATION.labels(str(worker_id), pump).observe(time.perf_counter() - started_at)


def inc_sync_failure(worker_id: int, kind: str) -> None:
    """成交落库/同步失败计数 +1（kind: 'live' / 'paper'）"""
    WORKER_SYNC_FAILURES.labels(str(worker_id), kind).inc()


def inc_worker_restart(worker_id: int) -> None:
    """worker 重启收口计数 +1（lifespan 启动恢复扫描处）"""
    WORKER_RESTARTS.labels(str(worker_id)).inc()


# ---------- 开关与渲染（端点 / 中间件使用） ----------


def metrics_enabled() -> bool:
    """总开关 observability.metrics_enabled（config.toml，默认 false）

    ponytail: 每请求重读 config.toml（微秒级，与 utils/rbac 同口径）；请求热路径
    若将来实测有感知，再加 10s TTL 缓存——接口签名不变。
    """
    # 函数内 import：utils.config_manager 顶部会拉起 collector.db.database，
    # 延迟到调用时加载（与 utils/rbac.py 同因，避免 observability 拖重依赖链）
    from utils.config_manager import get_flag

    return get_flag("observability.metrics_enabled", False)


def render_metrics() -> tuple[bytes, str]:
    """渲染 Prometheus 文本格式（当前单进程 uvicorn，不需要 multiproc）"""
    return generate_latest(), CONTENT_TYPE_LATEST
