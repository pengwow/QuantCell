"""
Worker IPC 协议模块单元测试

测试 MessageType、Message 和 MessageTopic 的功能
"""

import pytest
import json
import time
from datetime import datetime
from worker.ipc.protocol import (
    MessageType,
    Message,
    MessageTopic,
    serialize_message,
    deserialize_message
)


class TestMessageType:
    """测试 MessageType 枚举"""

    def test_message_type_values(self):
        """测试消息类型值"""
        assert MessageType.MARKET_DATA.value == "market_data"
        assert MessageType.TICK_DATA.value == "tick_data"
        assert MessageType.BAR_DATA.value == "bar_data"
        assert MessageType.START.value == "start"
        assert MessageType.STOP.value == "stop"
        assert MessageType.PAUSE.value == "pause"
        assert MessageType.RESUME.value == "resume"
        assert MessageType.HEARTBEAT.value == "heartbeat"
        assert MessageType.STATUS_UPDATE.value == "status_update"
        assert MessageType.ERROR.value == "error"
        assert MessageType.ORDER_REQUEST.value == "order_request"
        assert MessageType.ORDER_RESPONSE.value == "order_response"

    def test_message_type_from_value(self):
        """测试从值创建消息类型"""
        assert MessageType("market_data") == MessageType.MARKET_DATA
        assert MessageType("heartbeat") == MessageType.HEARTBEAT
        assert MessageType("error") == MessageType.ERROR


class TestMessage:
    """测试 Message 类"""

    def test_message_creation(self):
        """测试消息创建"""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            worker_id="worker-001",
            payload={"status": "running"},
            timestamp=1234567890.0,
            msg_id="msg-001"
        )
        
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-001"
        assert msg.payload == {"status": "running"}
        assert msg.timestamp == 1234567890.0
        assert msg.msg_id == "msg-001"

    def test_message_default_timestamp(self):
        """测试消息默认时间戳"""
        before = time.time()
        msg = Message(msg_type=MessageType.HEARTBEAT)
        after = time.time()
        
        assert before <= msg.timestamp <= after

    def test_message_to_json(self):
        """测试消息序列化为 JSON"""
        msg = Message(
            msg_type=MessageType.MARKET_DATA,
            worker_id="worker-001",
            payload={"symbol": "BTC/USDT", "price": 50000},
            timestamp=1234567890.0,
            msg_id="msg-001"
        )
        
        json_str = msg.to_json()
        data = json.loads(json_str)
        
        assert data["msg_type"] == "market_data"
        assert data["worker_id"] == "worker-001"
        assert data["payload"] == {"symbol": "BTC/USDT", "price": 50000}
        assert data["timestamp"] == 1234567890.0
        assert data["msg_id"] == "msg-001"

    def test_message_from_json(self):
        """测试从 JSON 反序列化消息"""
        json_str = json.dumps({
            "msg_type": "heartbeat",
            "worker_id": "worker-001",
            "payload": {"status": "running"},
            "timestamp": 1234567890.0,
            "msg_id": "msg-001"
        })
        
        msg = Message.from_json(json_str)
        
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-001"
        assert msg.payload == {"status": "running"}
        assert msg.timestamp == 1234567890.0
        assert msg.msg_id == "msg-001"

    def test_message_roundtrip(self):
        """测试消息的序列化和反序列化往返"""
        original = Message(
            msg_type=MessageType.ORDER_REQUEST,
            worker_id="worker-001",
            payload={"symbol": "BTC/USDT", "side": "buy", "amount": 1.0},
            msg_id="order-001"
        )
        
        json_str = original.to_json()
        restored = Message.from_json(json_str)
        
        assert restored.msg_type == original.msg_type
        assert restored.worker_id == original.worker_id
        assert restored.payload == original.payload
        assert restored.msg_id == original.msg_id

    def test_create_heartbeat(self):
        """测试创建心跳消息"""
        msg = Message.create_heartbeat("worker-001", "running")
        
        assert msg.msg_type == MessageType.HEARTBEAT
        assert msg.worker_id == "worker-001"
        assert msg.payload["status"] == "running"
        assert msg.timestamp is not None

    def test_create_market_data(self):
        """测试创建市场数据消息"""
        data = {"open": 50000, "high": 51000, "low": 49000, "close": 50500}
        msg = Message.create_market_data(
            symbol="BTC/USDT",
            data_type="kline",
            data=data,
            source="binance"
        )
        
        assert msg.msg_type == MessageType.MARKET_DATA
        assert msg.payload["symbol"] == "BTC/USDT"
        assert msg.payload["data_type"] == "kline"
        assert msg.payload["data"] == data
        assert msg.payload["source"] == "binance"

    def test_create_control(self):
        """测试创建控制消息"""
        msg = Message.create_control(
            MessageType.STOP,
            "worker-001",
            {"reason": "manual_stop"}
        )
        
        assert msg.msg_type == MessageType.STOP
        assert msg.worker_id == "worker-001"
        assert msg.payload["reason"] == "manual_stop"

    def test_create_error(self):
        """测试创建错误消息"""
        msg = Message.create_error(
            worker_id="worker-001",
            error_type="RuntimeError",
            error_message="Something went wrong",
            details={"traceback": "line 1"}
        )
        
        assert msg.msg_type == MessageType.ERROR
        assert msg.worker_id == "worker-001"
        assert msg.payload["error_type"] == "RuntimeError"
        assert msg.payload["error_message"] == "Something went wrong"
        assert msg.payload["details"] == {"traceback": "line 1"}

    def test_create_order_request(self):
        """测试创建订单请求消息"""
        msg = Message.create_order_request(
            worker_id="worker-001",
            symbol="BTC/USDT",
            side="buy",
            order_type="limit",
            amount=1.5,
            price=50000,
            params={"time_in_force": "GTC"}
        )
        
        assert msg.msg_type == MessageType.ORDER_REQUEST
        assert msg.worker_id == "worker-001"
        assert msg.payload["symbol"] == "BTC/USDT"
        assert msg.payload["side"] == "buy"
        assert msg.payload["order_type"] == "limit"
        assert msg.payload["amount"] == 1.5
        assert msg.payload["price"] == 50000
        assert msg.payload["params"] == {"time_in_force": "GTC"}

    def test_message_with_empty_payload(self):
        """测试空 payload 的消息"""
        msg = Message(msg_type=MessageType.HEARTBEAT)
        
        assert msg.payload == {}
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["payload"] == {}

    def test_message_with_none_worker_id(self):
        """测试 worker_id 为 None 的消息"""
        msg = Message(
            msg_type=MessageType.MARKET_DATA,
            worker_id=None,
            payload={"data": "test"}
        )
        
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["worker_id"] is None


class TestMessageTopic:
    """测试 MessageTopic 类"""

    def test_market_data_topic(self):
        """测试市场数据主题生成"""
        topic = MessageTopic.market_data("BTC/USDT", "kline")
        assert topic == "market.BTC/USDT.kline"
        
        topic = MessageTopic.market_data("ETH/USDT", "tick")
        assert topic == "market.ETH/USDT.tick"

    def test_control_topic(self):
        """测试控制命令主题生成"""
        topic = MessageTopic.control("worker-001")
        assert topic == "control.worker-001"

    def test_status_topic(self):
        """测试状态上报主题生成"""
        topic = MessageTopic.status("worker-001")
        assert topic == "status.worker-001"

    def test_topic_with_special_characters(self):
        """测试包含特殊字符的主题"""
        topic = MessageTopic.market_data("BTC-USDT_PERP", "depth")
        assert topic == "market.BTC-USDT_PERP.depth"


class TestSerializeDeserialize:
    """测试序列化和反序列化函数"""

    def test_serialize_message(self):
        """测试消息序列化为字节"""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            worker_id="worker-001",
            payload={"status": "running"}
        )
        
        data = serialize_message(msg)
        assert isinstance(data, bytes)
        
        # 验证可以反序列化
        restored = deserialize_message(data)
        assert restored.msg_type == MessageType.HEARTBEAT
        assert restored.worker_id == "worker-001"

    def test_deserialize_message(self):
        """测试从字节反序列化消息"""
        original = Message(
            msg_type=MessageType.STATUS_UPDATE,
            worker_id="worker-001",
            payload={"state": "running", "uptime": 3600}
        )
        
        data = original.to_json().encode('utf-8')
        restored = deserialize_message(data)
        
        assert restored.msg_type == MessageType.STATUS_UPDATE
        assert restored.worker_id == "worker-001"
        assert restored.payload["state"] == "running"
        assert restored.payload["uptime"] == 3600

    def test_serialize_deserialize_unicode(self):
        """测试包含 Unicode 字符的消息序列化"""
        msg = Message(
            msg_type=MessageType.ERROR,
            worker_id="worker-001",
            payload={"message": "错误信息", "detail": "详细描述"}
        )
        
        data = serialize_message(msg)
        restored = deserialize_message(data)
        
        assert restored.payload["message"] == "错误信息"
        assert restored.payload["detail"] == "详细描述"

    def test_deserialize_invalid_data(self):
        """测试反序列化无效数据"""
        with pytest.raises(json.JSONDecodeError):
            deserialize_message(b"invalid json data")

    def test_deserialize_empty_data(self):
        """测试反序列化空数据"""
        with pytest.raises(json.JSONDecodeError):
            deserialize_message(b"")
