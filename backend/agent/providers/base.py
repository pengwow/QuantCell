"""LLM 提供者基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class LLMResponse:
    """LLM 响应数据结构"""
    content: str | None
    has_tool_calls: bool
    tool_calls: list[Any]
    finish_reason: str | None = None
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None


@dataclass
class StreamChunk:
    """流式响应数据块"""
    content: str | None = None           # 累积的完整文本内容
    delta: str | None = None             # 本次增量文本（用于实时显示）
    finish_reason: str | None = None     # 完成原因 (stop/tool_calls/error)
    is_tool_call: bool = False           # 是否包含工具调用
    tool_calls: list[dict] | None = None # 工具调用信息列表
    usage: dict | None = None            # Token 使用量统计
    reasoning_content: str | None = None # 推理过程内容（DeepSeek-R1 等）

    @property
    def chunk_type(self) -> str:
        """返回块类型标识"""
        if self.is_tool_call:
            return "tool_call"
        if self.finish_reason:
            return "done"
        if self.reasoning_content:
            return "reasoning"
        if self.delta or self.content:
            return "content"
        return "empty"


@dataclass
class StreamEvent:
    """流式事件 - 用于 Agent Loop 向上层传递事件"""
    event_type: str  # start | content | reasoning | tool_calls | tool_start | tool_result | complete | error
    data: dict       # 事件数据
    timestamp: float = field(default_factory=lambda: __import__('time').time())


class LLMProvider(ABC):
    """LLM 提供者抽象基类"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """
        发送聊天请求

        Args:
            messages: 消息列表
            tools: 可用工具定义
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            reasoning_effort: 推理努力程度

        Returns:
            LLMResponse 对象
        """
        pass

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        流式聊天请求 - 实时返回响应内容

        Args:
            messages: 消息列表
            tools: 可用工具定义
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            reasoning_effort: 推理努力程度

        Yields:
            StreamChunk: 包含增量内容的流式数据块
                - 文本增量 (delta) 用于实时显示
                - 累积内容 (content) 用于完整记录
                - 工具调用 (tool_calls) 在完成时返回
                - 使用统计 (usage) 在最后一个 chunk 返回
        """
        pass

    @abstractmethod
    def get_default_model(self) -> str:
        """获取默认模型名称"""
        pass
