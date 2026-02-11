"""
ZeroMQ 消息协议定义

定义 Worker 进程间通信的消息格式和类型
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
import time


class MessageType(Enum):
    """消息类型枚举"""

    # 数据消息
    MARKET_DATA = "market_data"  # 市场数据（K线、Tick等）
    TICK_DATA = "tick_data"  # Tick 数据
    BAR_DATA = "bar_data"  # K线数据
    DEPTH_DATA = "depth_data"  # 深度数据

    # 控制消息
    START = "start"  # 启动策略
    STOP = "stop"  # 停止策略
    PAUSE = "pause"  # 暂停策略
    RESUME = "resume"  # 恢复策略
    RELOAD_CONFIG = "reload_config"  # 重载配置
    UPDATE_PARAMS = "update_params"  # 更新参数

    # 状态消息
    HEARTBEAT = "heartbeat"  # 心跳
    STATUS_UPDATE = "status_update"  # 状态更新
    ERROR = "error"  # 错误报告
    WARNING = "warning"  # 警告

    # 订单消息
    ORDER_REQUEST = "order_request"  # 订单请求
    ORDER_RESPONSE = "order_response"  # 订单响应
    ORDER_UPDATE = "order_update"  # 订单状态更新

    # 持仓消息
    POSITION_UPDATE = "position_update"  # 持仓更新
    POSITION_SYNC = "position_sync"  # 持仓同步请求

    # 账户消息
    ACCOUNT_UPDATE = "account_update"  # 账户更新
    BALANCE_UPDATE = "balance_update"  # 余额更新


@dataclass
class Message:
    """
    消息结构

    用于 Worker 进程间通信的标准消息格式
    """

    msg_type: MessageType
    payload: Dict[str, Any] = field(default_factory=dict)
    worker_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    msg_id: Optional[str] = None

    def to_json(self) -> str:
        """
        将消息序列化为 JSON 字符串

        Returns:
            JSON 字符串
        """
        return json.dumps({
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "worker_id": self.worker_id,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
        }, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "Message":
        """
        从 JSON 字符串反序列化消息

        Args:
            data: JSON 字符串

        Returns:
            Message 实例
        """
        obj = json.loads(data)
        return cls(
            msg_type=MessageType(obj["msg_type"]),
            payload=obj.get("payload", {}),
            worker_id=obj.get("worker_id"),
            timestamp=obj.get("timestamp", time.time()),
            msg_id=obj.get("msg_id"),
        )

    @classmethod
    def create_heartbeat(cls, worker_id: str, status: str = "running") -> "Message":
        """
        创建心跳消息

        Args:
            worker_id: Worker ID
            status: 当前状态

        Returns:
            心跳消息
        """
        return cls(
            msg_type=MessageType.HEARTBEAT,
            worker_id=worker_id,
            payload={"status": status},
        )

    @classmethod
    def create_market_data(
        cls,
        symbol: str,
        data_type: str,
        data: Dict[str, Any],
        source: Optional[str] = None,
    ) -> "Message":
        """
        创建市场数据消息

        Args:
            symbol: 交易对
            data_type: 数据类型 (kline, tick, depth)
            data: 数据内容
            source: 数据来源

        Returns:
            市场数据消息
        """
        return cls(
            msg_type=MessageType.MARKET_DATA,
            payload={
                "symbol": symbol,
                "data_type": data_type,
                "data": data,
                "source": source,
            },
        )

    @classmethod
    def create_control(
        cls,
        msg_type: MessageType,
        worker_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> "Message":
        """
        创建控制消息

        Args:
            msg_type: 控制消息类型 (START, STOP, PAUSE, RESUME)
            worker_id: Worker ID
            params: 控制参数

        Returns:
            控制消息
        """
        return cls(
            msg_type=msg_type,
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
        """
        创建错误消息

        Args:
            worker_id: Worker ID
            error_type: 错误类型
            error_message: 错误信息
            details: 详细错误信息

        Returns:
            错误消息
        """
        return cls(
            msg_type=MessageType.ERROR,
            worker_id=worker_id,
            payload={
                "error_type": error_type,
                "error_message": error_message,
                "details": details or {},
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
        """
        创建订单请求消息

        Args:
            worker_id: Worker ID
            symbol: 交易对
            side: 买卖方向 (buy/sell)
            order_type: 订单类型 (market/limit)
            amount: 数量
            price: 价格（限价单需要）
            params: 其他参数

        Returns:
            订单请求消息
        """
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


# 消息主题定义
class MessageTopic:
    """消息主题常量"""

    @staticmethod
    def market_data(symbol: str, data_type: str = "kline") -> str:
        """
        生成市场数据主题

        Args:
            symbol: 交易对
            data_type: 数据类型

        Returns:
            主题字符串
        """
        return f"market.{symbol}.{data_type}"

    @staticmethod
    def control(worker_id: str) -> str:
        """
        生成控制命令主题

        Args:
            worker_id: Worker ID

        Returns:
            主题字符串
        """
        return f"control.{worker_id}"

    @staticmethod
    def status(worker_id: str) -> str:
        """
        生成状态上报主题

        Args:
            worker_id: Worker ID

        Returns:
            主题字符串
        """
        return f"status.{worker_id}"


# 序列化/反序列化辅助函数
def serialize_message(message: Message) -> bytes:
    """
    将消息序列化为字节

    Args:
        message: 消息实例

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
        消息实例
    """
    return Message.from_json(data.decode("utf-8"))
