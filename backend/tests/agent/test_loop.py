"""Agent 循环测试"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.core.loop import AgentLoop


class FakeLLMBackend:
    """模拟 axon_quant LLMBackend(返回原始 axon 格式,桥接层负责归一化)"""

    def __init__(self, responses=None, stream_chunks=None):
        # responses: 依次返回的 chat 原始 dict 列表
        self.responses = responses or []
        self.stream_chunks = stream_chunks or []
        self.call_count = 0

    def _next(self):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return {"content": "Mock response", "reasoning_content": "", "finish_reason": "Stop"}

    async def chat_async(self, messages):
        return self._next()

    async def chat_with_tools_async(self, messages, tools):
        return self._next()

    async def stream_chat_async(self, messages):
        for c in self.stream_chunks:
            yield c


def text_response(content: str) -> dict:
    """构造纯文本响应的原始 axon dict"""
    return {"content": content, "reasoning_content": "", "finish_reason": "Stop"}


def tool_call_response(tool_name: str, arguments: dict, call_id: str = "call_1") -> dict:
    """构造工具调用响应的原始 axon dict"""
    return {
        "content": "",
        "reasoning_content": "",
        "finish_reason": "ToolCalls",
        "tool_calls": json.dumps([{"id": call_id, "function_name": tool_name, "arguments": json.dumps(arguments)}]),
    }


class TestAgentLoop:
    """测试 Agent 循环"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.mark.asyncio
    async def test_process_message_simple(self, temp_workspace):
        """测试简单消息处理"""
        backend = FakeLLMBackend([text_response("Hello!")])

        agent = AgentLoop(
            llm_backend=backend,
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

        backend = FakeLLMBackend(
            [
                tool_call_response("read_file", {"path": "test.txt"}),
                text_response("File content: Test content"),
            ]
        )

        agent = AgentLoop(
            llm_backend=backend,
            workspace=temp_workspace,
        )
        agent.register_tool(ReadFileTool(temp_workspace))

        response = await agent.process_message("Read the test file")

        assert "Test content" in response

    @pytest.mark.asyncio
    async def test_process_message_stream(self, temp_workspace):
        """测试流式消息处理"""
        backend = FakeLLMBackend(
            stream_chunks=[
                {"type": "content", "content": "Stream response"},
                {"type": "done", "finish_reason": "Stop"},
            ]
        )

        agent = AgentLoop(
            llm_backend=backend,
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
    async def test_iter_message_stream(self, temp_workspace):
        """async-for 模式应转发全部流事件（SSE 桥接契约）"""
        backend = FakeLLMBackend(
            stream_chunks=[
                {"type": "content", "content": "Stream response"},
                {"type": "done", "finish_reason": "Stop"},
            ]
        )

        agent = AgentLoop(
            llm_backend=backend,
            workspace=temp_workspace,
        )

        events = [event async for event in agent.iter_message_stream("Hello")]

        assert len(events) > 0
        event_types = [e.event_type for e in events]
        assert "start" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_iter_message_stream_propagates_error(self, temp_workspace):
        """后台任务异常应经队列桥接在消费侧重新抛出"""
        agent = AgentLoop(
            llm_backend=FakeLLMBackend([]),
            workspace=temp_workspace,
        )

        async def _boom(content, session_key, on_stream=None):
            raise RuntimeError("boom")

        agent._run_message_stream = _boom

        with pytest.raises(RuntimeError, match="boom"):
            _ = [event async for event in agent.iter_message_stream("Hello")]

    @pytest.mark.asyncio
    async def test_max_iterations(self, temp_workspace):
        """测试最大迭代限制"""
        # 创建一个总是返回工具调用的 backend
        backend = FakeLLMBackend([tool_call_response("mock_tool", {})] * 10)

        agent = AgentLoop(
            llm_backend=backend,
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
        # 创建一个会抛出异常的 backend
        backend = FakeLLMBackend([])
        backend.chat_async = AsyncMock(side_effect=Exception("API Error"))
        backend.chat_with_tools_async = AsyncMock(side_effect=Exception("API Error"))

        agent = AgentLoop(
            llm_backend=backend,
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
        backend = FakeLLMBackend([text_response("Direct response")])

        agent = AgentLoop(
            llm_backend=backend,
            workspace=temp_workspace,
        )

        response = await agent.process_direct("Hello")

        assert response == "Direct response"

    @pytest.mark.asyncio
    async def test_save_turn(self, temp_workspace):
        """测试保存对话轮次"""
        backend = FakeLLMBackend([text_response("Response")])

        agent = AgentLoop(
            llm_backend=backend,
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
        backend = FakeLLMBackend([text_response("Response")])

        agent = AgentLoop(
            llm_backend=backend,
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
