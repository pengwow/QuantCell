"""HTTP 指标埋点中间件（P2-01）

挂在 RequestIDMiddleware 内层（main.py 注册顺序：后 add 的在外层）。
开关 observability.metrics_enabled 关闭时直通（零指标开销），默认关闭。

高基数防护：route label 取 Starlette 路由模板（scope["route"].path，如
/api/v1/workers/{worker_id}），未匹配路由（404/静态扫描）统一记 unmatched；
request_id 只留给日志，不作为 label。

实现说明：采用纯 ASGI 协议而非 BaseHTTPMiddleware，避免每请求任务复制与
memory-stream 转发开销（见 core/middleware.py 顶部说明）。
"""

import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from observability.metrics import HTTP_DURATION, HTTP_IN_PROGRESS, HTTP_REQUESTS, metrics_enabled


class MetricsMiddleware:
    """请求计数 + 耗时直方图 + 在途 gauge；开关关闭时零开销直通

    状态码在 http.response.start 捕获；若下游抛异常或客户端断开导致 start
    未发出，finally 按 500 记录，保证 in_progress gauge 必然回落。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not metrics_enabled():
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        HTTP_IN_PROGRESS.inc()
        started_at = time.perf_counter()
        status_holder: list[str] = []

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder.append(str(message["status"]))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # 异常或断连时 status 缺失，按 500 兜底；最终 500 响应由
            # ServerErrorMiddleware 生成，行为与原 BaseHTTPMiddleware 版本一致
            self._record(scope, method, status_holder[0] if status_holder else "500", time.perf_counter() - started_at)

    @staticmethod
    def _record(scope: Scope, method: str, status: str, duration_s: float) -> None:
        HTTP_IN_PROGRESS.dec()
        # route 在路由匹配阶段写入 scope，此处必已就绪（或为 unmatched）
        route = getattr(scope.get("route"), "path", None) or "unmatched"
        HTTP_REQUESTS.labels(route, method, status).inc()
        HTTP_DURATION.labels(route, method).observe(duration_s)
