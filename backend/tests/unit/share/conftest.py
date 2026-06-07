"""
Worker share 模块测试配置
"""
import asyncio
import gc
import sys
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')


# 模拟 worker.service 模块
_mock_service_module = MagicMock()
_mock_service_module.get_workers = AsyncMock(return_value=[])
_mock_service_module.get_worker = AsyncMock(return_value={})
_mock_service_module.get_positions = AsyncMock(return_value=[])
_mock_service_module.get_orders = AsyncMock(return_value=[])
sys.modules['worker.service'] = _mock_service_module


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    if not loop.is_closed():
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


@pytest.fixture(scope="session")
def db_engine():
    """内存 SQLite 引擎"""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from collector.db.database import Base, _import_all_models

    # 确保 share 模型在 Base.metadata 中（独立于 _import_all_models 默认列表）
    import share.models  # noqa: F401

    _import_all_models()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    from sqlalchemy.orm import sessionmaker

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    connection = db_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def sample_worker(db_session):
    """插入一个测试用 worker"""
    from worker.models import Worker
    import json

    worker = Worker(
        name="test-share-worker",
        description="test",
        status="stopped",
        strategy_id=None,
        strategy_name="TestStrategy",
        trading_config=json.dumps({
            "exchange": "binance",
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper",
            "symbols_config": {
                "type": "symbols",
                "symbols": ["BTCUSDT", "ETHUSDT"],
            },
        }),
        config="{}",
    )
    db_session.add(worker)
    db_session.commit()
    db_session.refresh(worker)
    return worker


@pytest.fixture(autouse=True)
def cleanup_after_test():
    yield
    gc.collect()
