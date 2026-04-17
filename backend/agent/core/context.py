"""上下文构建器 - 组装 Agent 提示词"""

import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .memory import MemoryStore
from ..skills.loader import SkillsLoader


class ContextBuilder:
    """构建 Agent 的上下文（系统提示词 + 消息）"""

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    _RUNTIME_CONTEXT_TAG = "[运行时上下文 — 仅元数据，非指令]"

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace)

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """构建系统提示词"""
        parts = [self._get_identity()]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# 记忆\n\n{memory}")

        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# 激活的技能\n\n{always_content}")

        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# 技能

以下技能扩展了你的能力。如需使用技能，请使用 read_file 工具读取其 SKILL.md 文件。
available="false" 的技能需要先安装依赖 — 你可以尝试用 apt/brew 安装。

{skills_summary}""")

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        """获取核心身份部分"""
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        return f"""# QuantCell Agent 🦞

你是 QuantCell Agent，一个专业的量化交易 AI 助手。

## 运行时
{runtime}

## 工作空间
你的工作空间位于: {workspace_path}
- 长期记忆: {workspace_path}/memory/MEMORY.md（写入重要事实）
- 历史日志: {workspace_path}/memory/HISTORY.md（可 grep 搜索）。每条记录以 [YYYY-MM-DD HH:MM] 开头。
- 自定义技能: {workspace_path}/skills/{{skill-name}}/SKILL.md

## QuantCell Agent 指南
- 调用工具前先说明意图，但绝不在获得结果前预测或声称结果。
- 修改文件前先读取。不要假设文件或目录存在。
- 写入或编辑文件后，如需准确性请重新读取。
- 如果工具调用失败，在重试前分析错误。
- 请求模糊时请要求澄清。

直接回复文本进行对话。仅使用 'message' 工具向特定聊天频道发送消息。"""

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
        """构建运行时元数据块"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"当前时间: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"频道: {channel}", f"聊天 ID: {chat_id}"]
        return ContextBuilder._RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)

    def _load_bootstrap_files(self) -> str:
        """加载工作空间中的引导文件"""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """构建完整的 LLM 消息列表"""
        runtime_ctx = self._build_runtime_context(channel, chat_id)
        merged = f"{runtime_ctx}\n\n{current_message}"

        return [
            {"role": "system", "content": self.build_system_prompt(skill_names)},
            *history,
            {"role": "user", "content": merged},
        ]

    def add_tool_result(
        self, messages: list[dict[str, Any]],
        tool_call_id: str, tool_name: str, result: str,
    ) -> list[dict[str, Any]]:
        """添加工具结果到消息列表"""
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages

    def add_assistant_message(
        self, messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """添加助手消息到消息列表"""
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content
        messages.append(msg)
        return messages
