"""
Worker模块测试配置 - 优化版本

解决测试挂起和内存泄漏问题
"""

import pytest
import asyncio
import tracemalloc
import gc
import signal
import sys
from datetime import datetime
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Generator
from contextlib import contextmanager

sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')

# 启动内存跟踪
tracemalloc.start()


class TimeoutError(Exception):
    """自定义超时异常"""
    pass


def timeout_handler(signum, frame):
    """信号处理函数"""
    raise TimeoutError("测试执行超时")


@contextmanager
def timeout(seconds=30):
    """
    超时上下文管理器 - 使用信号机制
    
    Args:
        seconds: 超时时间（秒）
    """
    # 设置信号处理
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)  # 取消闹钟
        signal.signal(signal.SIGALRM, old_handler)


@contextmanager
def memory_limit(max_size_mb: int = 200):
    """
    内存限制上下文管理器
    
    Args:
        max_size_mb: 最大内存使用限制(MB)
    """
    gc.collect()  # 强制垃圾回收
    start_mem = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB
    
    yield
    
    gc.collect()
    end_mem = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB
    
    if end_mem - start_mem > max_size_mb:
        raise MemoryError(f"内存使用超过限制: {end_mem - start_mem:.2f}MB > {max_size_mb}MB")


# 在导入任何模块之前，先创建 mock service 模块
_mock_service_module = MagicMock()
_mock_service_module.start_worker_async = AsyncMock(return_value="task-123")
_mock_service_module.stop_worker = AsyncMock(return_value=True)
_mock_service_module.restart_worker_async = AsyncMock(return_value="task-456")
_mock_service_module.pause_worker = AsyncMock(return_value=True)
_mock_service_module.resume_worker = AsyncMock(return_value=True)
_mock_service_module.get_worker_status = AsyncMock(return_value={
    "worker_id": 1,
    "status": "running",
    "is_healthy": True
})
_mock_service_module.health_check = AsyncMock(return_value={
    "worker_id": 1,
    "is_healthy": True
})
_mock_service_module.get_worker_metrics = AsyncMock(return_value={
    "worker_id": 1,
    "cpu_usage": 15.5,
    "memory_usage": 45.2
})
_mock_service_module.deploy_strategy = AsyncMock(return_value={
    "deployed": True,
    "strategy_id": 1,
    "worker_id": 1
})
_mock_service_module.undeploy_strategy = AsyncMock(return_value={
    "undeployed": True,
    "worker_id": 1
})
_mock_service_module.update_strategy_params = AsyncMock(return_value=True)
_mock_service_module.get_positions = AsyncMock(return_value=[])
_mock_service_module.get_orders = AsyncMock(return_value=[])
_mock_service_module.send_trading_signal = AsyncMock(return_value={
    "sent": True,
    "signal_id": "test-signal-id"
})
_mock_service_module.stream_logs = AsyncMock()
_mock_service_module.batch_operation = AsyncMock(return_value={
    "success": [1, 2],
    "failed": {},
    "total": 2
})

# 预先注入 mock 模块到 sys.modules
# 这需要在导入 main 之前完成
sys.modules['worker.service'] = _mock_service_module


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环 - 会话级别"""
    loop = asyncio.new_event_loop()
    yield loop
    
    # 清理事件循环
    if not loop.is_closed():
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


@pytest.fixture(scope="session")
def db_engine():
    """延迟创建测试数据库引擎"""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from collector.db.database import Base
    
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    yield engine
    
    # 清理
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """创建测试数据库会话 - 函数级别隔离"""
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


@pytest.fixture(scope="function")
def client(db_session):
    """
    创建测试客户端 - 完全模拟模式
    
    使用内存监控防止内存泄漏
    完全模拟 WorkerService 避免 ZeroMQ 初始化
    使用超时保护防止测试挂起
    """
    with timeout(30):  # 30秒超时保护
        with memory_limit(max_size_mb=100):
            # 延迟导入 - 避免在导入时初始化大量资源
            from fastapi.testclient import TestClient
            from collector.db.database import get_db
            
            # 在导入 main 之前，确保 mock 已经注入
            # 同时 mock worker.api.routes.service
            import worker.api.routes
            worker.api.routes.service = _mock_service_module
            
            from main import app
            
            def override_get_db():
                try:
                    yield db_session
                finally:
                    pass
            
            # 设置依赖覆盖
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
            
            # 清理依赖覆盖
            app.dependency_overrides.clear()
            
            # 强制垃圾回收
            gc.collect()


@pytest.fixture
def mock_current_user():
    """模拟当前用户"""
    return {
        "user_id": "test-user-001",
        "user_name": "Test User",
        "email": "test@example.com"
    }


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


@pytest.fixture
def mock_worker_service():
    """模拟Worker服务 - 完全隔离"""
    mock = MagicMock()
    mock.start_worker_async = AsyncMock(return_value="task-123")
    mock.stop_worker = AsyncMock(return_value=True)
    mock.restart_worker_async = AsyncMock(return_value="task-456")
    mock.pause_worker = AsyncMock(return_value=True)
    mock.resume_worker = AsyncMock(return_value=True)
    mock.get_worker_status = AsyncMock(return_value={
        "worker_id": 1,
        "status": "running",
        "is_healthy": True
    })
    mock.health_check = AsyncMock(return_value={
        "worker_id": 1,
        "is_healthy": True
    })
    return mock


@pytest.fixture(autouse=True)
def cleanup_after_test():
    """每个测试后自动清理"""
    yield
    
    # 强制垃圾回收
    gc.collect()
    
    # 清理未关闭的事件循环
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        pass


# pytest钩子 - 添加超时和内存监控
def pytest_collection_modifyitems(config, items):
    """修改测试项 - 添加超时标记"""
    for item in items:
        # 为所有测试添加30秒超时
        item.add_marker(pytest.mark.timeout(30))


def pytest_runtest_call(item):
    """测试调用前记录内存"""
    gc.collect()
    item._memory_before = tracemalloc.get_traced_memory()[0]


def pytest_runtest_teardown(item, nextitem):
    """测试结束后检查内存"""
    gc.collect()
    memory_after = tracemalloc.get_traced_memory()[0]
    memory_diff = (memory_after - getattr(item, '_memory_before', 0)) / 1024 / 1024  # MB
    
    # 如果内存增长超过50MB，发出警告
    if memory_diff > 50:
        print(f"\n警告: 测试 {item.name} 内存使用增加 {memory_diff:.2f}MB")
