"""
Worker生命周期管理API测试 - 修复版本

解决测试挂起和内存泄漏问题
使用完全Mock化方式，避免真实数据库操作
"""

import pytest
import gc
import tracemalloc
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestWorkerLifecycleFixed:
    """
    修复后的生命周期测试类
    
    特点：
    1. 使用完全Mock化，避免数据库操作
    2. 每个测试独立，不依赖fixture
    3. 添加内存监控
    """
    
    def test_start_worker_not_found(self):
        """
        测试启动不存在的Worker
        
        使用完全Mock化，避免导入整个FastAPI应用
        """
        # 记录内存使用
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB
        
        try:
            # 延迟导入 - 只在测试内部导入
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            # 创建最小化FastAPI应用，只包含Worker路由
            app = FastAPI()
            app.include_router(router)
            
            # Mock数据库操作
            with patch("worker.crud.get_worker") as mock_get:
                mock_get.return_value = None
                
                client = TestClient(app)
                response = client.post("/api/workers/99999/lifecycle/start")
                
                assert response.status_code == 404
                mock_get.assert_called_once()
        finally:
            # 强制清理
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024  # MB
            
            # 检查内存增长
            mem_diff = mem_after - mem_before
            if mem_diff > 10:  # 超过10MB警告
                print(f"\n警告: 内存使用增加 {mem_diff:.2f}MB")
    
    def test_stop_worker_not_found(self):
        """测试停止不存在的Worker"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
            with patch("worker.crud.get_worker") as mock_get:
                mock_get.return_value = None
                
                client = TestClient(app)
                response = client.post("/api/workers/99999/lifecycle/stop")
                
                assert response.status_code == 404
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_start_worker_success(self):
        """测试成功启动Worker"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
            # Mock Worker对象
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
                    
                    client = TestClient(app)
                    response = client.post("/api/workers/1/lifecycle/start")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
                    assert "task_id" in data["data"]
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_stop_worker_success(self):
        """测试成功停止Worker"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
            mock_worker = MagicMock()
            mock_worker.id = 1
            mock_worker.status = "running"
            
            with patch("worker.crud.get_worker") as mock_get:
                mock_get.return_value = mock_worker
                
                with patch("worker.service.stop_worker") as mock_stop:
                    mock_stop.return_value = True
                    
                    client = TestClient(app)
                    response = client.post("/api/workers/1/lifecycle/stop")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_restart_worker_success(self):
        """测试成功重启Worker"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
            mock_worker = MagicMock()
            mock_worker.id = 1
            mock_worker.status = "running"
            
            with patch("worker.crud.get_worker") as mock_get:
                mock_get.return_value = mock_worker
                
                with patch("worker.service.restart_worker_async") as mock_restart:
                    mock_restart.return_value = "task-456"
                    
                    client = TestClient(app)
                    response = client.post("/api/workers/1/lifecycle/restart")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
                    assert "task_id" in data["data"]
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_pause_worker_success(self):
        """测试成功暂停Worker"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
            mock_worker = MagicMock()
            mock_worker.id = 1
            mock_worker.status = "running"
            
            with patch("worker.crud.get_worker") as mock_get:
                mock_get.return_value = mock_worker
                
                with patch("worker.service.pause_worker") as mock_pause:
                    mock_pause.return_value = True
                    
                    client = TestClient(app)
                    response = client.post("/api/workers/1/lifecycle/pause")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_resume_worker_success(self):
        """测试成功恢复Worker"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
            mock_worker = MagicMock()
            mock_worker.id = 1
            mock_worker.status = "paused"
            
            with patch("worker.crud.get_worker") as mock_get:
                mock_get.return_value = mock_worker
                
                with patch("worker.service.resume_worker") as mock_resume:
                    mock_resume.return_value = True
                    
                    client = TestClient(app)
                    response = client.post("/api/workers/1/lifecycle/resume")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_get_worker_status(self):
        """测试获取Worker状态"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
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
                    
                    client = TestClient(app)
                    response = client.get("/api/workers/1/lifecycle/status")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
                    assert data["data"]["status"] == "running"
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")
    
    def test_health_check(self):
        """测试健康检查"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from fastapi.testclient import TestClient
            from worker.api.routes import router
            from fastapi import FastAPI
            
            app = FastAPI()
            app.include_router(router)
            
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
                    
                    client = TestClient(app)
                    response = client.get("/api/workers/1/lifecycle/health")
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["code"] == 0
                    assert data["data"]["is_healthy"] is True
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            if mem_after - mem_before > 10:
                print(f"\n警告: 内存使用增加 {mem_after - mem_before:.2f}MB")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
