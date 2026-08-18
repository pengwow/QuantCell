"""上下文构建测试 - ContextBuilder"""

import pytest

from agent.core.context import ContextBuilder


class TestContextBuilder:
    """测试 ContextBuilder"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def context(self, temp_workspace):
        return ContextBuilder(temp_workspace)

    def test_build_system_prompt_basic(self, context, temp_workspace):
        """测试基本系统提示词构建"""
        prompt = context.build_system_prompt()

        assert "QuantCell Agent" in prompt
        assert "量化交易" in prompt
        assert "工作空间" in prompt

    def test_build_system_prompt_with_identity(self, context):
        """测试系统提示词包含身份信息"""
        prompt = context.build_system_prompt()

        assert "你是 QuantCell Agent" in prompt
        assert "专业的量化交易 AI 助手" in prompt

    def test_build_system_prompt_with_bootstrap_files(self, context, temp_workspace):
        """测试引导文件加载"""
        # 创建引导文件
        agents_file = temp_workspace / "AGENTS.md"
        agents_file.write_text("# Agent Rules\n\nBe helpful.", encoding="utf-8")

        soul_file = temp_workspace / "SOUL.md"
        soul_file.write_text("# Soul\n\nI am a trading bot.", encoding="utf-8")

        prompt = context.build_system_prompt()

        assert "Agent Rules" in prompt
        assert "Be helpful" in prompt
        assert "Soul" in prompt
        assert "I am a trading bot" in prompt

    def test_build_system_prompt_with_memory(self, context, temp_workspace):
        """测试记忆上下文注入"""
        # 创建记忆文件
        memory_dir = temp_workspace / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        memory_file = memory_dir / "MEMORY.md"
        memory_file.write_text("- 用户偏好: 简洁的回答", encoding="utf-8")

        prompt = context.build_system_prompt()

        assert "长期记忆" in prompt
        assert "用户偏好" in prompt

    def test_build_system_prompt_with_skills(self, context, temp_workspace):
        """测试技能上下文注入"""
        # 创建技能目录
        skills_dir = temp_workspace / "skills" / "test-skill"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text(
            "---\ndescription: Test skill\n---\n\n# Test Skill\n\nDo something.",
            encoding="utf-8",
        )

        prompt = context.build_system_prompt()

        assert "技能" in prompt

    def test_build_messages(self, context):
        """测试消息列表构建"""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        current_message = "What is 2+2?"

        messages = context.build_messages(
            history=history,
            current_message=current_message,
        )

        # 应该包含：system + history + current
        assert len(messages) >= 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "Hi!"
        assert messages[-1]["role"] == "user"
        assert "What is 2+2?" in messages[-1]["content"]

    def test_build_messages_with_channel(self, context):
        """测试带频道信息的消息构建"""
        messages = context.build_messages(
            history=[],
            current_message="Test",
            channel="telegram",
            chat_id="12345",
        )

        user_message = messages[-1]["content"]
        assert "telegram" in user_message
        assert "12345" in user_message

    def test_build_messages_with_skills(self, context, temp_workspace):
        """测试带技能的消息构建"""
        # 创建技能
        skills_dir = temp_workspace / "skills" / "my-skill"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("# My Skill\n\nUse this skill.", encoding="utf-8")

        messages = context.build_messages(
            history=[],
            current_message="Test",
            skill_names=["my-skill"],
        )

        system_prompt = messages[0]["content"]
        assert "my-skill" in system_prompt

    def test_add_tool_result(self, context):
        """测试添加工具结果"""
        messages = []

        messages = context.add_tool_result(
            messages=messages,
            tool_call_id="call_123",
            tool_name="read_file",
            result="File content here",
        )

        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "call_123"
        assert messages[0]["name"] == "read_file"
        assert messages[0]["content"] == "File content here"

    def test_add_assistant_message(self, context):
        """测试添加助手消息"""
        messages = []

        # 纯文本消息
        messages = context.add_assistant_message(
            messages=messages,
            content="Hello!",
        )

        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] == "Hello!"
        assert "tool_calls" not in messages[0]

    def test_add_assistant_message_with_tool_calls(self, context):
        """测试添加带工具调用的助手消息"""
        messages = []
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "test.txt"}',
                },
            }
        ]

        messages = context.add_assistant_message(
            messages=messages,
            content=None,
            tool_calls=tool_calls,
        )

        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["content"] is None
        assert "tool_calls" in messages[0]
        assert len(messages[0]["tool_calls"]) == 1

    def test_add_assistant_message_with_reasoning(self, context):
        """测试添加带推理内容的助手消息"""
        messages = []

        messages = context.add_assistant_message(
            messages=messages,
            content="The answer is 4.",
            reasoning_content="Let me think: 2+2=4",
        )

        assert len(messages) == 1
        assert messages[0]["reasoning_content"] == "Let me think: 2+2=4"

    def test_runtime_context(self, context):
        """测试运行时上下文构建"""
        runtime_ctx = context._build_runtime_context(
            channel="web",
            chat_id="session-123",
        )

        assert "当前时间" in runtime_ctx
        assert "web" in runtime_ctx
        assert "session-123" in runtime_ctx

    def test_runtime_context_without_channel(self, context):
        """测试无频道的运行时上下文"""
        runtime_ctx = context._build_runtime_context(
            channel=None,
            chat_id=None,
        )

        assert "当前时间" in runtime_ctx
        assert "频道" not in runtime_ctx

    def test_load_bootstrap_files_empty(self, context):
        """测试空引导文件加载"""
        bootstrap = context._load_bootstrap_files()

        # 空目录应该返回空字符串
        assert bootstrap == ""

    def test_load_bootstrap_files_partial(self, context, temp_workspace):
        """测试部分引导文件加载"""
        # 只创建部分文件
        agents_file = temp_workspace / "AGENTS.md"
        agents_file.write_text("# Agents", encoding="utf-8")

        bootstrap = context._load_bootstrap_files()

        assert "Agents" in bootstrap
        # 其他文件不应该出现
        assert "SOUL" not in bootstrap

    def test_get_identity(self, context):
        """测试身份信息获取"""
        identity = context._get_identity()

        assert "QuantCell Agent" in identity
        assert "量化交易" in identity
        assert "工作空间" in identity

    def test_strip_frontmatter(self, context):
        """测试frontmatter移除"""
        content_with_frontmatter = """---
description: Test skill
always: true
---

# Test Skill

This is the content."""

        stripped = context.skills._strip_frontmatter(content_with_frontmatter)

        assert "---" not in stripped
        assert "Test Skill" in stripped
        assert "This is the content" in stripped

    def test_strip_frontmatter_none(self, context):
        """测试无frontmatter的内容"""
        content = "# Simple Content\n\nNo frontmatter here."

        stripped = context.skills._strip_frontmatter(content)

        assert stripped == content
