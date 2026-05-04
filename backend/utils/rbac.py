"""
RBAC (Role-Based Access Control) 权限控制模块
实现基于角色的访问控制，支持访客和普通用户角色
"""

from enum import Enum
from typing import Dict, List, Optional, Set
from functools import wraps
from fastapi import HTTPException, Request

from utils.logger import get_logger, LogType
from utils.jwt_utils import decode_jwt_token, JWTError

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class UserRole(str, Enum):
    """用户角色枚举"""
    GUEST = "guest"  # 访客
    USER = "user"    # 普通用户
    ADMIN = "admin"  # 管理员


class Permission(str, Enum):
    """权限枚举"""
    # 系统配置权限
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"

    # 用户管理权限
    USER_READ = "user:read"
    USER_WRITE = "user:write"

    # 策略管理权限
    STRATEGY_READ = "strategy:read"
    STRATEGY_WRITE = "strategy:write"

    # 指标管理权限
    INDICATOR_READ = "indicator:read"
    INDICATOR_WRITE = "indicator:write"

    # 回测权限
    BACKTEST_READ = "backtest:read"
    BACKTEST_WRITE = "backtest:write"

    # 数据管理权限
    DATA_READ = "data:read"
    DATA_WRITE = "data:write"

    # AI功能权限
    AI_READ = "ai:read"
    AI_WRITE = "ai:write"

    # 系统日志权限
    LOG_READ = "log:read"

    # 交易所配置权限
    EXCHANGE_READ = "exchange:read"
    EXCHANGE_WRITE = "exchange:write"


# 角色权限映射
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.GUEST: {
        # 访客只读权限
        Permission.CONFIG_READ,
        Permission.STRATEGY_READ,
        Permission.INDICATOR_READ,
        Permission.BACKTEST_READ,
        Permission.DATA_READ,
        Permission.AI_READ,
        Permission.LOG_READ,
        Permission.EXCHANGE_READ,
    },
    UserRole.USER: {
        # 普通用户拥有大部分读写权限
        Permission.CONFIG_READ,
        Permission.CONFIG_WRITE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.STRATEGY_READ,
        Permission.STRATEGY_WRITE,
        Permission.INDICATOR_READ,
        Permission.INDICATOR_WRITE,
        Permission.BACKTEST_READ,
        Permission.BACKTEST_WRITE,
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.AI_READ,
        Permission.AI_WRITE,
        Permission.LOG_READ,
        Permission.EXCHANGE_READ,
        Permission.EXCHANGE_WRITE,
    },
    UserRole.ADMIN: {
        # 管理员拥有所有权限
        *Permission,
    },
}


def get_user_role_from_token(token: str) -> UserRole:
    """从token中获取用户角色

    Args:
        token: JWT token

    Returns:
        UserRole: 用户角色

    Raises:
        HTTPException: token无效时抛出
    """
    try:
        payload = decode_jwt_token(token)
        role_str = payload.get("role", "guest")
        return UserRole(role_str)
    except JWTError as e:
        logger.error(f"解析token获取角色失败: {e}")
        raise HTTPException(status_code=401, detail="无效的认证令牌")


def check_permission(user_role: UserRole, required_permission: Permission) -> bool:
    """检查用户角色是否拥有指定权限

    Args:
        user_role: 用户角色
        required_permission: 需要的权限

    Returns:
        bool: 是否有权限
    """
    user_permissions = ROLE_PERMISSIONS.get(user_role, set())
    return required_permission in user_permissions


def is_guest_user(request: Request) -> bool:
    """检查当前用户是否为未认证用户（无有效token）

    Args:
        request: FastAPI请求对象

    Returns:
        bool: 是否未认证
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        return True

    try:
        token = auth_header.split(" ")[1]
        payload = decode_jwt_token(token)
        role_str = payload.get("role", "guest")
        return role_str == "guest"
    except (IndexError, JWTError):
        return True


def get_current_user_id(request: Request) -> Optional[int]:
    """从JWT token中提取当前用户的user_id

    Args:
        request: FastAPI请求对象

    Returns:
        Optional[int]: 用户ID，未认证时返回None
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        return None

    try:
        token = auth_header.split(" ")[1]
        payload = decode_jwt_token(token)
        sub = payload.get("sub")
        if sub:
            try:
                return int(sub)
            except (ValueError, TypeError):
                return None
        return None
    except (IndexError, JWTError):
        return None


def require_permission_sync(permission: Permission):
    """同步版本的权限检查装饰器

    Args:
        permission: 需要的权限

    Returns:
        decorator: 装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request: Request, *args, **kwargs):
            # 从请求头中提取token
            auth_header = request.headers.get("Authorization", "")

            if not auth_header:
                raise HTTPException(
                    status_code=401,
                    detail={"code": 401, "message": "未提供认证令牌", "data": None}
                )

            # 提取token
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                raise HTTPException(
                    status_code=401,
                    detail={"code": 401, "message": "无效的认证令牌格式", "data": None}
                )

            # 获取用户角色
            user_role = get_user_role_from_token(token)

            # 检查权限
            if not check_permission(user_role, permission):
                logger.warning(f"权限不足: 角色={user_role.value}, 需要权限={permission.value}")
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": 403,
                        "message": "权限不足",
                        "data": {
                            "required_permission": permission.value,
                            "current_role": user_role.value,
                            "is_guest": user_role == UserRole.GUEST
                        }
                    }
                )

            # 记录访问日志
            logger.info(f"权限检查通过: 角色={user_role.value}, 权限={permission.value}")

            # 调用原始函数
            return func(request, *args, **kwargs)

        return wrapper
    return decorator


def get_current_user_info(request: Request) -> Dict:
    """获取当前用户信息

    Args:
        request: FastAPI请求对象

    Returns:
        Dict: 用户信息
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        return {"role": UserRole.GUEST.value, "is_guest": True}

    try:
        token = auth_header.split(" ")[1]
        payload = decode_jwt_token(token)
        role = payload.get("role", UserRole.GUEST.value)
        return {
            "sub": payload.get("sub"),
            "name": payload.get("name"),
            "role": role,
            "is_guest": role == UserRole.GUEST.value
        }
    except (IndexError, JWTError):
        return {"role": UserRole.GUEST.value, "is_guest": True}

