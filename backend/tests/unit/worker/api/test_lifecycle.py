"""
Worker生命周期管理API测试

测试Worker的启动、停止、重启、暂停、恢复等功能
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch

from worker.models import Worker
from collector.db.models import Strategy


class TestWorkerStart:
    """测试Worker启动功能"""
    
    def test_start_worker_success(self, client: TestClient, db_session: Session, monkeypatch):
        """测试成功启动Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="stopped"
        )
        db_session.add(worker)
        db_session.commit()
        
        # 模拟异步启动
        with patch("worker.service.start_worker_async") as mock_start:
            mock_start.return_value = "task-123"
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/start")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "task_id" in data["data"]
            assert data["data"]["status"] == "starting"
    
    def test_start_worker_not_found(self, client: TestClient):
        """测试启动不存在的Worker"""
        response = client.post("/api/workers/99999/lifecycle/start")
        
        assert response.status_code == 404
    
    def test_start_already_running_worker(self, client: TestClient, db_session: Session):
        """测试启动已在运行的Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Running Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="running"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.start_worker_async") as mock_start:
            mock_start.return_value = "task-456"
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/start")
            
            # 根据实现可能返回200或400
            assert response.status_code in [200, 400]


class TestWorkerStop:
    """测试Worker停止功能"""
    
    def test_stop_worker_success(self, client: TestClient, db_session: Session, monkeypatch):
        """测试成功停止Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="running"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.stop_worker") as mock_stop:
            mock_stop.return_value = True
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/stop")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "停止成功" in data["message"]
    
    def test_stop_worker_not_found(self, client: TestClient):
        """测试停止不存在的Worker"""
        response = client.post("/api/workers/99999/lifecycle/stop")
        
        assert response.status_code == 404
    
    def test_stop_already_stopped_worker(self, client: TestClient, db_session: Session):
        """测试停止已停止的Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Stopped Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="stopped"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.stop_worker") as mock_stop:
            mock_stop.return_value = True
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/stop")
            
            # 应该返回成功（幂等操作）
            assert response.status_code == 200


class TestWorkerRestart:
    """测试Worker重启功能"""
    
    def test_restart_worker_success(self, client: TestClient, db_session: Session):
        """测试成功重启Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="running"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.restart_worker_async") as mock_restart:
            mock_restart.return_value = "task-789"
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/restart")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "重启中" in data["message"]
            assert "task_id" in data["data"]


class TestWorkerPause:
    """测试Worker暂停功能"""
    
    def test_pause_worker_success(self, client: TestClient, db_session: Session):
        """测试成功暂停Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="running"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.pause_worker") as mock_pause:
            mock_pause.return_value = True
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/pause")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "已暂停" in data["message"]


class TestWorkerResume:
    """测试Worker恢复功能"""
    
    def test_resume_worker_success(self, client: TestClient, db_session: Session):
        """测试成功恢复Worker"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="paused"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.resume_worker") as mock_resume:
            mock_resume.return_value = True
            
            response = client.post(f"/api/workers/{worker.id}/lifecycle/resume")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "已恢复" in data["message"]


class TestWorkerStatus:
    """测试Worker状态查询"""
    
    def test_get_worker_status_success(self, client: TestClient, db_session: Session):
        """测试成功获取Worker状态"""
        strategy = Strategy(name="Test Strategy", filename="test.py")
        db_session.add(strategy)
        db_session.commit()
        
        worker = Worker(
            name="Test Worker",
            strategy_id=strategy.id,
            exchange="binance",
            symbol="BTCUSDT",
            status="running"
        )
        db_session.add(worker)
        db_session.commit()
        
        with patch("worker.service.get_worker_status") as mock_status:
            mock_status.return_value = {
                "worker_id": worker.id,
                "status": "running",
                "is_healthy": True,
                "uptime": 3600
            }
            
            response = client.get(f"/api/workers/{worker.id}/lifecycle/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["status"] == "running"


class TestWorkerHealth:
    """测试Worker健康检查"""
    
    def test_health_check_success(self, client: TestClient, db_session: Session):
        """测试成功健康检查"""
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
        
        with patch("worker.service.health_check") as mock_health:
            mock_health.return_value = {
                "worker_id": worker.id,
                "is_healthy": True,
                "checks": {
                    "communication": True,
                    "heartbeat": True
                }
            }
            
            response = client.get(f"/api/workers/{worker.id}/lifecycle/health")
            
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["is_healthy"] is True
