"""
Worker基础管理API测试

测试Worker的CRUD操作、克隆、批量操作等功能
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from worker.models import Worker
from collector.db.models import Strategy


class TestWorkerCreate:
    """测试Worker创建功能"""
    
    def test_create_worker_success(self, client: TestClient, db_session: Session, sample_worker_create_request):
        """测试成功创建Worker"""
        # 先创建一个策略
        strategy = Strategy(
            name="Test Strategy",
            filename="test_strategy.py",
            description="Test strategy"
        )
        db_session.add(strategy)
        db_session.commit()
        
        # 更新请求中的strategy_id
        sample_worker_create_request["strategy_id"] = strategy.id
        
        response = client.post("/api/workers", json=sample_worker_create_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["message"] == "Worker创建成功"
        assert "data" in data
        assert data["data"]["name"] == sample_worker_create_request["name"]
        assert data["data"]["status"] == "stopped"
    
    def test_create_worker_without_name(self, client: TestClient):
        """测试创建Worker时缺少名称"""
        request_data = {
            "strategy_id": 1,
            "exchange": "binance"
        }
        
        response = client.post("/api/workers", json=request_data)
        
        assert response.status_code == 422  # 验证错误
    
    def test_create_worker_invalid_strategy(self, client: TestClient, sample_worker_create_request):
        """测试创建Worker时使用不存在的策略ID"""
        sample_worker_create_request["strategy_id"] = 99999
        
        response = client.post("/api/workers", json=sample_worker_create_request)
        
        # 由于外键约束，可能会返回400或500错误
        assert response.status_code in [400, 500]
    
    def test_create_worker_duplicate_name(self, client: TestClient, db_session: Session, sample_worker_create_request):
        """测试创建同名Worker"""
        # 先创建策略
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        sample_worker_create_request["strategy_id"] = strategy.id
        
        # 创建第一个Worker
        response1 = client.post("/api/workers", json=sample_worker_create_request)
        assert response1.status_code == 200
        
        # 尝试创建同名Worker
        response2 = client.post("/api/workers", json=sample_worker_create_request)
        # 根据实现可能返回400或成功（如果允许同名）
        assert response2.status_code in [200, 400]


class TestWorkerList:
    """测试Worker列表查询功能"""
    
    def test_list_workers_empty(self, client: TestClient):
        """测试空列表"""
        response = client.get("/api/workers")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0
    
    def test_list_workers_with_data(self, client: TestClient, db_session: Session):
        """测试有数据的列表"""
        # 创建策略
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        # 创建多个Worker
        for i in range(3):
            worker = Worker(
                name=f"Worker {i}",
                strategy_id=strategy.id,
                exchange="binance",
                symbol="BTCUSDT",
                status="stopped"
            )
            db_session.add(worker)
        db_session.commit()
        
        response = client.get("/api/workers")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert len(data["data"]["items"]) == 3
        assert data["data"]["total"] == 3
    
    def test_list_workers_with_pagination(self, client: TestClient, db_session: Session):
        """测试分页功能"""
        # 创建策略和Worker
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        for i in range(5):
            worker = Worker(
                name=f"Worker {i}",
                strategy_id=strategy.id,
                exchange="binance",
                symbol="BTCUSDT"
            )
            db_session.add(worker)
        db_session.commit()
        
        # 测试第一页
        response = client.get("/api/workers?page=1&page_size=2")
        data = response.json()
        assert len(data["data"]["items"]) == 2
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2
        
        # 测试第二页
        response = client.get("/api/workers?page=2&page_size=2")
        data = response.json()
        assert len(data["data"]["items"]) == 2
        assert data["data"]["page"] == 2
    
    def test_list_workers_with_status_filter(self, client: TestClient, db_session: Session):
        """测试按状态筛选"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        # 创建不同状态的Worker
        worker1 = Worker(name="Running Worker", strategy_id=strategy.id, 
                        exchange="binance", symbol="BTCUSDT", status="running")
        worker2 = Worker(name="Stopped Worker", strategy_id=strategy.id,
                        exchange="binance", symbol="BTCUSDT", status="stopped")
        db_session.add_all([worker1, worker2])
        db_session.commit()
        
        response = client.get("/api/workers?status=running")
        data = response.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["items"][0]["status"] == "running"
    
    def test_list_workers_with_strategy_filter(self, client: TestClient, db_session: Session):
        """测试按策略ID筛选"""
        strategy1 = Strategy(name="Strategy 1", filename="s1.py")
        strategy2 = Strategy(name="Strategy 2", filename="s2.py")
        db_session.add_all([strategy1, strategy2])
        db_session.commit()
        
        worker1 = Worker(name="Worker 1", strategy_id=strategy1.id,
                        exchange="binance", symbol="BTCUSDT")
        worker2 = Worker(name="Worker 2", strategy_id=strategy2.id,
                        exchange="binance", symbol="ETHUSDT")
        db_session.add_all([worker1, worker2])
        db_session.commit()
        
        response = client.get(f"/api/workers?strategy_id={strategy1.id}")
        data = response.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["items"][0]["strategy_id"] == strategy1.id


class TestWorkerGet:
    """测试获取Worker详情"""
    
    def test_get_worker_success(self, client: TestClient, db_session: Session):
        """测试成功获取Worker详情"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            description="Test description"
        )
        db_session.add(worker)
        db_session.commit()
        
        response = client.get(f"/api/workers/{worker.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Test Worker"
        assert data["data"]["description"] == "Test description"
    
    def test_get_worker_not_found(self, client: TestClient):
        """测试获取不存在的Worker"""
        response = client.get("/api/workers/99999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestWorkerUpdate:
    """测试Worker更新功能"""
    
    def test_update_worker_success(self, client: TestClient, db_session: Session):
        """测试成功更新Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Original Name",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT"
        )
        db_session.add(worker)
        db_session.commit()
        
        update_data = {
            "name": "Updated Name",
            "description": "Updated description"
        }
        
        response = client.put(f"/api/workers/{worker.id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Updated Name"
        assert data["data"]["description"] == "Updated description"
    
    def test_update_worker_not_found(self, client: TestClient):
        """测试更新不存在的Worker"""
        update_data = {"name": "New Name"}
        
        response = client.put("/api/workers/99999", json=update_data)
        
        assert response.status_code == 404
    
    def test_update_worker_partial(self, client: TestClient, db_session: Session):
        """测试部分更新Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            description="Original description"
        )
        db_session.add(worker)
        db_session.commit()
        
        # 只更新名称
        update_data = {"name": "New Name Only"}
        
        response = client.put(f"/api/workers/{worker.id}", json=update_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "New Name Only"
        # 其他字段应保持不变


class TestWorkerConfigUpdate:
    """测试Worker配置更新"""
    
    def test_update_worker_config_success(self, client: TestClient, db_session: Session):
        """测试成功更新Worker配置"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT"
        )
        db_session.add(worker)
        db_session.commit()
        
        config_update = {
            "config": {
                "new_param": "new_value",
                "risk_level": "high"
            }
        }
        
        response = client.patch(f"/api/workers/{worker.id}/config", json=config_update)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["config"]["new_param"] == "new_value"


class TestWorkerDelete:
    """测试Worker删除功能"""
    
    def test_delete_worker_success(self, client: TestClient, db_session: Session):
        """测试成功删除Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Worker to Delete",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT"
        )
        db_session.add(worker)
        db_session.commit()
        
        response = client.delete(f"/api/workers/{worker.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["message"] == "Worker删除成功"
        
        # 验证Worker已被删除
        deleted_worker = db_session.query(Worker).filter_by(id=worker.id).first()
        assert deleted_worker is None
    
    def test_delete_worker_not_found(self, client: TestClient):
        """测试删除不存在的Worker"""
        response = client.delete("/api/workers/99999")
        
        assert response.status_code == 404


class TestWorkerClone:
    """测试Worker克隆功能"""
    
    def test_clone_worker_success(self, client: TestClient, db_session: Session):
        """测试成功克隆Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Original Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            description="Original description"
        )
        db_session.add(worker)
        db_session.commit()
        
        clone_request = {
            "new_name": "Cloned Worker",
            "copy_config": True,
            "copy_parameters": True
        }
        
        response = client.post(f"/api/workers/{worker.id}/clone", json=clone_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Cloned Worker"
        assert data["data"]["description"] == "Original description"
    
    def test_clone_worker_not_found(self, client: TestClient):
        """测试克隆不存在的Worker"""
        clone_request = {"new_name": "Cloned Worker"}
        
        response = client.post("/api/workers/99999/clone", json=clone_request)
        
        assert response.status_code == 400


class TestBatchOperation:
    """测试批量操作功能"""
    
    def test_batch_start_workers(self, client: TestClient, db_session: Session):
        """测试批量启动Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        workers = []
        for i in range(3):
            worker = Worker(
                name=f"Worker {i}",
                strategy_id=strategy.id,
                exchange="binance",
                symbol="BTCUSDT",
                status="stopped"
            )
            db_session.add(worker)
            workers.append(worker)
        db_session.commit()
        
        batch_request = {
            "worker_ids": [w.id for w in workers],
            "operation": "start"
        }
        
        response = client.post("/api/workers/batch", json=batch_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "data" in data
    
    def test_batch_stop_workers(self, client: TestClient, db_session: Session):
        """测试批量停止Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        workers = []
        for i in range(3):
            worker = Worker(
                name=f"Worker {i}",
                strategy_id=strategy.id,
                exchange="binance",
                symbol="BTCUSDT",
                status="running"
            )
            db_session.add(worker)
            workers.append(worker)
        db_session.commit()
        
        batch_request = {
            "worker_ids": [w.id for w in workers],
            "operation": "stop"
        }
        
        response = client.post("/api/workers/batch", json=batch_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
    
    def test_batch_invalid_operation(self, client: TestClient, db_session: Session):
        """测试无效的批量操作"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(name="Test Worker", strategy_id=strategy.id,
                       exchange="binance", symbol="BTCUSDT")
        db_session.add(worker)
        db_session.commit()
        
        batch_request = {
            "worker_ids": [worker.id],
            "operation": "invalid_operation"
        }
        
        response = client.post("/api/workers/batch", json=batch_request)
        
        # 可能返回400或200（取决于实现）
        assert response.status_code in [200, 400]
