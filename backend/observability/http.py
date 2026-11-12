"""HTTP 指标埋点中间件（P2-01）

挂在 RequestIDMiddleware 内层（main.py 注册顺序：后 add 的在外层）。
开关 observability.metrics_enabled 关闭时直通（零指标开销），默认关闭。

高基数防护：route label 取 Starlette 路由模板（scope["route"].path，如
/api/v1/workers/{worker_id}），未匹配路由（404/静态扫描）统一记 unmatched；
request_id 只留给日志，不作为 label。
"""

import time
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from observability.metrics import HTTP_DURATION, HTTP_IN_PROGRESS, HTTP_REQUESTS, metrics_enabled


def _route_label(request: Request) -> str:
    """路由模板 label：命中则用 route.path（含 {param} 占位），未命中记 unmatched"""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    """请求计数 + 耗时直方图 + 在途 gauge；开关关闭时零开销直通"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not metrics_enabled():
            return await call_next(request)

        HTTP_IN_PROGRESS.inc()
        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # call_next 抛异常时最终由 ServerErrorMiddleware 兜底 500；先补记指标
            # 再原样上抛（观测性不反噬业务链路）
            self._record(request, "500", time.perf_counter() - started_at)
            raise
        self._record(request, str(response.status_code), time.perf_counter() - started_at)
        return response

    @staticmethod
    def _record(request: Request, status: str, duration_s: float) -> None:
        HTTP_IN_PROGRESS.dec()
        route = _route_label(request)
        HTTP_REQUESTS.labels(route, request.method, status).inc()
        HTTP_DURATION.labels(route, request.method).observe(duration_s)
