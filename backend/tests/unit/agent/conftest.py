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


@pytest.fixture(scope="session", autouse=True)
def _restore_real_worker_service():
    """隔离 tests/unit/worker/conftest.py 的 sys.modules 污染。

    该 conftest 在**收集期**把 ``sys.modules["worker.service"]`` 永久替换成
    MagicMock（供 worker 路由测试用，从不还原）。同一次 pytest 会话先跑
    agent 测试时，daily_review 的 ``get_positions_sync`` 会拿到这个 mock，
    持仓恒为空 → 复盘/建议断言假失败。

    这里在 agent 测试执行期间换回真实模块，会话结束时还原 mock，
    不影响随后运行的 worker 测试。
    """
    import importlib
    import sys

    mocked = sys.modules.pop("worker.service", None)
    importlib.import_module("worker.service")
    yield
    if mocked is not None:
        sys.modules["worker.service"] = mocked
