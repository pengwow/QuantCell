"""
IPC协议模块单元测试

测试Message、MessageType、MessageTopic和序列化/反序列化功能
"""

import pytest
import json
import time
import sys
import importlib.util
from pathlib import Path

root_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(root_path))

protocol_path = root_path / "worker" / "ipc" / "protocol.py"
spec = importlib.util.spec_from_file_location("protocol", protocol_path)
protocol_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol_module)

Message = protocol_module.Message
MessageType = protocol_module.MessageType
MessageTopic = protocol_module.MessageTopic
serialize_message = protocol_module.serialize_message
deserialize_message = protocol_module.deserialize_message


class TestMessageType:
    """测试MessageType枚举"""

    def test_data_message_types(self):
        """测试数据消息类型"""
        assert MessageType.MARKET_DATA.value == "market_data"
        assert MessageType.TICK_DATA.value == "tick_data"
        assert MessageType.BAR_DATA.value == "bar_data"
        assert MessageType.ORDER_BOOK.value == "order_book"
        assert MessageType.TRADE_DATA.value == "trade_data"

    def test_control_message_types(self):
        """测试控制消息类型"""
        assert MessageType.START.value == "start"
        assert MessageType.STOP.value == "stop"
        assert MessageType.PAUSE.value == "pause"
        assert MessageType.RESUME.value == "resume"
        assert MessageType.RESTART.value == "restart"
        assert MessageType.RELOAD_CONFIG.value == "reload_config"
        assert MessageType.UPDATE_PARAMS.value == "update_params"

    def test_status_message_types(self):
        """测试状态消息类型"""
        assert MessageType.HEARTBEAT.value == "heartbeat"
        assert MessageType.STATUS_UPDATE.value == "status_update"
        assert MessageType.ERROR.value == "error"
        assert MessageType.WARNING.value == "warning"
        assert MessageType.INFO.value == "info"

    def test_trading_message_types(self):
        """测试交易消息类型"""
        assert MessageType.ORDER_REQUEST.value == "order_request"
        assert MessageType.ORDER_RESPONSE.value == "order_response"
        assert MessageType.POSITION_UPDATE.value == "position_update"
        assert MessageType.BALANCE_UPDATE.value == "balance_update"


class TestMessage:
    """测试Message数据类"""

    def test_create_basic_message(self):
        """测试创建基本消息"""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            worker_id="worker-001",
            payload={"status": "running"}
        )
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-001"
        assert msg.payload["status"] == "running"
        assert msg.timestamp > 0
        assert msg.msg_id is not None

    def test_message_has_unique_id(self):
        """测试消息ID唯一性"""
        msg1 = Message(msg_type=MessageType.HEARTBEAT)
        msg2 = Message(msg_type=MessageType.HEARTBEAT)
        assert msg1.msg_id != msg2.msg_id

    def test_default_values(self):
        """测试默认值"""
        msg = Message(msg_type=MessageType.STATUS_UPDATE)
        assert msg.worker_id is None
        assert msg.payload == {}
        assert msg.timestamp > 0

    def test_to_json_serialization(self):
        """测试JSON序列化"""
        msg = Message(
            msg_type=MessageType.ERROR,
            worker_id="worker-002",
            payload={"error": "test_error"}
        )
        json_str = msg.to_json()
        data = json.loads(json_str)
        
        assert data["msg_type"] == "error"
        assert data["worker_id"] == "worker-002"
        assert data["payload"]["error"] == "test_error"
        assert "timestamp" in data
        assert "msg_id" in data

    def test_from_json_deserialization(self):
        """测试JSON反序列化"""
        json_str = json.dumps({
            "msg_type": "heartbeat",
            "worker_id": "worker-003",
            "payload": {"status": "running"},
            "timestamp": time.time(),
            "msg_id": "test-id-123"
        })
        msg = Message.from_json(json_str)
        
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-003"
        assert msg.payload["status"] == "running"
        assert msg.msg_id == "test-id-123"

    def test_roundtrip_serialization(self):
        """测试序列化往返"""
        original = Message(
            msg_type=MessageType.ORDER_REQUEST,
            worker_id="worker-004",
            payload={
                "symbol": "BTCUSDT",
                "side": "buy",
                "amount": 1.5
            }
        )
        json_str = original.to_json()
        restored = Message.from_json(json_str)
        
        assert restored.msg_type == original.msg_type
        assert restored.worker_id == original.worker_id
        assert restored.payload == original.payload
        assert restored.msg_id == original.msg_id

    def test_create_heartbeat(self):
        """测试创建心跳消息"""
        msg = Message.create_heartbeat("worker-005", "running")
        
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-005"
        assert msg.payload["status"] == "running"
        assert "timestamp" in msg.payload

    def test_create_market_data(self):
        """测试创建市场数据消息"""
        data = {"close": 50000, "volume": 100}
        msg = Message.create_market_data(
            symbol="BTCUSDT",
            data_type="kline",
            data=data,
            source="binance"
        )
        
        assert msg.msg_type == MessageType.MARKET_DATA
        assert msg.payload["symbol"] == "BTCUSDT"
        assert msg.payload["data_type"] == "kline"
        assert msg.payload["data"] == data
        assert msg.payload["source"] == "binance"

    def test_create_control(self):
        """测试创建控制消息"""
        msg = Message.create_control(
            command=MessageType.STOP,
            worker_id="worker-006",
            params={"reason": "manual"}
        )
        
        assert msg.msg_type == MessageType.STOP
        assert msg.worker_id == "worker-006"
        assert msg.payload["reason"] == "manual"

    def test_create_error(self):
        """测试创建错误消息"""
        msg = Message.create_error(
            worker_id="worker-007",
            error_type="RuntimeError",
            error_message="Connection failed",
            details={"retry_count": 3}
        )
        
        assert msg.msg_type == MessageType.ERROR
        assert msg.worker_id == "worker-007"
        assert msg.payload["error_type"] == "RuntimeError"
        assert msg.payload["error_message"] == "Connection failed"
        assert msg.payload["details"]["retry_count"] == 3

    def test_create_status_update(self):
        """测试创建状态更新消息"""
        msg = Message.create_status_update(
            worker_id="worker-008",
            state="stopped",
            info={"exit_code": 0}
        )
        
        assert msg.msg_type == MessageType.STATUS_UPDATE
        assert msg.worker_id == "worker-008"
        assert msg.payload["state"] == "stopped"
        assert msg.payload["info"]["exit_code"] == 0

    def test_create_metrics(self):
        """测试创建指标消息"""
        metrics = {"cpu": 45.5, "memory": 1024}
        msg = Message.create_metrics("worker-009", metrics)
        
        assert msg.msg_type == MessageType.METRICS
        assert msg.worker_id == "worker-009"
        assert msg.payload["metrics"] == metrics

    def test_create_order_request(self):
        """测试创建订单请求消息"""
        msg = Message.create_order_request(
            worker_id="worker-010",
            symbol="ETHUSDT",
            side="sell",
            order_type="limit",
            amount=10.0,
            price=3000.0,
            params={"timeInForce": "GTC"}
        )
        
        assert msg.msg_type == MessageType.ORDER_REQUEST
        assert msg.worker_id == "worker-010"
        assert msg.payload["symbol"] == "ETHUSDT"
        assert msg.payload["side"] == "sell"
        assert msg.payload["order_type"] == "limit"
        assert msg.payload["amount"] == 10.0
        assert msg.payload["price"] == 3000.0
        assert msg.payload["params"]["timeInForce"] == "GTC"

    def test_create_log(self):
        """测试创建日志消息"""
        msg = Message.create_log(
            worker_id="worker-011",
            level="INFO",
            message="Strategy started",
            source="strategy"
        )
        
        assert msg.msg_type == MessageType.LOG
        assert msg.worker_id == "worker-011"
        assert msg.payload["level"] == "INFO"
        assert msg.payload["message"] == "Strategy started"
        assert msg.payload["source"] == "strategy"


class TestMessageTopic:
    """测试MessageTopic工具类"""

    def test_market_data_topic(self):
        """测试市场数据主题生成"""
        topic = MessageTopic.market_data("BTCUSDT", "kline")
        assert topic == "market.BTCUSDT.kline"

    def test_control_topic(self):
        """测试控制主题生成"""
        topic = MessageTopic.control("worker-001")
        assert topic == "control.worker-001"

    def test_status_topic(self):
        """测试状态主题生成"""
        topic = MessageTopic.status("worker-002")
        assert topic == "status.worker-002"

    def test_broadcast_topic(self):
        """测试广播主题"""
        topic = MessageTopic.broadcast()
        assert topic == "broadcast.all"


class TestSerialization:
    """测试序列化/反序列化函数"""

    def test_serialize_message(self):
        """测试消息序列化"""
        msg = Message(
            msg_type=MessageType.INFO,
            worker_id="worker-012",
            payload={"message": "test"}
        )
        data = serialize_message(msg)
        
        assert isinstance(data, bytes)
        assert b"worker-012" in data
        assert b"info" in data

    def test_deserialize_message(self):
        """测试消息反序列化"""
        original = Message(
            msg_type=MessageType.WARNING,
            worker_id="worker-013",
            payload={"code": 101}
        )
        data = serialize_message(original)
        restored = deserialize_message(data)
        
        assert restored.msg_type == original.msg_type
        assert restored.worker_id == original.worker_id

    def test_deserialize_empty_data(self):
        """测试反序列化空数据"""
        with pytest.raises(ValueError, match="接收到的数据为空"):
            deserialize_message(b"")
        
        with pytest.raises(ValueError, match="解码后的JSON字符串为空"):
            deserialize_message(b"   ")

    def test_deserialize_invalid_json(self):
        """测试反序列化无效JSON"""
        with pytest.raises(json.JSONDecodeError):
            deserialize_message(b"not valid json")

    def test_roundtrip_complex_payload(self):
        """测试复杂负载的往返序列化"""
        original = Message(
            msg_type=MessageType.MARKET_DATA,
            worker_id="worker-014",
            payload={
                "symbol": "BTCUSDT",
                "data_type": "kline",
                "data": {
                    "open": 49000,
                    "high": 51000,
                    "low": 48500,
                    "close": 50500,
                    "volume": 12345.67,
                    "nested": {"key": "value", "list": [1, 2, 3]}
                },
                "source": "binance",
                "timestamp": time.time()
            }
        )
        
        json_str = original.to_json()
        restored = Message.from_json(json_str)
        
        assert restored.payload == original.payload
        assert restored.payload["data"]["nested"]["list"] == [1, 2, 3]
