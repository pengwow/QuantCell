"""LLM 提供者基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResponse:
    """LLM 响应数据结构"""
    content: str | None
    has_tool_calls: bool
    tool_calls: list[Any]
    finish_reason: str | None = None
    reasoning_content: str | None = None
    thinking_blocks: list[dict] | None = None


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
    def get_default_model(self) -> str:
        """获取默认模型名称"""
        pass
