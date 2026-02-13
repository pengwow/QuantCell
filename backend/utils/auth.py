# JWT认证装饰器模块
# 实现JWT认证装饰器，用于保护API接口

from typing import Callable, Optional, Any

from fastapi import Depends, HTTPException, Request, Response
from functools import wraps
from loguru import logger

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


def get_current_user(request: Request) -> dict:
    """获取当前用户信息
    
    Args:
        request: FastAPI请求对象
    
    Returns:
        dict: 当前用户信息
    
    Raises:
        HTTPException: 认证失败时抛出
    """
    # 从请求头中提取令牌
    token = request.headers.get("Authorization")
    
    if not token:
        raise HTTPException(
            status_code=401,
            detail={
                "path": request.url.path,
                "reason": "未提供认证令牌"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 提取令牌部分（去掉Bearer前缀）
    try:
        token = token.split(" ")[1]
    except IndexError:
        raise HTTPException(
            status_code=401,
            detail={
                "path": request.url.path,
                "reason": "无效的认证令牌格式"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 验证令牌
    try:
        payload = decode_jwt_token(token)
        return payload
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail={
                "path": request.url.path,
                "reason": "令牌已过期"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError:
        raise HTTPException(
            status_code=401,
            detail={
                "path": request.url.path,
                "reason": "令牌无效"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenDecodeError:
        raise HTTPException(
            status_code=401,
            detail={
                "path": request.url.path,
                "reason": "令牌解码失败"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=401,
            detail={
                "path": request.url.path,
                "reason": f"认证失败: {str(e)}"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"认证过程中发生未知错误: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "path": request.url.path,
                "reason": "内部服务器错误"
            }
        )


def jwt_auth_required(func: Callable) -> Callable:
    """JWT认证装饰器
    
    用于保护需要认证的API接口，验证JWT令牌的有效性
    并支持令牌自动续期功能
    
    Args:
        func: 被装饰的API函数
    
    Returns:
        Callable: 装饰后的API函数
    """
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        # 从请求头中提取令牌
        token = request.headers.get("Authorization")
        
        if not token:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "未提供认证令牌"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 提取令牌部分（去掉Bearer前缀）
        try:
            token = token.split(" ")[1]
        except IndexError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "无效的认证令牌格式"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 验证令牌
        try:
            payload = decode_jwt_token(token)
        except TokenExpiredError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "令牌已过期"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except TokenInvalidError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "令牌无效"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except TokenDecodeError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "令牌解码失败"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWTError as e:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": f"认证失败: {str(e)}"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"认证过程中发生未知错误: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "path": request.url.path,
                    "reason": "内部服务器错误"
                }
            )
        
        # 检查是否需要刷新令牌
        new_token = None
        if should_refresh_token(token):
            # 生成新的访问令牌
            new_token = create_jwt_token(data={
                "sub": payload.get("sub"),
                "name": payload.get("name")
            })
        
        # 调用原始函数
        response = await func(request, *args, **kwargs)
        
        # 如果生成了新令牌，将其添加到响应头中
        if new_token:
            # 确保响应是Response对象
            if not isinstance(response, Response):
                # 如果是字典或其他类型，创建一个Response对象
                from fastapi.responses import JSONResponse
                if isinstance(response, dict):
                    response = JSONResponse(content=response)
                elif hasattr(response, 'model_dump'):
                    # 处理Pydantic模型（如ApiResponse）
                    response = JSONResponse(content=response.model_dump())
                else:
                    response = JSONResponse(content={"result": str(response)})
            
            # 添加新令牌到响应头
            response.headers["X-Refreshed-Token"] = new_token
        
        return response
    
    return wrapper


def jwt_auth_required_sync(func: Callable) -> Callable:
    """同步版本的JWT认证装饰器
    
    用于保护需要认证的同步API接口
    
    Args:
        func: 被装饰的API函数
    
    Returns:
        Callable: 装饰后的API函数
    """
    @wraps(func)
    def wrapper(request: Request, *args, **kwargs):
        # 从请求头中提取令牌
        token = request.headers.get("Authorization")
        
        if not token:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "未提供认证令牌"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 提取令牌部分（去掉Bearer前缀）
        try:
            token = token.split(" ")[1]
        except IndexError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "无效的认证令牌格式"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 验证令牌
        try:
            payload = decode_jwt_token(token)
        except TokenExpiredError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "令牌已过期"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except TokenInvalidError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "令牌无效"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except TokenDecodeError:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": "令牌解码失败"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except JWTError as e:
            raise HTTPException(
                status_code=401,
                detail={
                    "path": request.url.path,
                    "reason": f"认证失败: {str(e)}"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"认证过程中发生未知错误: {e}")
            raise HTTPException(
                status_code=500,
                detail={
                    "path": request.url.path,
                    "reason": "内部服务器错误"
                }
            )
        
        # 检查是否需要刷新令牌
        new_token = None
        if should_refresh_token(token):
            # 生成新的访问令牌
            new_token = create_jwt_token(data={
                "sub": payload.get("sub"),
                "name": payload.get("name")
            })
        
        # 调用原始函数
        response = func(request, *args, **kwargs)
        
        # 如果生成了新令牌，将其添加到响应头中
        if new_token:
            # 确保响应是Response对象
            if not isinstance(response, Response):
                # 如果是字典或其他类型，创建一个Response对象
                from fastapi.responses import JSONResponse
                if isinstance(response, dict):
                    response = JSONResponse(content=response)
                elif hasattr(response, 'model_dump'):
                    # 处理Pydantic模型（如ApiResponse）
                    # 使用mode='json'来处理datetime等不可序列化的类型
                    response = JSONResponse(content=response.model_dump(mode='json'))
                else:
                    response = JSONResponse(content={"result": str(response)})

            # 添加新令牌到响应头
            response.headers["X-Refreshed-Token"] = new_token

        return response
    
    return wrapper
