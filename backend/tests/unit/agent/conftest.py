"""P2-06 单测公共夹具：in-memory 库 + 测试用 SessionLocal 替身。

agent.tokens / agent.core.audit 运行期从 collector.db.database 取 SessionLocal，
测试直接替换该模块属性即可让 service 代码打到测试库。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from collector.db.database import Base, _import_all_models


@pytest.fixture(scope="session")
def agent_db_engine():
    _import_all_models()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def agent_session_factory(agent_db_engine, monkeypatch):
    """函数级 sessionmaker，并替换 collector.db.database.SessionLocal"""
    factory = sessionmaker(autocommit=False, autoflush=False, bind=agent_db_engine)
    from collector.db import database as db_module

    monkeypatch.setattr(db_module, "SessionLocal", factory)
    return factory
