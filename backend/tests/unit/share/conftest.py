"""
Worker share 模块测试配置
"""

import gc
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# 模拟 worker.service 模块（模块级注入 + teardown 恢复，防全仓污染）
_mock_service_module = MagicMock()
_mock_service_module.get_workers = AsyncMock(return_value=[])
_mock_service_module.get_worker = AsyncMock(return_value={})
_mock_service_module.get_positions = AsyncMock(return_value=[])
_mock_service_module.get_orders = AsyncMock(return_value=[])
_saved_service = sys.modules.get("worker.service")
sys.modules["worker.service"] = _mock_service_module


def teardown_module() -> None:
    """恢复被注入的 worker.service。"""
    if _saved_service is None:
        sys.modules.pop("worker.service", None)
    else:
        sys.modules["worker.service"] = _saved_service


@pytest.fixture(scope="session")
def db_engine():
    """内存 SQLite 引擎"""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    # 确保 share 模型在 Base.metadata 中(独立于 _import_all_models 默认列表)
    import share.models
    from collector.db.database import Base, _import_all_models

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
    import json

    from worker.models import Worker

    worker = Worker(
        name="test-share-worker",
        description="test",
        status="stopped",
        strategy_id=None,
        strategy_name="TestStrategy",
        trading_config=json.dumps(
            {
                "exchange": "binance",
                "timeframe": "1h",
                "market_type": "spot",
                "trading_mode": "paper",
                "symbols_config": {
                    "type": "symbols",
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                },
            }
        ),
        config="{}",
    )
    db_session.add(worker)
    db_session.commit()
    db_session.refresh(worker)
    return worker


@pytest.fixture
def test_client(db_session):
    """FastAPI TestClient 复用 db_session

    默认覆盖 get_db / get_db_session / get_current_user,
    让测试无需登录即可调用受保护端点。

    故意使用 TestClient(app) 而非 `with TestClient(app) as client`,
    以跳过 FastAPI lifespan(后者会启动 ZMQ 监控等后台任务,
    在测试结束时不清理干净,会阻塞后续 async 测试的事件循环)。
    """
    from fastapi.testclient import TestClient

    # 显式触发 share 模块加载,确保 router 被注册
    import share.models
    import share.routes
    from collector.db.database import get_db
    from main import app
    from share import router as share_router
    from worker.dependencies import get_current_user, get_db_session

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_db_session():
        """share 路由使用 worker.dependencies.get_db_session"""
        try:
            yield db_session
        finally:
            pass

    # 默认匿名用户(未登录)— 不走 JWT 解码
    async def override_get_current_user():
        return {"user_id": "anonymous", "user_name": "Anonymous"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_db_session] = override_get_db_session
    # 默认覆盖:避免无 token 时直接 raise 401
    app.dependency_overrides[get_current_user] = override_get_current_user

    # 兜底:若 main 中没有注册 share_router,则手动注册
    # getattr 容错：新版 Starlette 的 _IncludedRouter 没有 .path 属性
    routes_paths = [getattr(r, "path", "") for r in app.routes]
    if not any("/api/share" in (p or "") for p in routes_paths):
        app.include_router(share_router)

    # 不走 lifespan,避免 ZMQ 监控 / 调度器等后台任务污染事件循环
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def cleanup_after_test():
    yield
    gc.collect()
