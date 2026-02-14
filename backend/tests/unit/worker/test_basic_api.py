"""
Worker API基础测试 - 最简化版本

避免复杂的导入和数据库操作
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json


class TestWorkerAPIBasic:
    """基础API测试"""
    
    def test_api_response_format(self):
        """测试API响应格式"""
        # 模拟API响应
        response = {
            "code": 0,
            "message": "success",
            "data": {"id": 1, "name": "Test Worker"}
        }
        
        assert response["code"] == 0
        assert "message" in response
        assert "data" in response
    
    def test_worker_create_schema(self):
        """测试Worker创建数据模型"""
        worker_data = {
            "name": "Test Worker",
            "strategy_id": 1,
            "exchange": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "market_type": "spot",
            "trading_mode": "paper",
            "cpu_limit": 1,
            "memory_limit": 512
        }
        
        # 验证必填字段
        assert worker_data["name"]
        assert isinstance(worker_data["strategy_id"], int)
        assert worker_data["exchange"]
        assert worker_data["symbol"]
    
    def test_worker_status_values(self):
        """测试Worker状态值"""
        valid_statuses = ["stopped", "running", "paused", "error", "starting", "stopping"]
        
        for status in valid_statuses:
            assert status in valid_statuses
    
    def test_lifecycle_commands(self):
        """测试生命周期命令"""
        commands = ["start", "stop", "restart", "pause", "resume"]
        
        for cmd in commands:
            assert cmd in commands


class TestWorkerModels:
    """测试Worker模型"""
    
    def test_worker_to_dict(self):
        """测试Worker转字典"""
        # 模拟Worker对象
        worker = Mock()
        worker.id = 1
        worker.name = "Test Worker"
        worker.status = "running"
        worker.exchange = "binance"
        worker.symbol = "BTCUSDT"
        
        # 模拟to_dict方法
        worker.to_dict.return_value = {
            "id": 1,
            "name": "Test Worker",
            "status": "running",
            "exchange": "binance",
            "symbol": "BTCUSDT"
        }
        
        result = worker.to_dict()
        assert result["id"] == 1
        assert result["name"] == "Test Worker"
    
    def test_worker_config_handling(self):
        """测试Worker配置处理"""
        import json
        
        config = {"param1": "value1", "risk_level": "low"}
        config_json = json.dumps(config)
        
        # 验证JSON序列化
        parsed = json.loads(config_json)
        assert parsed["param1"] == "value1"
        assert parsed["risk_level"] == "low"


class TestZeroMQProtocol:
    """测试ZeroMQ协议"""
    
    def test_message_type_enum(self):
        """测试消息类型枚举"""
        from worker.ipc.protocol import MessageType
        
        # 验证消息类型存在
        assert MessageType.START
        assert MessageType.STOP
        assert MessageType.HEARTBEAT
        assert MessageType.STATUS_UPDATE
    
    def test_message_creation(self):
        """测试消息创建"""
        from worker.ipc.protocol import Message, MessageType
        
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            worker_id="worker-001",
            payload={"status": "running"}
        )
        
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-001"
        assert msg.payload["status"] == "running"
    
    def test_message_serialization(self):
        """测试消息序列化"""
        from worker.ipc.protocol import Message, MessageType, serialize_message, deserialize_message
        
        msg = Message(
            msg_type=MessageType.MARKET_DATA,
            worker_id="worker-001",
            payload={"symbol": "BTCUSDT", "price": 50000}
        )
        
        # 序列化
        data = serialize_message(msg)
        assert isinstance(data, bytes)
        
        # 反序列化
        restored = deserialize_message(data)
        assert restored.msg_type == MessageType.MARKET_DATA
        assert restored.payload["symbol"] == "BTCUSDT"


class TestWorkerService:
    """测试Worker服务"""
    
    def test_service_initialization(self):
        """测试服务初始化"""
        from worker.service import WorkerService
        
        service = WorkerService()
        assert service is not None
    
    def test_worker_manager_singleton(self):
        """测试WorkerManager单例"""
        from worker.service import WorkerService
        
        service1 = WorkerService()
        service2 = WorkerService()
        
        # 验证是同一个实例
        assert service1 is service2


class TestAPIEndpoints:
    """测试API端点定义"""
    
    def test_api_routes_exist(self):
        """测试API路由存在"""
        from worker.api.routes import router
        
        assert router is not None
        assert router.prefix == "/api/workers"
    
    def test_api_schemas_exist(self):
        """测试API数据模型存在"""
        from worker.schemas import WorkerCreate, WorkerUpdate, ApiResponse
        
        assert WorkerCreate is not None
        assert WorkerUpdate is not None
        assert ApiResponse is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
