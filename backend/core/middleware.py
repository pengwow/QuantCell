"""
请求中间件模块

提供跨请求的可观测性能力：
- request_id：为每个 HTTP 请求生成/透传全局唯一 ID，注入日志上下文
  （utils.logger 的 trace_id），并在响应头 X-Request-ID 返回，便于链路追踪
- 结构化访问日志：记录 method / path / status / 耗时
- X-Refreshed-Token：统一注入认证模块写入 request.state.refreshed_token 的续期 token，
  避免各个路由自行包装响应（Depends 与装饰器两条链路行为一致）

实现说明：采用纯 ASGI 协议而非 BaseHTTPMiddleware——后者对每个请求做任务复制
加 anyio memory-stream 转发，SSE/流式响应逐帧都要过中间层，首字节延迟与断连
检测都被拖累；纯 ASGI 直通转发无此开销。
"""

import time
import uuid

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from utils.logger import LogType, clear_trace_id, get_logger, set_trace_id

logger = get_logger(__name__, LogType.API)

# 客户端可传入的请求 ID 头（网关层常透传此头）
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """为每个请求生成 request_id 并注入日志上下文

    透传链路的典型用法：
        前端在请求头附带 X-Request-ID（或由本中间件生成），
        后端日志的 trace_id 字段与响应头中的 X-Request-ID 一致，
        方便按请求 ID 串联日志与排障。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # websocket / lifespan 直接透传，不注入请求上下文
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 优先复用客户端透传的 ID，否则生成新 ID（uuid4 hex，紧凑且不泄露机器信息）
        request_id = Headers(scope=scope).get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        # contextvar 在同一协程链上传播，端点内通过 utils.logger 读取 trace_id
        set_trace_id(request_id)

        method = scope["method"]
        path = scope["path"]
        start_time = time.perf_counter()
        status_holder: list[int] = []

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder.append(message["status"])
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    f"{method} {path} -> {message['status']} ({duration_ms:.1f}ms)",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "duration_ms": round(duration_ms, 1),
                    },
                )
                # 原地注入响应头：request_id + 续期 token
                # （认证成功后由 utils.auth 写入 scope["state"].refreshed_token）
                raw_headers = list(message.setdefault("headers", []))
                raw_headers.append((b"x-request-id", request_id.encode("latin-1")))
                refreshed_token = scope.setdefault("state", {}).get("refreshed_token")
                if refreshed_token:
                    raw_headers.append((b"x-refreshed-token", str(refreshed_token).encode("latin-1")))
                message["headers"] = raw_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            # 下游抛异常时，最终会由 ServerErrorMiddleware 兜底返回 500；
            # 这里补一条带 request_id 的访问日志，再原样向上传播
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{method} {path} -> 500 ({duration_ms:.1f}ms)",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "duration_ms": round(duration_ms, 1),
                },
            )
            raise
        finally:
            # 无论成功失败都清理上下文，避免污染下一请求
            clear_trace_id()
