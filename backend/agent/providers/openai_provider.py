"""OpenAI API 提供者实现"""

import os
from typing import Any

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """OpenAI API 提供者"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        """懒加载客户端"""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """发送聊天请求到 OpenAI API"""
        model = model or self.get_default_model()
        
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        
        if reasoning_effort and "o1" in model or "o3" in model:
            kwargs["reasoning_effort"] = reasoning_effort

        response = await self.client.chat.completions.create(**kwargs)
        
        choice = response.choices[0]
        message = choice.message
        
        # 提取工具调用
        tool_calls = []
        has_tool_calls = False
        
        if message.tool_calls:
            has_tool_calls = True
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })
        
        return LLMResponse(
            content=message.content,
            has_tool_calls=has_tool_calls,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            reasoning_content=getattr(message, "reasoning_content", None),
        )

    def get_default_model(self) -> str:
        """获取默认模型"""
        return os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
