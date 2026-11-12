"""
RBAC (Role-Based Access Control) 权限控制模块
实现基于角色的访问控制，支持访客和普通用户角色
"""

from enum import StrEnum
from functools import wraps

from fastapi import HTTPException, Request

from config import is_auth_check_disabled
from utils.jwt_utils import JWTError, TokenExpiredError, decode_jwt_token
from utils.logger import LogType, get_logger

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class UserRole(StrEnum):
    """用户角色枚举"""

    GUEST = "guest"  # 访客
    USER = "user"  # 普通用户
    ADMIN = "admin"  # 管理员


class Permission(StrEnum):
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

    # Worker 管理权限（P1-07 权限枚举落地，operate=启停/归档/优化等生命周期操作）
    WORKER_READ = "worker:read"
    WORKER_WRITE = "worker:write"
    WORKER_OPERATE = "worker:operate"


# 角色权限映射
ROLE_PERMISSIONS: dict[UserRole, set[Permission]] = {
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
        Permission.WORKER_READ,
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
        Permission.WORKER_READ,
        Permission.WORKER_WRITE,
        Permission.WORKER_OPERATE,
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
    """检查当前用户是否为访客角色

    仅在 token 有效且 role=guest 时返回 True（由调用方返回 403）。
    未携带 token / 格式错误 / token 无效或过期时抛 401：这些是"未认证"
    而非"访客"，若伪装成访客返回 403，前端不会触发重新登录，用户只能看到
    无法自愈的"权限不足"（登录过期后 AI 生成指标保存被拦即此场景）。
    HTTP 401 会被前端拦截器捕获并自动跳转登录页。

    config.toml 的 [security].auth_enabled = false 时跳过全部校验
    （开发调试用），直接按非访客放行；生产环境由 is_auth_check_disabled
    强制回收该开关。
    """
    if is_auth_check_disabled():
        return False

    auth_header = request.headers.get("Authorization", "")

    if not auth_header:
        raise HTTPException(status_code=401, detail={"code": 401, "message": "未登录，请先登录", "data": None})

    try:
        token = auth_header.split(" ")[1]
        payload = decode_jwt_token(token)
    except IndexError:
        raise HTTPException(
            status_code=401, detail={"code": 401, "message": "无效的认证令牌格式，请重新登录", "data": None}
        )
    except JWTError as e:
        msg = "登录已过期，请重新登录" if isinstance(e, TokenExpiredError) else "无效的认证令牌，请重新登录"
        logger.warning(f"权限检查拦截: {msg} ({e})")
        raise HTTPException(status_code=401, detail={"code": 401, "message": msg, "data": None})

    # 有效 token 缺少 role 字段时按访客处理（与 get_user_role_from_token 的默认一致）
    return payload.get("role", "guest") == "guest"


def get_current_user_id(request: Request) -> int | None:
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
            except ValueError, TypeError:
                return None
        return None
    except IndexError, JWTError:
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
                    detail={"code": 401, "message": "未提供认证令牌", "data": None},
                )

            # 提取token
            try:
                token = auth_header.split(" ")[1]
            except IndexError:
                raise HTTPException(
                    status_code=401,
                    detail={"code": 401, "message": "无效的认证令牌格式", "data": None},
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
                            "is_guest": user_role == UserRole.GUEST,
                        },
                    },
                )

            # 记录访问日志
            logger.info(f"权限检查通过: 角色={user_role.value}, 权限={permission.value}")

            # 调用原始函数
            return func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_permission(permission: Permission):
    """FastAPI 依赖形式的权限检查（P1-07 权限枚举落地）

    用法（逐路由灰度挂载）：
        @router.post("", dependencies=[Depends(require_permission(Permission.WORKER_WRITE))])

    开关 rbac.enforcement_enabled（config.toml，默认 false）：
    - off：完全旁路直接放行，行为与未挂载一致（单用户模式全通）
    - on：解析 Bearer token 取角色并校验权限；token 缺失/无效按"未认证"抛 401
      （与 is_guest_user 语义一致，让前端拦截器触发重新登录），权限不足抛 403。
      拒绝与通过均写审计日志（user/permission/resource/result），复用 utils/logger。
    """

    async def dependency(request: Request) -> None:
        # 函数内 import：utils.config_manager 顶部会拉起 collector.db.database
        # → collector.api → worker/__init__ → worker.routes → utils.rbac，
        # 形成 utils.rbac 自环（模块初始化未完成时 Permission 尚不存在）；
        # 请求期各模块已就绪，函数内导入安全
        from utils.config_manager import get_value as get_config_value

        if not get_config_value("rbac.enforcement_enabled", False):
            return

        auth_header = request.headers.get("Authorization", "")
        if not auth_header:
            raise HTTPException(status_code=401, detail={"code": 401, "message": "未登录，请先登录", "data": None})

        try:
            token = auth_header.split(" ")[1]
        except IndexError:
            raise HTTPException(
                status_code=401, detail={"code": 401, "message": "无效的认证令牌格式，请重新登录", "data": None}
            )

        # P2-06：Agent Token（qctk_ 前缀）不走 JWT/角色体系，按令牌 scope 判定：
        # read 令牌只放行读权限端点，write 令牌可访问写权限端点。
        if token.startswith("qctk_"):
            # 函数内 import：与下方 config_manager 同理，避免模块初始化期拉起
            # collector.db（agent.tokens → agent.models）形成导入环
            from agent.tokens import authenticate_agent_token

            agent_row = authenticate_agent_token(token)
            if agent_row is None:
                raise HTTPException(
                    status_code=401,
                    detail={"code": 401, "message": "代理令牌无效、已撤销或已过期", "data": None},
                )
            write_permission = permission in (Permission.AI_WRITE, Permission.WORKER_OPERATE, Permission.SYSTEM_ADMIN)
            if write_permission and agent_row.scope != "write":
                logger.warning(f"RBAC 拦截: agent_token={agent_row.id} scope={agent_row.scope} 需要写权限")
                raise HTTPException(
                    status_code=403,
                    detail={"code": 403, "message": "权限不足：只读代理令牌不可执行写操作", "data": None},
                )
            return

        try:
            payload = decode_jwt_token(token)
        except TokenExpiredError as e:
            logger.warning(f"RBAC 拦截: 登录已过期, resource={request.url.path} ({e})")
            raise HTTPException(
                status_code=401, detail={"code": 401, "message": "登录已过期，请重新登录", "data": None}
            )
        except JWTError as e:
            logger.warning(f"RBAC 拦截: 无效认证令牌, resource={request.url.path} ({e})")
            raise HTTPException(
                status_code=401, detail={"code": 401, "message": "无效的认证令牌，请重新登录", "data": None}
            )

        user_role = UserRole(payload.get("role", "guest"))
        resource = request.url.path

        if not check_permission(user_role, permission):
            logger.warning(
                f"RBAC 拒绝: user={payload.get('sub')}, role={user_role.value}, "
                f"permission={permission.value}, resource={resource}, result=denied"
            )
            raise HTTPException(
                status_code=403,
                detail={
                    "code": 403,
                    "message": "权限不足",
                    "data": {
                        "required_permission": permission.value,
                        "current_role": user_role.value,
                        "is_guest": user_role == UserRole.GUEST,
                    },
                },
            )

        logger.info(
            f"RBAC 通过: user={payload.get('sub')}, role={user_role.value}, "
            f"permission={permission.value}, resource={resource}, result=allowed"
        )

    return dependency


def get_current_user_info(request: Request) -> dict:
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
            "is_guest": role == UserRole.GUEST.value,
        }
    except IndexError, JWTError:
        return {"role": UserRole.GUEST.value, "is_guest": True}
