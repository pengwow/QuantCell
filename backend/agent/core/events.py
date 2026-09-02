"""Agent 流式事件定义(原 agent/providers/base.py 的 StreamEvent 搬家)"""

from dataclasses import dataclass, field


@dataclass
class StreamEvent:
    """流式事件 - 用于 Agent Loop 向上层传递事件"""

    event_type: str  # start | content | reasoning | tool_calls | tool_start | tool_result | complete | error
    data: dict  # 事件数据
    timestamp: float = field(default_factory=lambda: __import__("time").time())
