"""Agent 循环测试"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from agent.core.loop import AgentLoop
from agent.providers.base import LLMProvider, LLMResponse


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
        provider = MockProvider([
            LLMResponse(
                content="Hello!",
                has_tool_calls=False,
                tool_calls=[],
            )
        ])
        
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
        
        provider = MockProvider([
            LLMResponse(
                content=None,
                has_tool_calls=True,
                tool_calls=[{
                    "id": "call_1",
                    "name": "read_file",
                    "arguments": {"path": "test.txt"},
                }],
            ),
            LLMResponse(
                content="File content: Test content",
                has_tool_calls=False,
                tool_calls=[],
            ),
        ])
        
        agent = AgentLoop(
            provider=provider,
            workspace=temp_workspace,
        )
        agent.register_tool(ReadFileTool(temp_workspace))
        
        response = await agent.process_message("Read the test file")
        
        assert "Test content" in response
