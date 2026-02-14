"""
Worker模块测试配置

提供测试所需的fixture和配置
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Generator

import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from collector.db.database import Base
from main import app


# 创建测试数据库引擎
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """设置测试数据库"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """创建测试数据库会话"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session) -> Generator[TestClient, None, None]:
    """创建测试客户端"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    # 模拟依赖
    from collector.db.database import get_db
    app.dependency_overrides[get_db] = override_get_db
    
    # 模拟JWT验证
    with patch("worker.dependencies.decode_jwt_token") as mock_decode:
        mock_decode.return_value = {
            "user_id": "test-user-001",
            "user_name": "Test User",
            "email": "test@example.com"
        }
        
        with TestClient(app) as test_client:
            yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_worker_create_request():
    """示例Worker创建请求"""
    return {
        "name": "BTC Strategy Worker",
        "description": "BTC/USDT 1小时策略",
        "strategy_id": 1,
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "market_type": "spot",
        "trading_mode": "paper",
        "cpu_limit": 2,
        "memory_limit": 1024,
        "env_vars": {"API_KEY": "test_key"},
        "config": {"risk_level": "low"}
    }


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
