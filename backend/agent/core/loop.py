"""Agent 主循环 - 核心处理引擎"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from utils.logger import get_logger, LogType

from .context import ContextBuilder
from .memory import MemoryStore
from ..session.manager import Session, SessionManager
from ..tools.registry import ToolRegistry

if TYPE_CHECKING:
    from ..providers.base import LLMProvider

logger = get_logger(__name__, LogType.APPLICATION)


class AgentLoop:
    """
    Agent 主循环 - 核心处理引擎

    工作流程:
    1. 接收消息
    2. 构建上下文（历史、记忆、技能）
    3. 调用 LLM
    4. 执行工具调用
    5. 返回响应
    """

    _TOOL_RESULT_MAX_CHARS = 500

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
    ):
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.reasoning_effort = reasoning_effort

        self.context = ContextBuilder(workspace)
        self.sessions = SessionManager(workspace)
        self.tools = ToolRegistry()

        self._running = False
        self._consolidating: set[str] = set()
        self._consolidation_locks: dict[str, asyncio.Lock] = {}

    def register_tool(self, tool) -> None:
        """注册工具"""
        self.tools.register(tool)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """移除 <think>…</think> 块"""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """格式化工具调用为简洁提示"""
        def _fmt(tc):
            args = tc.get("arguments", {}) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.get("name", "")
            return f'{tc["name"]}("{val[:40]}…")' if len(val) > 40 else f'{tc["name"]}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """
        运行 Agent 迭代循环
        
        Returns:
            (最终内容, 使用的工具列表, 所有消息)
        """
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
            )

            if response.has_tool_calls:
                if on_progress:
                    thoughts = [
                        self._strip_think(response.content),
                        response.reasoning_content,
                    ]
                    combined_thoughts = "\n\n".join(filter(None, thoughts))
                    if combined_thoughts:
                        await on_progress(combined_thoughts)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False) if isinstance(tc["arguments"], dict) else tc["arguments"]
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call["name"])
                    args_str = json.dumps(tool_call.get("arguments", {}), ensure_ascii=False)
                    logger.info(f"工具调用: {tool_call['name']}({args_str[:200]})")
                    result = await self.tools.execute(tool_call["name"], tool_call.get("arguments", {}))
                    messages = self.context.add_tool_result(
                        messages, tool_call["id"], tool_call["name"], result
                    )
            else:
                clean = self._strip_think(response.content)
                if response.finish_reason == "error":
                    logger.error(f"LLM 返回错误: {(clean or '')[:200]}")
                    final_content = clean or "抱歉，调用 AI 模型时遇到错误。"
                    break
                messages = self.context.add_assistant_message(
                    messages, clean, reasoning_content=response.reasoning_content,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning(f"达到最大迭代次数 ({self.max_iterations})")
            final_content = (
                f"我达到了工具调用的最大迭代次数 ({self.max_iterations}) "
                "仍未完成任务。你可以尝试将任务分解为更小的步骤。"
            )

        return final_content, tools_used, messages

    async def process_message(
        self,
        content: str,
        session_key: str = "default",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """
        处理单条消息
        
        Args:
            content: 用户消息内容
            session_key: 会话标识
            on_progress: 进度回调函数
            
        Returns:
            Agent 响应内容
        """
        session = self.sessions.get_or_create(session_key)

        # 检查记忆整合
        unconsolidated = len(session.messages) - session.last_consolidated
        if unconsolidated >= self.memory_window and session_key not in self._consolidating:
            self._consolidating.add(session_key)
            if session_key not in self._consolidation_locks:
                self._consolidation_locks[session_key] = asyncio.Lock()

            async def _consolidate_and_unlock():
                try:
                    async with self._consolidation_locks[session_key]:
                        await MemoryStore(self.workspace).consolidate(
                            session, self.provider, self.model,
                            memory_window=self.memory_window,
                        )
                finally:
                    self._consolidating.discard(session_key)

            asyncio.create_task(_consolidate_and_unlock())

        # 构建初始消息
        history = session.get_history(max_messages=self.memory_window)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=content,
        )

        # 运行 Agent 循环
        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages, on_progress=on_progress
        )

        if final_content is None:
            final_content = "我已完成处理，但没有响应内容。"

        # 保存会话
        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        return final_content

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """保存新一轮消息到会话"""
        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # 跳过空助手消息
            if role == "tool" and isinstance(content, str) and len(content) > self._TOOL_RESULT_MAX_CHARS:
                entry["content"] = content[:self._TOOL_RESULT_MAX_CHARS] + "\n... (已截断)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                    # 移除运行时上下文前缀
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """直接处理消息（用于 CLI 或定时任务）"""
        return await self.process_message(content, session_key, on_progress)
