"""ZMQ 消息协议定义。

定义 Worker 与 Orchestrator 之间的消息格式、常量和序列化工具。
所有消息使用 JSON 编码，通过 ZMQ frame 传递。
"""

from __future__ import annotations

import json
import time
import uuid
from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    """ZMQ 消息类型。"""

    COMMAND = "command"
    RESPONSE = "response"
    EVENT = "event"


class EventType(StrEnum):
    """事件消息子类型。"""

    TRADE = "trade"
    HEARTBEAT = "heartbeat"
    LOG = "log"
    ORDER = "order"
    POSITION = "position"


# 命令常量
CMD_PING = "ping"
CMD_START = "start"
CMD_STOP = "stop"
CMD_RESTART = "restart"
CMD_STATUS = "status"
CMD_UPDATE_PARAMS = "update_params"

# 响应状态常量
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_TIMEOUT = "timeout"

# ZMQ 默认地址
DEFAULT_EVENT_PULL_ADDR = "tcp://127.0.0.1:5558"
DEFAULT_CMD_PUSH_ADDR = "tcp://127.0.0.1:5559"

# 超时配置（秒）
DEFAULT_CMD_TIMEOUT = 5.0
DEFAULT_HANDSHAKE_TIMEOUT = 5.0
DEFAULT_HEALTH_CHECK_INTERVAL = 30.0
DEFAULT_OFFLINE_THRESHOLD = 60.0


def encode_message(msg: dict[str, Any]) -> bytes:
    """将消息 dict 序列化为 JSON bytes。"""
    return json.dumps(msg, ensure_ascii=False).encode("utf-8")


def decode_message(data: bytes) -> dict[str, Any]:
    """将 bytes 反序列化为消息 dict。"""
    try:
        msg = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"Invalid JSON: {e}") from e
    if not isinstance(msg, dict):
        raise ValueError("Message must be a dict")
    return msg


def validate_message(msg: dict[str, Any]) -> str | None:
    """验证消息格式，返回错误信息或 None。"""
    msg_type = msg.get("type")
    if msg_type not in (MessageType.COMMAND, MessageType.RESPONSE, MessageType.EVENT):
        return f"Invalid or missing 'type': {msg_type}"
    if "worker_id" not in msg:
        return "Missing required field: worker_id"
    if "timestamp" not in msg:
        return "Missing required field: timestamp"
    if msg_type == MessageType.COMMAND and "cmd" not in msg:
        return "Command message missing 'cmd' field"
    if msg_type == MessageType.COMMAND and "request_id" not in msg:
        return "Command message missing 'request_id' field"
    if msg_type == MessageType.RESPONSE and "request_id" not in msg:
        return "Response message missing 'request_id' field"
    if msg_type == MessageType.EVENT and "event_type" not in msg:
        return "Event message missing 'event_type' field"
    return None


def make_command(
    worker_id: int, cmd: str, params: dict[str, Any] | None = None, request_id: str | None = None
) -> dict[str, Any]:
    """构建命令消息。"""
    return {
        "type": MessageType.COMMAND,
        "worker_id": worker_id,
        "cmd": cmd,
        "params": params or {},
        "request_id": request_id or str(uuid.uuid4()),
        "timestamp": time.time(),
    }


def make_response(worker_id: int, request_id: str, status: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """构建响应消息。"""
    return {
        "type": MessageType.RESPONSE,
        "worker_id": worker_id,
        "request_id": request_id,
        "status": status,
        "data": data or {},
        "timestamp": time.time(),
    }


def make_event(worker_id: int, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """构建事件消息。"""
    return {
        "type": MessageType.EVENT,
        "worker_id": worker_id,
        "event_type": event_type,
        "payload": payload or {},
        "timestamp": time.time(),
    }
