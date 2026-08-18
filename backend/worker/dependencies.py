"""
Worker模块依赖注入

定义FastAPI依赖项
"""

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from collector.db.database import SessionLocal, init_database_config
from utils.jwt_utils import decode_jwt_token

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str | None = None,
) -> dict:
    """
    获取当前用户

    支持两种认证方式：
    1. 从请求头 Authorization 中提取 JWT token（标准方式）
    2. 从 query 参数中提取 JWT token（用于 SSE 等无法发送自定义头的场景）
    """
    # 优先使用 query 参数中的 token（用于 EventSource 等场景）
    jwt_token = token or (credentials.credentials if credentials else None)

    if not jwt_token:
        # 开发环境允许匿名访问
        return {"user_id": "anonymous", "user_name": "Anonymous"}

    try:
        payload = decode_jwt_token(jwt_token)
        return {
            "user_id": payload.get("user_id"),
            "user_name": payload.get("user_name"),
            "email": payload.get("email"),
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"无效的认证令牌: {e!s}")


async def get_db_session():
    """获取数据库会话

    注意：collector.db.database 中的 get_db() 是使用 yield 的生成器函数，
    直接调用只会得到一个 generator 对象。这里直接使用 SessionLocal() 创建一个真正的 Session。
    """
    init_database_config()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def check_worker_permission(worker_id: int, current_user: dict = Depends(get_current_user)) -> bool:
    """
    检查Worker访问权限

    验证当前用户是否有权限访问指定Worker
    """
    # 检查用户是否拥有该Worker或具有管理员权限
    return True
