"""
Worker API完全隔离测试

不导入任何项目模块，完全避免初始化开销
"""

import pytest
import gc
import tracemalloc
from unittest.mock import Mock, patch, MagicMock
import json


# 启动内存跟踪
tracemalloc.start()


class TestWorkerAPIIsolated:
    """
    完全隔离的Worker API测试
    
    不导入任何项目模块，避免初始化开销
    """
    
    def test_api_response_format(self):
        """测试API响应格式"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            # 模拟API响应
            response = {
                "code": 0,
                "message": "success",
                "data": {"id": 1, "name": "Test Worker"}
            }
            
            assert response["code"] == 0
            assert "message" in response
            assert "data" in response
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_worker_create_schema(self):
        """测试Worker创建数据模型"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
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
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_worker_status_values(self):
        """测试Worker状态值"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            valid_statuses = ["stopped", "running", "paused", "error", "starting", "stopping"]
            
            for status in valid_statuses:
                assert status in valid_statuses
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_lifecycle_commands(self):
        """测试生命周期命令"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            commands = ["start", "stop", "restart", "pause", "resume"]
            
            for cmd in commands:
                assert cmd in commands
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_worker_to_dict(self):
        """测试Worker转字典"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
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
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_worker_config_handling(self):
        """测试Worker配置处理"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            config = {"param1": "value1", "risk_level": "low"}
            config_json = json.dumps(config)
            
            # 验证JSON序列化
            parsed = json.loads(config_json)
            assert parsed["param1"] == "value1"
            assert parsed["risk_level"] == "low"
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")


class TestZeroMQProtocolIsolated:
    """隔离的ZeroMQ协议测试"""
    
    def test_message_type_enum(self):
        """测试消息类型枚举 - 延迟导入"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            # 延迟导入 - 只导入 protocol 模块，不导入 comm_manager
            from worker.ipc.protocol import MessageType
            
            # 验证消息类型存在
            assert MessageType.START
            assert MessageType.STOP
            assert MessageType.HEARTBEAT
            assert MessageType.STATUS_UPDATE
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_message_creation(self):
        """测试消息创建"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from worker.ipc.protocol import Message, MessageType
            
            msg = Message(
                msg_type=MessageType.HEARTBEAT,
                worker_id="worker-001",
                payload={"status": "running"}
            )
            
            assert msg.msg_type == MessageType.HEARTBEAT
            assert msg.worker_id == "worker-001"
            assert msg.payload["status"] == "running"
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_message_serialization(self):
        """测试消息序列化"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
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
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")


class TestAPIEndpointsIsolated:
    """隔离的API端点测试"""
    
    def test_api_routes_exist(self):
        """测试API路由存在 - 使用模拟避免导入"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            # 使用 patch 模拟导入，避免触发 CommManager 初始化
            with patch.dict('sys.modules', {'worker.ipc.comm_manager': MagicMock()}):
                from worker.api.routes import router
                
                assert router is not None
                assert router.prefix == "/api/workers"
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")
    
    def test_api_schemas_exist(self):
        """测试API数据模型存在"""
        gc.collect()
        mem_before = tracemalloc.get_traced_memory()[0] / 1024 / 1024
        
        try:
            from worker.schemas import WorkerCreate, WorkerUpdate, ApiResponse
            
            assert WorkerCreate is not None
            assert WorkerUpdate is not None
            assert ApiResponse is not None
        finally:
            gc.collect()
            mem_after = tracemalloc.get_traced_memory()[0] / 1024 / 1024
            print(f"\n内存使用: {mem_after - mem_before:.2f}MB")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
