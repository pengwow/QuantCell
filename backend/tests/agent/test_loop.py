"""Agent 循环测试"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.core.loop import AgentLoop
from agent.providers.base import LLMProvider, LLMResponse, StreamChunk


class MockProvider(LLMProvider):
    """模拟 LLM 提供者"""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0

    async def chat(self, **kwargs):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        return LLMResponse(
            content="Mock response",
            has_tool_calls=False,
            tool_calls=[],
        )

    async def chat_stream(self, **kwargs):
        for response in self.responses:
            yield StreamChunk(
                content=response.content,
                delta=response.content,
                finish_reason="stop" if not response.has_tool_calls else "tool_calls",
                tool_calls=response.tool_calls if response.has_tool_calls else None,
            )

    def get_default_model(self):
        return "mock-model"


class TestAgentLoop:
    """测试 Agent 循环"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.mark.asyncio
    async def test_process_message_simple(self, temp_workspace):
        """测试简单消息处理"""
        provider = MockProvider(
            [
                LLMResponse(
                    content="Hello!",
                    has_tool_calls=False,
                    tool_calls=[],
                )
            ]
        )

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )

        response = await agent.process_message("Hi")

        assert response == "Hello!"
        assert len(agent.sessions.get_or_create("default").messages) > 0

    @pytest.mark.asyncio
    async def test_process_message_with_tool(self, temp_workspace):
        """测试带工具调用的消息处理"""
        from agent.tools.filesystem import ReadFileTool

        # 创建测试文件
        test_file = temp_workspace / "test.txt"
        test_file.write_text("Test content")

        provider = MockProvider(
            [
                LLMResponse(
                    content=None,
                    has_tool_calls=True,
                    tool_calls=[
                        {
                            "id": "call_1",
                            "name": "read_file",
                            "arguments": {"path": "test.txt"},
                        }
                    ],
                ),
                LLMResponse(
                    content="File content: Test content",
                    has_tool_calls=False,
                    tool_calls=[],
                ),
            ]
        )

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )
        agent.register_tool(ReadFileTool(temp_workspace))

        response = await agent.process_message("Read the test file")

        assert "Test content" in response

    @pytest.mark.asyncio
    async def test_process_message_stream(self, temp_workspace):
        """测试流式消息处理"""
        provider = MockProvider(
            [
                LLMResponse(
                    content="Stream response",
                    has_tool_calls=False,
                    tool_calls=[],
                )
            ]
        )

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )

        events = []

        async def on_stream(event):
            events.append(event)

        await agent.process_message_stream("Hello", on_stream=on_stream)

        assert len(events) > 0
        # 应该有 start, content, complete 事件
        event_types = [e.event_type for e in events]
        assert "start" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_max_iterations(self, temp_workspace):
        """测试最大迭代限制"""
        # 创建一个总是返回工具调用的provider
        tool_response = LLMResponse(
            content=None,
            has_tool_calls=True,
            tool_calls=[
                {
                    "id": "call_1",
                    "name": "mock_tool",
                    "arguments": {},
                }
            ],
        )

        provider = MockProvider([tool_response] * 10)

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
            max_iterations=3,
        )

        # 注册一个mock工具
        mock_tool = MagicMock()
        mock_tool.name = "mock_tool"
        mock_tool.execute = AsyncMock(return_value="Tool result")
        mock_tool.to_schema.return_value = {
            "type": "function",
            "function": {"name": "mock_tool"},
        }
        agent.register_tool(mock_tool)

        response = await agent.process_message("Do something")

        # 应该达到最大迭代次数
        assert "最大迭代次数" in response

    @pytest.mark.asyncio
    async def test_error_handling(self, temp_workspace):
        """测试错误处理"""
        # 创建一个会抛出异常的provider
        provider = MockProvider([])
        provider.chat = AsyncMock(side_effect=Exception("API Error"))

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )

        with pytest.raises(Exception) as exc_info:
            await agent.process_message("Hello")

        assert "API Error" in str(exc_info.value)

    def test_strip_think(self):
        """测试移除think标签"""
        text_with_think = """
<think>
This is thinking content.
</think>
This is the actual response."""

        result = AgentLoop._strip_think(text_with_think)

        assert "thinking content" not in result
        assert "actual response" in result

    def test_strip_think_none(self):
        """测试移除None的think标签"""
        result = AgentLoop._strip_think(None)
        assert result is None

    def test_strip_think_empty(self):
        """测试移除空的think标签"""
        result = AgentLoop._strip_think("")
        assert result is None

    def test_tool_hint(self):
        """测试工具提示格式化"""
        tool_calls = [
            {"name": "read_file", "arguments": {"path": "test.txt"}},
            {
                "name": "write_file",
                "arguments": {"path": "output.txt", "content": "data"},
            },
        ]

        hint = AgentLoop._tool_hint(tool_calls)

        assert "read_file" in hint
        assert "write_file" in hint

    def test_tool_hint_long_args(self):
        """测试长参数的工具提示"""
        tool_calls = [
            {"name": "write_file", "arguments": {"content": "a" * 100}},
        ]

        hint = AgentLoop._tool_hint(tool_calls)

        assert "write_file" in hint
        assert "…" in hint  # 应该被截断

    @pytest.mark.asyncio
    async def test_process_direct(self, temp_workspace):
        """测试直接处理消息"""
        provider = MockProvider(
            [
                LLMResponse(
                    content="Direct response",
                    has_tool_calls=False,
                    tool_calls=[],
                )
            ]
        )

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )

        response = await agent.process_direct("Hello")

        assert response == "Direct response"

    @pytest.mark.asyncio
    async def test_save_turn(self, temp_workspace):
        """测试保存对话轮次"""
        provider = MockProvider(
            [
                LLMResponse(
                    content="Response",
                    has_tool_calls=False,
                    tool_calls=[],
                )
            ]
        )

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )

        # 处理消息
        await agent.process_message("Hello")

        # 获取会话
        session = agent.sessions.get_or_create("default")

        # 应该有用户消息和助手消息
        user_messages = [m for m in session.messages if m.get("role") == "user"]
        assistant_messages = [m for m in session.messages if m.get("role") == "assistant"]

        assert len(user_messages) >= 1
        assert len(assistant_messages) >= 1

    @pytest.mark.asyncio
    async def test_session_key(self, temp_workspace):
        """测试不同的会话key"""
        provider = MockProvider(
            [
                LLMResponse(
                    content="Response",
                    has_tool_calls=False,
                    tool_calls=[],
                )
            ]
        )

        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )

        # 处理两个不同会话的消息
        await agent.process_message("Hello", session_key="session-1")
        await agent.process_message("World", session_key="session-2")

        # 验证会话是分开的
        session1 = agent.sessions.get_or_create("session-1")
        session2 = agent.sessions.get_or_create("session-2")

        assert session1.key == "session-1"
        assert session2.key == "session-2"
        assert session1.messages != session2.messages
