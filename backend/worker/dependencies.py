"""
Worker模块依赖注入

定义FastAPI依赖项
"""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from collector.db.database import SessionLocal, init_database_config

# 认证统一走 utils.auth：
# - re-export 保持 worker/share 既有 `from worker.dependencies import get_current_user` 引用不变
# - 统一后不再有「缺 token 匿名放行」的逻辑：未认证一律 401
from utils.auth import get_current_user, security
from utils.logger import LogType, get_logger

# 这些角色不做归属过滤：admin 是平台管理角色；agent 是服务间令牌
# （sub=agent_token:*），供后端内部调用（如智能体拉取 worker 上下文）
# 归属口径唯一定义处：routes 的列表过滤与 check_worker_permission 共用
_OWNER_FILTER_EXEMPT_ROLES = {"admin", "agent"}


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


_worker_perm_logger = get_logger(__name__, LogType.APPLICATION)


async def check_worker_permission(
    worker_id: int,
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(get_current_user),
) -> None:
    """检查当前用户对指定 Worker 的访问权限（越权防护，P0-1 落地）。

    规则与列表接口的 _worker_owner_filter 保持同一口径：
    - 鉴权关闭（单机模式，current_user 无 role）：不过滤
    - admin / agent 角色放行
    - 其余角色只能是 worker.owner_id 本人，否则 403；worker 不存在按 404
      （避免向无权用户泄露「该 id 存在」这一信息）

    用法：挂到所有 /{worker_id}/... 端点的 dependencies 里，依赖声明同名
    worker_id 参数由 FastAPI 自动从路径注入。
    """
    role = current_user.get("role")
    if not role:
        # 鉴权关闭路径：单机模式无「用户」概念，不校验
        return
    if role in _OWNER_FILTER_EXEMPT_ROLES:
        return

    from worker import crud  # 局部导入防止 dependencies ↔ crud 循环依赖

    worker = crud.get_worker(db, worker_id)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} 不存在")
    try:
        owner_id = int(current_user.get("user_id"))
    except (TypeError, ValueError):
        # user_id 非数字（异常 token）：置为不可能匹配的值，宁拒不放
        owner_id = -1
    if worker.owner_id != owner_id:
        _worker_perm_logger.warning(
            f"[Worker权限] 越权访问被拒: worker_id={worker_id}, owner_id={worker.owner_id}, user_id={current_user.get('user_id')}"
        )
        raise HTTPException(status_code=403, detail="无权访问该 Worker")
