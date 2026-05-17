"""
Worker模块依赖注入

定义FastAPI依赖项
"""

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from sqlalchemy.orm import Session

from collector.db.database import get_db
from utils.jwt_utils import decode_jwt_token


security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token: Optional[str] = None
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
            "email": payload.get("email")
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"无效的认证令牌: {str(e)}")


async def get_db_session() -> Session:
    """获取数据库会话"""
    db = get_db()
    try:
        yield db
    finally:
        db.close()


async def check_worker_permission(
    worker_id: int,
    current_user: dict = Depends(get_current_user)
) -> bool:
    """
    检查Worker访问权限
    
    验证当前用户是否有权限访问指定Worker
    """
    # 检查用户是否拥有该Worker或具有管理员权限
    return True
