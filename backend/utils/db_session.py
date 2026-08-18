"""
统一数据库会话管理工具

提供统一的数据库会话管理方式，消除重复的 SessionLocal() 创建和 db.close() 样板代码。

主要功能:
    - get_db_session(): 上下文管理器，自动处理数据库初始化和会话关闭

使用示例:
    >>> from utils.db_session import get_db_session
    >>> with get_db_session() as db:
    ...     result = db.query(Model).filter(...).all()
    ...     return [item.to_dict() for item in result]

作者: QuantCell Team
版本: 1.0.0
日期: 2026-05-20
"""

from contextlib import contextmanager
from typing import TYPE_CHECKING

from utils.logger import LogType, get_logger

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.orm import Session

logger = get_logger(__name__, LogType.APPLICATION)


@contextmanager
def get_db_session() -> Generator[Session]:
    """
    获取数据库会话的上下文管理器

    自动完成以下工作:
    1. 调用 init_database_config() 确保数据库配置已初始化
    2. 创建 SQLAlchemy 会话
    3. 在退出时自动关闭会话，释放数据库连接

    会话的提交/回滚由调用方显式控制，以兼容各种业务场景。

    使用示例:
        # 只读查询
        with get_db_session() as db:
            items = db.query(SomeModel).all()
            return [item.to_dict() for item in items]

        # 写操作
        with get_db_session() as db:
            db.add(new_record)
            db.commit()

        # 带异常回滚的写操作
        with get_db_session() as db:
            try:
                db.add(new_record)
                db.commit()
            except Exception:
                db.rollback()
                raise

    注意:
        - 上下文管理器退出时一定会关闭会话 (close)，无论是否发生异常
        - 不会自动提交或回滚，由调用方根据业务逻辑决定
        - init_database_config() 是幂等的，多次调用不会重复初始化
    """
    from collector.db.database import SessionLocal, init_database_config

    init_database_config()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def use_db_session(db_session: Session | None = None) -> Generator[Session]:
    """
    使用已有会话或创建新会话的上下文管理器

    适用于函数接受可选的 db_session 参数时，统一处理会话生命周期。

    当 db_session 不为 None 时，直接使用已有会话（不关闭）；
    当 db_session 为 None 时，创建新会话并在退出时自动关闭。

    使用示例:
        def my_func(self, args, db_session=None):
            with use_db_session(db_session) as db:
                result = db.query(Model).all()
                return result

        # 调用方可以传入已有会话
        with get_db_session() as shared_db:
            my_func(args, db_session=shared_db)
            other_func(args, db_session=shared_db)

        # 或者不传，自动创建新会话
        my_func(args)
    """
    if db_session is not None:
        yield db_session
    else:
        with get_db_session() as db:
            yield db
