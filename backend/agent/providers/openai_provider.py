"""OpenAI API 提供者实现"""

import json
import os
import time
from typing import Any

from openai import AsyncOpenAI

from .base import LLMProvider, LLMResponse

logger = None

def _get_logger():
    global logger
    if logger is None:
        from utils.logger import get_logger, LogType
        logger = get_logger(__name__, LogType.APPLICATION)
    return logger


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
            from openai import Timeout
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
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
        import json

        log = _get_logger()
        model = model or self.get_default_model()

        log.info(f"[OpenAIProvider] 准备调用API: model={model}, messages={len(messages)}, tools={len(tools) if tools else 0}")

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if reasoning_effort and ("o1" in model or "o3" in model):
            kwargs["reasoning_effort"] = reasoning_effort

        # 详细记录 API 请求参数
        log.info("=" * 80)
        log.info("[OpenAIProvider] 📤 API 请求详情")
        log.info("-" * 80)
        log.info(f"API 接口: {self.base_url or 'https://api.openai.com'}/v1/chat/completions")
        log.info(f"模型名称: {model}")
        log.info(f"温度参数: {temperature}")
        log.info(f"最大 Token: {max_tokens}")

        if reasoning_effort and ("o1" in model or "o3" in model):
            log.info(f"推理强度: {reasoning_effort}")

        log.info(f"\n📨 Messages ({len(messages)} 条):")
        for idx, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if isinstance(content, list):
                content_str = f"[{len(content)} 个内容块]"
                log.info(f"  {idx}. [{role}] {content_str}")
                for c_idx, c in enumerate(content[:3], 1):
                    if c.get("type") == "text":
                        text = c.get("text", "")[:200]
                        log.info(f"      -> [{c_idx}] text: {text}...")
                    elif c.get("type") == "tool_use":
                        log.info(f"      -> [{c_idx}] tool_use: {c.get('name', '')}")
                    elif c.get("type") == "tool_result":
                        tool_content = str(c.get("content", ""))[:150]
                        log.info(f"      -> [{c_idx}] tool_result: {tool_content}...")
                if len(content) > 3:
                    log.info(f"      ... 还有 {len(content) - 3} 个内容块")
            else:
                content_preview = str(content)[:200] + ("..." if len(str(content)) > 200 else "")
                log.info(f"  {idx}. [{role}] {content_preview}")

            if msg.get("tool_calls"):
                log.info(f"      🔧 工具调用:")
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    args_preview = json.dumps(func.get("arguments", {}), ensure_ascii=False)[:150]
                    log.info(f"         - {func.get('name', 'unknown')}({args_preview})")

            if msg.get("name"):
                log.info(f"      📛 工具名: {msg.get('name')}")

        if tools:
            log.info(f"\n🔧 工具定义 ({len(tools)} 个):")
            for idx, tool in enumerate(tools, 1):
                func = tool.get("function", {})
                name = func.get("name", "unknown")
                desc = func.get("description", "")[:100]
                params = func.get("parameters", {})
                props = params.get("properties", {}) if isinstance(params, dict) else {}
                required = params.get("required", []) if isinstance(params, dict) else []

                log.info(f"  {idx}. {name}")
                log.info(f"     描述: {desc}")
                if props:
                    param_list = [f"{k}" for k in list(props.keys())[:5]]
                    if len(props) > 5:
                        param_list.append(f"...+{len(props)-5}")
                    req_marker = " [必填]" if name in required else ""
                    log.info(f"     参数: {', '.join(param_list)}{req_marker}")

        log.info("-" * 80)
        log.info("=" * 80)

        try:
            start_time = time.time()
            log.debug(f"[OpenAIProvider] 发送请求到 {self.base_url or 'OpenAI API'}...")

            response = await self.client.chat.completions.create(**kwargs)

            elapsed = time.time() - start_time
            log.info(f"[OpenAIProvider] API 响应成功, 耗时: {elapsed:.2f}s, usage={response.usage}")

            choice = response.choices[0]
            message = choice.message

            # 记录响应详情
            log.info("\n[OpenAIProvider] 📥 API 响应详情")
            log.info("-" * 80)
            log.info(f"完成原因: {choice.finish_reason}")
            log.info(f"Token 使用: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}, total={response.usage.total_tokens}")

            if message.content:
                content_preview = message.content[:300] + ("..." if len(message.content) > 300 else "")
                log.info(f"响应内容: {content_preview}")

            if hasattr(message, 'reasoning_content') and message.reasoning_content:
                reasoning_preview = message.reasoning_content[:200] + ("..." if len(message.reasoning_content) > 200 else "")
                log.info(f"推理过程: {reasoning_preview}")

            # 提取工具调用
            tool_calls = []
            has_tool_calls = False

            if message.tool_calls:
                has_tool_calls = True
                log.info(f"\n🔧 返回的工具调用 ({len(message.tool_calls)} 个):")
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })
                    args_preview = json.dumps(tc.function.arguments, ensure_ascii=False)[:200]
                    log.info(f"  - {tc.function.name}({args_preview})")

            log.info("-" * 80)

            return LLMResponse(
                content=message.content,
                has_tool_calls=has_tool_calls,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
                reasoning_content=getattr(message, "reasoning_content", None),
            )

        except Exception as e:
            log.error(f"[OpenAIProvider] API 调用异常: {type(e).__name__}: {e}")
            raise

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ):
        """流式聊天请求 - 实时返回响应内容"""
        from .base import StreamChunk

        log = _get_logger()
        model = model or self.get_default_model()

        log.info(f"[OpenAIProvider] 准备调用流式API: model={model}, messages={len(messages)}, tools={len(tools) if tools else 0}")

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,  # 启用流式
            "stream_options": {"include_usage": True},  # 获取最终 usage 统计
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if reasoning_effort and ("o1" in model or "o3" in model):
            kwargs["reasoning_effort"] = reasoning_effort

        try:
            start_time = time.time()
            log.debug(f"[OpenAIProvider] 发送流式请求到 {self.base_url or 'OpenAI API'}...")

            stream = await self.client.chat.completions.create(**kwargs)

            full_content = ""
            accumulated_tool_calls: dict[int, dict] = {}

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # 提取文本增量并立即 yield
                text_delta = delta.content or ""
                if text_delta:
                    full_content += text_delta
                    yield StreamChunk(
                        content=full_content,
                        delta=text_delta,
                    )

                # 提取推理过程（DeepSeek-R1 等）
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    yield StreamChunk(
                        reasoning_content=delta.reasoning_content,
                    )

                # 累积工具调用参数（分多次发送，需要拼接）
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }

                        if tc.id:
                            accumulated_tool_calls[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                accumulated_tool_calls[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

                # 检查是否完成
                finish_reason = chunk.choices[0].finish_reason
                if finish_reason:
                    # 收集并整理所有工具调用
                    tool_calls_list = []
                    for idx in sorted(accumulated_tool_calls.keys()):
                        tc_data = accumulated_tool_calls[idx]
                        # 尝试解析 arguments JSON
                        try:
                            tc_data["arguments"] = json.loads(tc_data["arguments"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                        tool_calls_list.append(tc_data)

                    usage_info = None
                    if chunk.usage:
                        usage_info = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens,
                        }

                    elapsed = time.time() - start_time
                    log.info(f"[OpenAIProvider] 流式API响应完成, 耗时: {elapsed:.2f}s, finish_reason={finish_reason}")

                    yield StreamChunk(
                        content=full_content,
                        finish_reason=finish_reason,
                        is_tool_call=len(tool_calls_list) > 0,
                        tool_calls=tool_calls_list if tool_calls_list else None,
                        usage=usage_info,
                    )

                    break  # 流结束

        except Exception as e:
            elapsed = time.time() - start_time
            log.error(f"[OpenAIProvider] 流式API调用异常: {type(e).__name__}: {e} (耗时: {elapsed:.2f}s)")
            raise

    def get_default_model(self) -> str:
        """获取默认模型"""
        return os.environ.get("DEFAULT_MODEL", "gpt-4o-mini")
