# JWT认证装饰器模块
# 实现JWT认证装饰器，用于保护API接口

import os
from typing import Callable, Optional, Any

from fastapi import Depends, HTTPException, Request, Response
from functools import wraps
from fastapi.responses import JSONResponse
from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)
from .jwt_utils import (
    decode_jwt_token,
    verify_jwt_token,
    should_refresh_token,
    create_jwt_token,
    JWTError,
    TokenExpiredError,
    TokenInvalidError,
    TokenDecodeError
)

# ponytail: debug 模式跳过认证，每次调用时检查以支持测试中动态设置
def _is_debug_mode() -> bool:
    return os.environ.get('DEBUG', '').lower() in ('true', '1', 'yes') or \
           os.environ.get('APP_ENV', '').lower() in ('development', 'dev', 'debug')


def _extract_bearer_token(request: Request) -> str:
    """从 Authorization 头提取 Bearer token，失败抛 HTTP 401。"""
    auth = request.headers.get("Authorization")
    if not auth:
        raise HTTPException(
            status_code=401,
            detail={"path": request.url.path, "reason": "未提供认证令牌"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return auth.split(" ")[1]
    except IndexError:
        raise HTTPException(
            status_code=401,
            detail={"path": request.url.path, "reason": "无效的认证令牌格式"},
            headers={"WWW-Authenticate": "Bearer"},
        )


def _decode_token_or_raise(token: str, path: str) -> dict:
    """解码 JWT token，失败时抛对应 HTTP 异常。"""
    try:
        return decode_jwt_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail={"path": path, "reason": "令牌已过期"},
                            headers={"WWW-Authenticate": "Bearer"})
    except TokenInvalidError:
        raise HTTPException(status_code=401, detail={"path": path, "reason": "令牌无效"},
                            headers={"WWW-Authenticate": "Bearer"})
    except TokenDecodeError:
        raise HTTPException(status_code=401, detail={"path": path, "reason": "令牌解码失败"},
                            headers={"WWW-Authenticate": "Bearer"})
    except JWTError as e:
        raise HTTPException(status_code=401, detail={"path": path, "reason": f"认证失败: {e}"},
                            headers={"WWW-Authenticate": "Bearer"})
    except Exception as e:
        logger.error(f"认证过程中发生未知错误: {e}")
        raise HTTPException(status_code=500, detail={"path": path, "reason": "内部服务器错误"})


def _maybe_refresh_token(token: str, payload: dict) -> Optional[str]:
    """如需刷新则返回新 token，否则 None。"""
    if should_refresh_token(token):
        return create_jwt_token(data={"sub": payload.get("sub"), "name": payload.get("name")})
    return None


def _wrap_response_with_token(response: Any, new_token: str) -> Response:
    """将 new_token 注入 X-Refreshed-Token 响应头。"""
    if not isinstance(response, Response):
        if isinstance(response, dict):
            response = JSONResponse(content=response)
        elif hasattr(response, 'model_dump'):
            response = JSONResponse(content=response.model_dump(mode='json'))
        else:
            response = JSONResponse(content={"result": str(response)})
    response.headers["X-Refreshed-Token"] = new_token
    return response


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def get_current_user(request: Request) -> dict:
    """获取当前用户信息（供 Depends 使用）"""
    token = _extract_bearer_token(request)
    return _decode_token_or_raise(token, request.url.path)


def jwt_auth_required(func: Callable) -> Callable:
    """异步 JWT 认证装饰器，支持 debug 跳过 + token 自动续期。"""
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        if _is_debug_mode():
            logger.debug(f"Debug模式：跳过JWT认证 - {request.url.path}")
            return await func(request, *args, **kwargs)

        token = _extract_bearer_token(request)
        payload = _decode_token_or_raise(token, request.url.path)
        new_token = _maybe_refresh_token(token, payload)

        response = await func(request, *args, **kwargs)

        if new_token:
            response = _wrap_response_with_token(response, new_token)
        return response

    return wrapper


def jwt_auth_required_sync(func: Callable) -> Callable:
    """同步 JWT 认证装饰器，支持 debug 跳过 + token 自动续期。"""
    @wraps(func)
    def wrapper(request: Request, *args, **kwargs):
        if _is_debug_mode():
            logger.debug(f"Debug模式：跳过JWT认证 - {request.url.path}")
            return func(request, *args, **kwargs)

        token = _extract_bearer_token(request)
        payload = _decode_token_or_raise(token, request.url.path)
        new_token = _maybe_refresh_token(token, payload)

        response = func(request, *args, **kwargs)

        if new_token:
            response = _wrap_response_with_token(response, new_token)
        return response

    return wrapper
