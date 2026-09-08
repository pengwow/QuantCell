"""
请求中间件模块

提供跨请求的可观测性能力：
- request_id：为每个 HTTP 请求生成/透传全局唯一 ID，注入日志上下文
  （utils.logger 的 trace_id），并在响应头 X-Request-ID 返回，便于链路追踪
- 结构化访问日志：记录 method / path / status / 耗时
"""

import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from utils.logger import LogType, clear_trace_id, get_logger, set_trace_id

logger = get_logger(__name__, LogType.API)

# 客户端可传入的请求 ID 头（网关层常透传此头）
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 request_id 并注入日志上下文

    透传链路的典型用法：
        前端在请求头附带 X-Request-ID（或由本中间件生成），
        后端日志的 trace_id 字段与响应头中的 X-Request-ID 一致，
        方便按请求 ID 串联日志与排障。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 优先复用客户端透传的 ID，否则生成新 ID（uuid4 hex，紧凑且不泄露机器信息）
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_trace_id(request_id)

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # call_next 抛异常时，最终会由 ServerErrorMiddleware 兜底返回 500；
            # 这里补一条带 request_id 的访问日志，再原样向上传播
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{request.method} {request.url.path} -> 500 ({duration_ms:.1f}ms)",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 1),
                },
            )
            raise
        finally:
            # 无论成功失败都清理上下文，避免污染下一请求
            clear_trace_id()

        # 统一记录访问日志（按 500 的状态码作为异常/正常分支标记）
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 1),
            },
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
