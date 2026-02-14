"""
Worker IPC协议定义

定义Worker进程间通信的消息协议，包括消息类型、消息格式和序列化/反序列化
"""

import json
import time
import uuid
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field, asdict


class MessageType(Enum):
    """消息类型枚举"""
    # 数据消息
    MARKET_DATA = "market_data"
    TICK_DATA = "tick_data"
    BAR_DATA = "bar_data"
    ORDER_BOOK = "order_book"
    TRADE_DATA = "trade_data"

    # 控制消息
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    RESTART = "restart"
    RELOAD_CONFIG = "reload_config"
    UPDATE_PARAMS = "update_params"

    # 状态消息
    HEARTBEAT = "heartbeat"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    # 交易消息
    ORDER_REQUEST = "order_request"
    ORDER_RESPONSE = "order_response"
    POSITION_UPDATE = "position_update"
    BALANCE_UPDATE = "balance_update"

    # 系统消息
    METRICS = "metrics"
    LOG = "log"
    CONTROL = "control"


@dataclass
class Message:
    """
    消息基类

    Attributes:
        msg_type: 消息类型
        worker_id: Worker ID
        payload: 消息负载数据
        timestamp: 时间戳
        msg_id: 消息唯一ID
    """
    msg_type: MessageType
    worker_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_json(self) -> str:
        """将消息序列化为JSON字符串"""
        data = {
            "msg_type": self.msg_type.value,
            "worker_id": self.worker_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
        }
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        """从JSON字符串反序列化消息"""
        data = json.loads(json_str)
        return cls(
            msg_type=MessageType(data["msg_type"]),
            worker_id=data.get("worker_id"),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", time.time()),
            msg_id=data.get("msg_id", str(uuid.uuid4())),
        )

    @classmethod
    def create_heartbeat(cls, worker_id: str, status: str = "running") -> "Message":
        """创建心跳消息"""
        return cls(
            msg_type=MessageType.HEARTBEAT,
            worker_id=worker_id,
            payload={"status": status, "timestamp": time.time()},
        )

    @classmethod
    def create_market_data(
        cls,
        symbol: str,
        data_type: str,
        data: Dict[str, Any],
        source: str = "exchange",
    ) -> "Message":
        """创建市场数据消息"""
        return cls(
            msg_type=MessageType.MARKET_DATA,
            payload={
                "symbol": symbol,
                "data_type": data_type,
                "data": data,
                "source": source,
                "timestamp": time.time(),
            },
        )

    @classmethod
    def create_control(
        cls,
        command: MessageType,
        worker_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """创建控制命令消息"""
        return cls(
            msg_type=command,
            worker_id=worker_id,
            payload=params or {},
        )

    @classmethod
    def create_error(
        cls,
        worker_id: str,
        error_type: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """创建错误消息"""
        return cls(
            msg_type=MessageType.ERROR,
            worker_id=worker_id,
            payload={
                "error_type": error_type,
                "error_message": error_message,
                "details": details or {},
                "timestamp": time.time(),
            },
        )

    @classmethod
    def create_status_update(
        cls,
        worker_id: str,
        state: str,
        info: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """创建状态更新消息"""
        return cls(
            msg_type=MessageType.STATUS_UPDATE,
            worker_id=worker_id,
            payload={
                "state": state,
                "info": info or {},
                "timestamp": time.time(),
            },
        )

    @classmethod
    def create_metrics(
        cls,
        worker_id: str,
        metrics: Dict[str, Any],
    ) -> "Message":
        """创建指标消息"""
        return cls(
            msg_type=MessageType.METRICS,
            worker_id=worker_id,
            payload={
                "metrics": metrics,
                "timestamp": time.time(),
            },
        )

    @classmethod
    def create_order_request(
        cls,
        worker_id: str,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """创建订单请求消息"""
        return cls(
            msg_type=MessageType.ORDER_REQUEST,
            worker_id=worker_id,
            payload={
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": amount,
                "price": price,
                "params": params or {},
            },
        )

    @classmethod
    def create_log(
        cls,
        worker_id: str,
        level: str,
        message: str,
        source: str = "worker",
    ) -> "Message":
        """创建日志消息"""
        return cls(
            msg_type=MessageType.LOG,
            worker_id=worker_id,
            payload={
                "level": level,
                "message": message,
                "source": source,
                "timestamp": time.time(),
            },
        )


class MessageTopic:
    """消息主题工具类"""

    @staticmethod
    def market_data(symbol: str, data_type: str) -> str:
        """生成市场数据主题"""
        return f"market.{symbol}.{data_type}"

    @staticmethod
    def control(worker_id: str) -> str:
        """生成控制命令主题"""
        return f"control.{worker_id}"

    @staticmethod
    def status(worker_id: str) -> str:
        """生成状态上报主题"""
        return f"status.{worker_id}"

    @staticmethod
    def broadcast() -> str:
        """生成广播主题"""
        return "broadcast.all"


def serialize_message(message: Message) -> bytes:
    """
    序列化消息为字节

    Args:
        message: 消息对象

    Returns:
        字节数据
    """
    return message.to_json().encode("utf-8")


def deserialize_message(data: bytes) -> Message:
    """
    从字节反序列化消息

    Args:
        data: 字节数据

    Returns:
        消息对象
    """
    return Message.from_json(data.decode("utf-8"))
