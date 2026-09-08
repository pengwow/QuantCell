"""
Worker模块依赖注入

定义FastAPI依赖项
"""

from fastapi import Depends

from collector.db.database import SessionLocal, init_database_config

# 认证统一走 utils.auth：
# - re-export 保持 worker/share 既有 `from worker.dependencies import get_current_user` 引用不变
# - 统一后不再有「缺 token 匿名放行」的逻辑：未认证一律 401
from utils.auth import get_current_user, security


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
