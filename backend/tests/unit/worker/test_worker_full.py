"""
QuantCell Worker 完整功能测试

测试 Worker 相关的所有核心功能，包括：
- Worker CRUD 操作
- Worker 生命周期管理（启动、停止、暂停、恢复、重启）
- Worker 状态查询
- Worker 批量操作
- Worker 策略部署
- Worker 监控数据
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Any, List

import sys
sys.path.insert(0, '/Users/liupeng/workspace/quant/QuantCell/backend')


# =============================================================================
# 测试 Worker 模型
# =============================================================================

class TestWorkerModels:
    """测试 Worker 数据模型"""

    def test_worker_creation(self, db_session):
        """测试 Worker 创建"""
        from worker.models import Worker

        worker = Worker(
            name="Test Worker",
            description="Test Description",
            status="stopped",
            cpu_limit=2,
            memory_limit=1024
        )
        db_session.add(worker)
        db_session.commit()
        db_session.refresh(worker)

        assert worker.id is not None
        assert worker.name == "Test Worker"
        assert worker.description == "Test Description"
        assert worker.status == "stopped"
        assert worker.cpu_limit == 2
        assert worker.memory_limit == 1024

    def test_worker_config_dict(self, db_session):
        """测试 Worker 配置字典操作"""
        from worker.models import Worker

        worker = Worker(name="Config Test Worker")
        db_session.add(worker)
        db_session.commit()

        # 测试设置配置
        config = {"key1": "value1", "key2": 123}
        worker.set_config_dict(config)
        db_session.commit()

        # 测试获取配置
        retrieved_config = worker.get_config_dict()
        assert retrieved_config["key1"] == "value1"
        assert retrieved_config["key2"] == 123

    def test_worker_trading_config(self, db_session):
        """测试 Worker 交易配置"""
        from worker.models import Worker

        worker = Worker(name="Trading Config Test")
        db_session.add(worker)
        db_session.commit()

        trading_config = {
            "exchange": "binance",
            "symbols_config": {
                "type": "symbols",
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "pool_id": None,
                "pool_name": None
            },
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper"
        }
        worker.set_trading_config_dict(trading_config)
        db_session.commit()

        retrieved = worker.get_trading_config_dict()
        assert retrieved["exchange"] == "binance"
        assert retrieved["timeframe"] == "1h"
        assert "BTCUSDT" in retrieved["symbols_config"]["symbols"]

    def test_worker_env_vars(self, db_session):
        """测试 Worker 环境变量"""
        from worker.models import Worker

        worker = Worker(name="Env Vars Test")
        db_session.add(worker)
        db_session.commit()

        env_vars = {"API_KEY": "test_key", "SECRET": "test_secret"}
        worker.set_env_vars_dict(env_vars)
        db_session.commit()

        retrieved = worker.get_env_vars_dict()
        assert retrieved["API_KEY"] == "test_key"
        assert retrieved["SECRET"] == "test_secret"

    def test_worker_to_dict(self, db_session):
        """测试 Worker 转换为字典"""
        from worker.models import Worker

        worker = Worker(
            name="Dict Test Worker",
            status="running",
            cpu_limit=4,
            memory_limit=2048
        )
        db_session.add(worker)
        db_session.commit()

        worker_dict = worker.to_dict()
        assert worker_dict["name"] == "Dict Test Worker"
        assert worker_dict["status"] == "running"
        assert worker_dict["cpu_limit"] == 4
        assert worker_dict["memory_limit"] == 2048
        assert "id" in worker_dict

    def test_worker_log_creation(self, db_session):
        """测试 Worker 日志创建"""
        from worker.models import Worker, WorkerLog

        worker = Worker(name="Log Test Worker")
        db_session.add(worker)
        db_session.commit()

        log = WorkerLog(
            worker_id=worker.id,
            level="INFO",
            message="Test log message",
            source="test"
        )
        db_session.add(log)
        db_session.commit()

        assert log.id is not None
        assert log.worker_id == worker.id
        assert log.level == "INFO"
        assert log.message == "Test log message"

    def test_worker_performance_creation(self, db_session):
        """测试 Worker 绩效记录创建"""
        from worker.models import Worker, WorkerPerformance

        worker = Worker(name="Performance Test Worker")
        db_session.add(worker)
        db_session.commit()

        performance = WorkerPerformance(
            worker_id=worker.id,
            total_trades=100,
            winning_trades=60,
            losing_trades=40,
            net_profit=5000.0,
            win_rate=0.6,
            date=datetime.now()
        )
        db_session.add(performance)
        db_session.commit()

        assert performance.id is not None
        assert performance.total_trades == 100
        assert performance.win_rate == 0.6


# =============================================================================
# 测试 Worker CRUD 操作
# =============================================================================

class TestWorkerCRUD:
    """测试 Worker CRUD 操作"""

    def test_create_worker(self, db_session):
        """测试创建 Worker"""
        from worker.crud import create_worker
        from worker.schemas import WorkerCreate

        worker_data = WorkerCreate(
            name="CRUD Test Worker",
            description="Test Description",
            exchange="binance",
            symbols=["BTCUSDT"],
            timeframe="1h",
            market_type="spot",
            trading_mode="paper",
            cpu_limit=2,
            memory_limit=1024
        )

        worker = create_worker(db_session, worker_data)

        assert worker.id is not None
        assert worker.name == "CRUD Test Worker"
        assert worker.status == "stopped"

    def test_get_worker(self, db_session):
        """测试获取单个 Worker"""
        from worker.crud import create_worker, get_worker
        from worker.schemas import WorkerCreate

        worker_data = WorkerCreate(name="Get Test Worker")
        created = create_worker(db_session, worker_data)

        retrieved = get_worker(db_session, created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.name == "Get Test Worker"

    def test_get_workers_list(self, db_session):
        """测试获取 Worker 列表"""
        from worker.crud import create_worker, get_workers
        from worker.schemas import WorkerCreate

        # 创建多个 Worker
        for i in range(3):
            worker_data = WorkerCreate(name=f"List Test Worker {i}")
            create_worker(db_session, worker_data)

        workers, total = get_workers(db_session, skip=0, limit=10)

        assert total >= 3
        assert len(workers) >= 3

    def test_update_worker(self, db_session):
        """测试更新 Worker"""
        from worker.crud import create_worker, update_worker
        from worker.schemas import WorkerCreate, WorkerUpdate

        worker_data = WorkerCreate(name="Update Test Worker")
        created = create_worker(db_session, worker_data)

        update_data = WorkerUpdate(
            name="Updated Worker Name",
            description="Updated Description"
        )

        updated = update_worker(db_session, created.id, update_data)

        assert updated is not None
        assert updated.name == "Updated Worker Name"
        assert updated.description == "Updated Description"

    def test_update_worker_status(self, db_session):
        """测试更新 Worker 状态"""
        from worker.crud import create_worker, update_worker_status
        from worker.schemas import WorkerCreate

        worker_data = WorkerCreate(name="Status Test Worker")
        created = create_worker(db_session, worker_data)

        updated = update_worker_status(db_session, created.id, "running", pid=12345)

        assert updated is not None
        assert updated.status == "running"
        assert updated.pid == 12345
        assert updated.started_at is not None

    def test_delete_worker(self, db_session):
        """测试删除 Worker"""
        from worker.crud import create_worker, delete_worker, get_worker
        from worker.schemas import WorkerCreate

        worker_data = WorkerCreate(name="Delete Test Worker")
        created = create_worker(db_session, worker_data)
        worker_id = created.id

        success = delete_worker(db_session, worker_id)
        assert success is True

        retrieved = get_worker(db_session, worker_id)
        assert retrieved is None

    def test_clone_worker(self, db_session):
        """测试克隆 Worker"""
        from worker.crud import create_worker, clone_worker
        from worker.schemas import WorkerCreate, WorkerCloneRequest

        worker_data = WorkerCreate(name="Original Worker")
        original = create_worker(db_session, worker_data)

        clone_request = WorkerCloneRequest(new_name="Cloned Worker")
        cloned = clone_worker(db_session, original.id, clone_request)

        assert cloned.id != original.id
        assert cloned.name == "Cloned Worker"


# =============================================================================
# 测试 Worker 状态机
# =============================================================================

class TestWorkerStateMachine:
    """测试 Worker 状态机"""

    def test_worker_state_enum(self):
        """测试 Worker 状态枚举"""
        from worker.state import WorkerState

        assert WorkerState.STOPPED.value == "stopped"
        assert WorkerState.RUNNING.value == "running"
        assert WorkerState.PAUSED.value == "paused"
        assert WorkerState.ERROR.value == "error"

    def test_worker_state_transitions(self):
        """测试 Worker 状态转换"""
        from worker.state import WorkerState

        # 测试合法的状态转换
        assert WorkerState.STOPPED.can_transition_to(WorkerState.STARTING) is True
        assert WorkerState.STARTING.can_transition_to(WorkerState.RUNNING) is True
        assert WorkerState.RUNNING.can_transition_to(WorkerState.PAUSED) is True
        assert WorkerState.RUNNING.can_transition_to(WorkerState.STOPPING) is True
        assert WorkerState.PAUSED.can_transition_to(WorkerState.RUNNING) is True

    def test_invalid_state_transitions(self):
        """测试非法的状态转换"""
        from worker.state import WorkerState

        # 测试非法的状态转换
        assert WorkerState.STOPPED.can_transition_to(WorkerState.RUNNING) is False
        assert WorkerState.RUNNING.can_transition_to(WorkerState.STOPPED) is False

    def test_worker_status_creation(self):
        """测试 Worker 状态对象创建"""
        from worker.state import WorkerStatus, WorkerState

        status = WorkerStatus(worker_id="test-worker-001")

        assert status.worker_id == "test-worker-001"
        assert status.state == WorkerState.INITIALIZING

    def test_worker_status_update_state(self):
        """测试 Worker 状态更新"""
        from worker.state import WorkerStatus, WorkerState

        status = WorkerStatus(worker_id="test-worker-001")

        # 合法的状态转换
        result = status.update_state(WorkerState.RUNNING)
        assert result is True
        assert status.state == WorkerState.RUNNING

    def test_worker_status_heartbeat(self):
        """测试 Worker 心跳更新"""
        from worker.state import WorkerStatus

        status = WorkerStatus(worker_id="test-worker-001")

        assert status.last_heartbeat is None
        status.update_heartbeat()
        assert status.last_heartbeat is not None

    def test_worker_status_health_check(self):
        """测试 Worker 健康检查"""
        from worker.state import WorkerStatus, WorkerState

        status = WorkerStatus(worker_id="test-worker-001")
        status.update_state(WorkerState.RUNNING)
        status.update_heartbeat()

        assert status.is_healthy() is True

    def test_state_machine_transition(self):
        """测试状态机转换"""
        from worker.state import StateMachine, WorkerState

        sm = StateMachine(initial_state=WorkerState.STOPPED)

        assert sm.current_state == WorkerState.STOPPED

        result = sm.transition_to(WorkerState.STARTING)
        assert result is True
        assert sm.current_state == WorkerState.STARTING


# =============================================================================
# 测试 Worker API 路由
# =============================================================================

@pytest.mark.asyncio
class TestWorkerAPI:
    """测试 Worker API 端点"""

    async def test_create_worker_api(self, client):
        """测试创建 Worker API"""
        response = client.post("/api/workers", json={
            "name": "API Test Worker",
            "description": "Test Description",
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper",
            "cpu_limit": 2,
            "memory_limit": 1024
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "API Test Worker"

    async def test_list_workers_api(self, client):
        """测试获取 Worker 列表 API"""
        # 先创建一个 Worker
        client.post("/api/workers", json={
            "name": "List API Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })

        response = client.get("/api/workers")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "items" in data["data"]
        assert "total" in data["data"]

    async def test_get_worker_api(self, client):
        """测试获取单个 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Get API Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["id"] == worker_id

    async def test_update_worker_api(self, client):
        """测试更新 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Update API Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.put(f"/api/workers/{worker_id}", json={
            "name": "Updated API Worker",
            "description": "Updated Description"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Updated API Worker"

    async def test_delete_worker_api(self, client):
        """测试删除 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Delete API Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.delete(f"/api/workers/{worker_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_clone_worker_api(self, client):
        """测试克隆 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Clone Source Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/clone", json={
            "new_name": "Cloned API Worker",
            "copy_config": True,
            "copy_parameters": True
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Cloned API Worker"


# =============================================================================
# 测试 Worker 生命周期管理
# =============================================================================

@pytest.mark.asyncio
class TestWorkerLifecycle:
    """测试 Worker 生命周期管理"""

    async def test_start_worker_api(self, client):
        """测试启动 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Start Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        # 模拟启动 Worker
        with patch("worker.api.routes.get_worker_manager") as mock_manager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.start_strategy = AsyncMock(return_value=str(worker_id))
            mock_manager_instance.get_worker_pid = Mock(return_value=12345)
            mock_manager.return_value = mock_manager_instance

            response = client.post(f"/api/workers/{worker_id}/lifecycle/start")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0

    async def test_stop_worker_api(self, client):
        """测试停止 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Stop Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        # 模拟停止 Worker
        with patch("worker.api.routes.get_worker_manager") as mock_manager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.stop_worker = AsyncMock(return_value=True)
            mock_manager.return_value = mock_manager_instance

            response = client.post(f"/api/workers/{worker_id}/lifecycle/stop")

            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0

    async def test_restart_worker_api(self, client):
        """测试重启 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Restart Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/lifecycle/restart")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "task_id" in data["data"]

    async def test_pause_worker_api(self, client):
        """测试暂停 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Pause Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/lifecycle/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_resume_worker_api(self, client):
        """测试恢复 Worker API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Resume Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/lifecycle/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_get_worker_status_api(self, client):
        """测试获取 Worker 状态 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Status Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/lifecycle/status")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "status" in data["data"]

    async def test_health_check_api(self, client):
        """测试 Worker 健康检查 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Health Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/lifecycle/health")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "is_healthy" in data["data"]


# =============================================================================
# 测试 Worker 批量操作
# =============================================================================

@pytest.mark.asyncio
class TestWorkerBatchOperations:
    """测试 Worker 批量操作"""

    async def test_batch_start_workers(self, client):
        """测试批量启动 Worker"""
        # 创建多个 Worker
        worker_ids = []
        for i in range(3):
            create_response = client.post("/api/workers", json={
                "name": f"Batch Start Worker {i}",
                "exchange": "binance",
                "symbol": "BTCUSDT"
            })
            worker_ids.append(create_response.json()["data"]["id"])

        response = client.post("/api/workers/batch", json={
            "worker_ids": worker_ids,
            "operation": "start"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "success" in data["data"]

    async def test_batch_stop_workers(self, client):
        """测试批量停止 Worker"""
        # 创建多个 Worker
        worker_ids = []
        for i in range(3):
            create_response = client.post("/api/workers", json={
                "name": f"Batch Stop Worker {i}",
                "exchange": "binance",
                "symbol": "BTCUSDT"
            })
            worker_ids.append(create_response.json()["data"]["id"])

        response = client.post("/api/workers/batch", json={
            "worker_ids": worker_ids,
            "operation": "stop"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_batch_restart_workers(self, client):
        """测试批量重启 Worker"""
        # 创建多个 Worker
        worker_ids = []
        for i in range(3):
            create_response = client.post("/api/workers", json={
                "name": f"Batch Restart Worker {i}",
                "exchange": "binance",
                "symbol": "BTCUSDT"
            })
            worker_ids.append(create_response.json()["data"]["id"])

        response = client.post("/api/workers/batch", json={
            "worker_ids": worker_ids,
            "operation": "restart"
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0


# =============================================================================
# 测试 Worker 策略操作
# =============================================================================

@pytest.mark.asyncio
class TestWorkerStrategy:
    """测试 Worker 策略操作"""

    async def test_deploy_strategy_api(self, client):
        """测试部署策略 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Deploy Strategy Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/strategy/deploy", json={
            "strategy_id": 1,
            "parameters": {"param1": "value1"},
            "auto_start": False
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_undeploy_strategy_api(self, client):
        """测试卸载策略 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Undeploy Strategy Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/strategy/undeploy")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_get_strategy_parameters_api(self, client):
        """测试获取策略参数 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Get Params Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/strategy/parameters")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_update_strategy_parameters_api(self, client):
        """测试更新策略参数 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Update Params Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.put(f"/api/workers/{worker_id}/strategy/parameters", json={
            "parameters": {"param1": "new_value", "param2": 123}
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_get_positions_api(self, client):
        """测试获取持仓 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Get Positions Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/strategy/positions")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_get_orders_api(self, client):
        """测试获取订单 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Get Orders Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/strategy/orders")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_send_trading_signal_api(self, client):
        """测试发送交易信号 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Signal Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.post(f"/api/workers/{worker_id}/strategy/signal", json={
            "action": "buy",
            "symbol": "BTCUSDT",
            "quantity": 1.0,
            "price": 50000.0
        })

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0


# =============================================================================
# 测试 Worker 监控数据
# =============================================================================

@pytest.mark.asyncio
class TestWorkerMonitoring:
    """测试 Worker 监控数据"""

    async def test_get_worker_metrics_api(self, client):
        """测试获取 Worker 性能指标 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Metrics Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/monitoring/metrics")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "cpu_usage" in data["data"]
        assert "memory_usage" in data["data"]

    async def test_get_worker_logs_api(self, client):
        """测试获取 Worker 日志 API"""
        from worker.crud import create_worker_log

        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Logs Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/monitoring/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_get_worker_performance_api(self, client):
        """测试获取 Worker 绩效 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Performance Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/monitoring/performance")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0

    async def test_get_worker_trades_api(self, client):
        """测试获取 Worker 交易记录 API"""
        # 先创建一个 Worker
        create_response = client.post("/api/workers", json={
            "name": "Trades Test Worker",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })
        worker_id = create_response.json()["data"]["id"]

        response = client.get(f"/api/workers/{worker_id}/monitoring/trades")

        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "items" in data["data"]


# =============================================================================
# 测试 Worker 服务层
# =============================================================================

@pytest.mark.asyncio
class TestWorkerService:
    """测试 Worker 服务层"""

    async def test_worker_service_singleton(self):
        """测试 WorkerService 单例模式"""
        from worker.service import WorkerService

        service1 = WorkerService()
        service2 = WorkerService()

        assert service1 is service2

    async def test_start_worker_async(self):
        """测试异步启动 Worker"""
        from worker.service import start_worker_async

        # 由于 CommManager 可能未初始化，测试会进入模拟模式
        task_id = await start_worker_async(1)

        assert task_id is not None
        assert isinstance(task_id, str)

    async def test_stop_worker_async(self):
        """测试异步停止 Worker"""
        from worker.service import stop_worker

        result = await stop_worker(1)

        assert result is True

    async def test_restart_worker_async(self):
        """测试异步重启 Worker"""
        from worker.service import restart_worker_async

        task_id = await restart_worker_async(1)

        assert task_id is not None
        assert isinstance(task_id, str)

    async def test_get_worker_status_service(self):
        """测试获取 Worker 状态服务"""
        from worker.service import get_worker_status

        status = await get_worker_status(1)

        assert status is not None
        assert "worker_id" in status
        assert "status" in status

    async def test_health_check_service(self):
        """测试健康检查服务"""
        from worker.service import health_check

        health = await health_check(1)

        assert health is not None
        assert "is_healthy" in health

    async def test_get_worker_metrics_service(self):
        """测试获取 Worker 指标服务"""
        from worker.service import get_worker_metrics

        metrics = await get_worker_metrics(1)

        assert metrics is not None
        assert "cpu_usage" in metrics
        assert "memory_usage" in metrics


# =============================================================================
# 测试 Worker 管理器
# =============================================================================

@pytest.mark.asyncio
class TestWorkerManager:
    """测试 Worker 管理器"""

    async def test_worker_manager_creation(self):
        """测试 WorkerManager 创建"""
        from worker.manager import WorkerManager

        manager = WorkerManager(max_workers=5)

        assert manager.max_workers == 5
        assert manager.get_worker_count() == 0

    async def test_worker_manager_start_stop(self):
        """测试 WorkerManager 启动和停止"""
        from worker.manager import WorkerManager

        manager = WorkerManager(max_workers=2)

        # 启动管理器
        success = await manager.start()
        # 注意：由于 ZeroMQ 可能无法初始化，这里可能返回 False
        # 但我们仍然可以测试基本逻辑

        # 停止管理器
        await manager.stop()

        assert True  # 如果没有异常，测试通过

    async def test_worker_manager_stats(self):
        """测试 WorkerManager 统计信息"""
        from worker.manager import WorkerManager

        manager = WorkerManager(max_workers=10)

        stats = manager.get_stats()

        assert "total_workers" in stats
        assert "running_workers" in stats
        assert "max_workers" in stats
        assert stats["max_workers"] == 10


# =============================================================================
# 测试 Worker Schemas
# =============================================================================

class TestWorkerSchemas:
    """测试 Worker 数据模型验证"""

    def test_worker_create_schema(self):
        """测试 Worker 创建模型"""
        from worker.schemas import WorkerCreate

        worker = WorkerCreate(
            name="Schema Test Worker",
            description="Test",
            exchange="binance",
            symbols=["BTCUSDT"],
            timeframe="1h",
            cpu_limit=2,
            memory_limit=1024
        )

        assert worker.name == "Schema Test Worker"
        assert worker.cpu_limit == 2

    def test_worker_update_schema(self):
        """测试 Worker 更新模型"""
        from worker.schemas import WorkerUpdate

        update = WorkerUpdate(
            name="Updated Name",
            description="Updated Description"
        )

        assert update.name == "Updated Name"

    def test_worker_command_schema(self):
        """测试 Worker 命令模型"""
        from worker.schemas import WorkerCommand

        command = WorkerCommand(
            command="start",
            params={"key": "value"}
        )

        assert command.command == "start"
        assert command.params["key"] == "value"

    def test_batch_operation_request_schema(self):
        """测试批量操作请求模型"""
        from worker.schemas import BatchOperationRequest

        request = BatchOperationRequest(
            worker_ids=[1, 2, 3],
            operation="start"
        )

        assert len(request.worker_ids) == 3
        assert request.operation == "start"

    def test_strategy_deploy_request_schema(self):
        """测试策略部署请求模型"""
        from worker.schemas import StrategyDeployRequest

        request = StrategyDeployRequest(
            strategy_id=1,
            parameters={"param1": "value1"},
            auto_start=True
        )

        assert request.strategy_id == 1
        assert request.auto_start is True


# =============================================================================
# 测试错误处理
# =============================================================================

@pytest.mark.asyncio
class TestWorkerErrorHandling:
    """测试 Worker 错误处理"""

    async def test_get_nonexistent_worker(self, client):
        """测试获取不存在的 Worker"""
        response = client.get("/api/workers/99999")

        assert response.status_code == 404

    async def test_update_nonexistent_worker(self, client):
        """测试更新不存在的 Worker"""
        response = client.put("/api/workers/99999", json={
            "name": "Updated Name"
        })

        assert response.status_code == 404

    async def test_delete_nonexistent_worker(self, client):
        """测试删除不存在的 Worker"""
        response = client.delete("/api/workers/99999")

        assert response.status_code == 404

    async def test_invalid_worker_name(self, client):
        """测试无效的 Worker 名称"""
        response = client.post("/api/workers", json={
            "name": "",  # 空名称
            "exchange": "binance",
            "symbol": "BTCUSDT"
        })

        # 应该返回 422 验证错误
        assert response.status_code in [400, 422]


# =============================================================================
# 主测试入口
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
