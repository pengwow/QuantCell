# JWT认证统一模块
# 统一认证入口：
# - get_current_user：FastAPI 依赖注入方式（Depends），同时支持 Authorization 头与 SSE query token
# - jwt_auth_required / jwt_auth_required_sync：兼容装饰器，委托同一套校验逻辑
# - 续期 token 统一写入 request.state.refreshed_token，由 RequestIDMiddleware 注入 X-Refreshed-Token
#
# 路由层统一用法：
#     async def ep(current_user: dict = Depends(get_current_user)): ...
# SSE 等无法发送 Authorization 头的场景：
#     路由声明 token: str | None = Query(None) 后手动调用 authenticate_request(request, token=token)

import os
from functools import wraps
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)
from .jwt_utils import (
    JWTError,
    TokenDecodeError,
    TokenExpiredError,
    TokenInvalidError,
    create_jwt_token,
    decode_jwt_token,
    should_refresh_token,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# ponytail: debug 模式跳过认证，每次调用时实时检查以支持测试中动态设置。
# 「生产环境强制豁免」优先级最高：只要 APP_ENV=production/prod，
# 无论是否携带 DEBUG 标志都不允许跳过认证，防止误配导致接口裸奔。
def _is_debug_mode() -> bool:
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env in ("production", "prod"):
        return False
    return os.environ.get("DEBUG", "").lower() in ("true", "1", "yes") or app_env in ("development", "dev", "debug")


# 模块级变量，可被测试 patch
IS_DEBUG_MODE = _is_debug_mode()


def _auth_disabled() -> bool:
    """debug 跳过判定（生产环境强制关闭）。

    env(DEBUG/APP_ENV)每次请求实时读取——测试文件常在模块级先被其他测试
    导入 utils.auth 之后才设置 os.environ["DEBUG"]，若只看导入时固化的
    IS_DEBUG_MODE 会漏掉后设的 env；同时保留模块级变量供测试直接 patch。
    生产环境额外拦截：即使测试 patch IS_DEBUG_MODE 也无法绕过。
    """
    app_env = os.environ.get("APP_ENV", "").lower()
    if app_env in ("production", "prod"):
        return False
    return IS_DEBUG_MODE or _is_debug_mode()


def _extract_bearer_token(request: Request) -> str:
    """从 Authorization 头提取 Bearer token，失败抛 HTTP 401。

    严格校验 scheme 必须为 Bearer（大小写不敏感），
    避免 Basic/Token 等其他 scheme 被误当作 JWT 解析。
    注意 token 不做 strip 处理：保留原始空白字符交由 jwt 解码校验，
    与既有测试「token 内部多余空格须返回 401」的行为保持一致。
    """
    auth = request.headers.get("Authorization")
    if not auth:
        raise HTTPException(
            status_code=401,
            detail={"path": request.url.path, "reason": "未提供认证令牌"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        scheme, token = auth.split(" ", 1)
    except ValueError:
        scheme, token = "", ""
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail={"path": request.url.path, "reason": "无效的认证令牌格式"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def _decode_token_or_raise(token: str, path: str) -> dict:
    """解码 JWT token，失败时抛对应 HTTP 异常。"""
    try:
        return decode_jwt_token(token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail={"path": path, "reason": "令牌已过期"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=401,
            detail={"path": path, "reason": "令牌无效"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenDecodeError:
        raise HTTPException(
            status_code=401,
            detail={"path": path, "reason": "令牌解码失败"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail={"path": path, "reason": f"认证失败: {e}"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"认证过程中发生未知错误: {e}")
        raise HTTPException(status_code=500, detail={"path": path, "reason": "内部服务器错误"})


def _maybe_refresh_token(token: str, payload: dict) -> str | None:
    """如需刷新则返回新 token，否则 None。"""
    if should_refresh_token(token):
        return create_jwt_token(data={"sub": payload.get("sub"), "name": payload.get("name")})
    return None


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

# 模块级 HTTPBearer 实例（auto_error=False：缺失/格式错时返回 None，由下方统一抛出 401）
security = HTTPBearer(auto_error=False)


def _build_user_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """规范化用户信息：保留 JWT 原生键（sub/name/role），同时补 user_id/user_name 别名。

    历史上有两套读取约定：
    - 装饰器时代：request.state.user 是原始 payload，业务读 sub / name
    - worker/share：current_user.get("user_id") / get("user_name")
    统一返回同时携带两套键，避免下游按旧约定取值时拿到 None。
    """
    return {
        "sub": payload.get("sub"),
        "user_id": payload.get("sub"),
        "name": payload.get("name"),
        "user_name": payload.get("name"),
        "role": payload.get("role"),
    }


def _store_authenticated_user(request: Request, jwt_token: str, payload: dict) -> dict:
    """认证成功后写入 request.state，返回统一用户字典。

    - request.state.user：路由层可直接读取当前用户
    - request.state.refreshed_token：由 RequestIDMiddleware 统一注入 X-Refreshed-Token 响应头，
      避免每个路由自行包装响应（装饰器与 Depends 两条链路行为一致）
    """
    user = _build_user_dict(payload)
    request.state.user = user
    new_token = _maybe_refresh_token(jwt_token, payload)
    if new_token:
        request.state.refreshed_token = new_token
    return user


def _authenticate(request: Request, token: str | None = None) -> dict:
    """同步认证核心（装饰器与 async 依赖共用同一套校验逻辑）。"""
    if _auth_disabled():
        logger.debug(f"Debug模式：跳过JWT认证 - {request.url.path}")
        request.state.user = {}
        return request.state.user

    jwt_token = token or _extract_bearer_token(request)
    payload = _decode_token_or_raise(jwt_token, request.url.path)
    return _store_authenticated_user(request, jwt_token, payload)


async def authenticate_request(request: Request, token: str | None = None) -> dict:
    """统一认证入口（供 SSE 等无法携带 Authorization 头的场景手动调用）。

    用法：
        async def sse_endpoint(request: Request, token: str | None = Query(None)):
            await authenticate_request(request, token=token)
    """
    return _authenticate(request, token)


async def get_current_user(
    request: Request,
    token: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """获取当前用户信息（统一供 Depends 使用）。

    支持两种取 token 方式：
    1. query 参数 ?token=<jwt>（EventSource 等无法自定义请求头的场景）
    2. Authorization: Bearer <jwt>

    注意：不直接使用 credentials.credentials —— 新版 Starlette 的 HTTPBearer
    会自动 strip token 首尾空白，历史行为要求 token 内多余空格返回 401
    （见 tests/integration/api/test_auth.py::test_whitespace_in_token），
    因此标准 Bearer 头场景统一走 _extract_bearer_token 的严格提取。
    credentials 参数仅用于在 OpenAPI 文档中声明 HTTPBearer 安全方案。
    """
    if token:
        return _authenticate(request, token)
    return _authenticate(request)


def jwt_auth_required(func: Callable) -> Callable:
    """异步 JWT 认证装饰器（兼容保留，内部复用统一认证逻辑）。"""

    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        _authenticate(request)
        return await func(request, *args, **kwargs)

    return wrapper


def jwt_auth_required_sync(func: Callable) -> Callable:
    """同步 JWT 认证装饰器（兼容保留，内部复用统一认证逻辑）。"""

    @wraps(func)
    def wrapper(request: Request, *args, **kwargs):
        _authenticate(request)
        return func(request, *args, **kwargs)

    return wrapper
