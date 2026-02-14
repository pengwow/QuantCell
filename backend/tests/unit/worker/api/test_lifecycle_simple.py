"""
Worker生命周期管理API简单测试

使用mock避免数据库操作问题
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


class TestWorkerLifecycleSimple:
    """简化的生命周期测试"""
    
    def test_start_worker_not_found(self, client: TestClient):
        """测试启动不存在的Worker - 使用mock"""
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = None
            
            response = client.post("/api/workers/99999/lifecycle/start")
            
            assert response.status_code == 404
    
    def test_stop_worker_not_found(self, client: TestClient):
        """测试停止不存在的Worker"""
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = None
            
            response = client.post("/api/workers/99999/lifecycle/stop")
            
            assert response.status_code == 404
    
    def test_get_status_worker_not_found(self, client: TestClient):
        """测试获取不存在Worker的状态"""
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = None
            
            response = client.get("/api/workers/99999/lifecycle/status")
            
            assert response.status_code == 404
    
    def test_health_check_worker_not_found(self, client: TestClient):
        """测试健康检查不存在的Worker"""
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = None
            
            response = client.get("/api/workers/99999/lifecycle/health")
            
            assert response.status_code == 404


class TestWorkerLifecycleWithMock:
    """使用Mock对象测试生命周期"""
    
    def test_start_worker_success(self, client: TestClient):
        """测试成功启动Worker"""
        # 创建mock worker
        mock_worker = MagicMock()
        mock_worker.id = 1
        mock_worker.name = "Test Worker"
        mock_worker.status = "stopped"
        mock_worker.to_dict.return_value = {
            "id": 1,
            "name": "Test Worker",
            "status": "stopped"
        }
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.start_worker_async") as mock_start:
                mock_start.return_value = "task-123"
                
                response = client.post("/api/workers/1/lifecycle/start")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert "task_id" in data["data"]
    
    def test_stop_worker_success(self, client: TestClient):
        """测试成功停止Worker"""
        mock_worker = MagicMock()
        mock_worker.id = 1
        mock_worker.status = "running"
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.stop_worker") as mock_stop:
                mock_stop.return_value = True
                
                response = client.post("/api/workers/1/lifecycle/stop")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
    
    def test_restart_worker_success(self, client: TestClient):
        """测试成功重启Worker"""
        mock_worker = MagicMock()
        mock_worker.id = 1
        mock_worker.status = "running"
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.restart_worker_async") as mock_restart:
                mock_restart.return_value = "task-456"
                
                response = client.post("/api/workers/1/lifecycle/restart")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert "task_id" in data["data"]
    
    def test_pause_worker_success(self, client: TestClient):
        """测试成功暂停Worker"""
        mock_worker = MagicMock()
        mock_worker.id = 1
        mock_worker.status = "running"
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.pause_worker") as mock_pause:
                mock_pause.return_value = True
                
                response = client.post("/api/workers/1/lifecycle/pause")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
    
    def test_resume_worker_success(self, client: TestClient):
        """测试成功恢复Worker"""
        mock_worker = MagicMock()
        mock_worker.id = 1
        mock_worker.status = "paused"
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.resume_worker") as mock_resume:
                mock_resume.return_value = True
                
                response = client.post("/api/workers/1/lifecycle/resume")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
    
    def test_get_status_success(self, client: TestClient):
        """测试成功获取Worker状态"""
        mock_worker = MagicMock()
        mock_worker.id = 1
        mock_worker.status = "running"
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.get_worker_status") as mock_status:
                mock_status.return_value = {
                    "worker_id": 1,
                    "status": "running",
                    "is_healthy": True
                }
                
                response = client.get("/api/workers/1/lifecycle/status")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["status"] == "running"
    
    def test_health_check_success(self, client: TestClient):
        """测试成功健康检查"""
        mock_worker = MagicMock()
        mock_worker.id = 1
        
        with patch("worker.crud.get_worker") as mock_get:
            mock_get.return_value = mock_worker
            
            with patch("worker.service.health_check") as mock_health:
                mock_health.return_value = {
                    "worker_id": 1,
                    "is_healthy": True,
                    "checks": {"communication": True}
                }
                
                response = client.get("/api/workers/1/lifecycle/health")
                
                assert response.status_code == 200
                data = response.json()
                assert data["code"] == 0
                assert data["data"]["is_healthy"] is True
