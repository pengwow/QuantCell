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
        max_history: int = 200,
        reasoning_effort: str | None = None,
    ):
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.max_history = max_history
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
        import time
        loop_start_time = time.time()
        logger.info(f"[AgentLoop] 开始运行 Agent 循环, 初始消息数: {len(initial_messages)}")
        
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1
            iter_start_time = time.time()
            logger.info(f"[AgentLoop] === 第 {iteration}/{self.max_iterations} 次迭代开始 ===")

            try:
                llm_start = time.time()
                logger.info(f"[AgentLoop] 调用 LLM API... (model={self.model}, messages={len(messages)})")
                
                response = await self.provider.chat(
                    messages=messages,
                    tools=self.tools.get_definitions(),
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                )
                
                llm_elapsed = time.time() - llm_start
                logger.info(f"[AgentLoop] LLM API 响应完成, 耗时: {llm_elapsed:.2f}s, finish_reason={response.finish_reason}, has_tool_calls={response.has_tool_calls}")

            except Exception as e:
                logger.error(f"[AgentLoop] LLM API 调用失败: {type(e).__name__}: {e}")
                raise

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
                    logger.info(f"[AgentLoop] 执行工具: {tool_call['name']}({args_str[:200]})")
                    
                    tool_start = time.time()
                    result = await self.tools.execute(tool_call["name"], tool_call.get("arguments", {}))
                    tool_elapsed = time.time() - tool_start
                    
                    logger.info(f"[AgentLoop] 工具执行完成: {tool_call['name']}, 耗时: {tool_elapsed:.2f}s, 结果长度: {len(str(result))}")
                    
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
                logger.info(f"[AgentLoop] 获得 LLM 文本响应, 长度: {len(clean) if clean else 0}")
                break

            iter_elapsed = time.time() - iter_start_time
            logger.info(f"[AgentLoop] === 第 {iteration} 次迭代结束, 耗时: {iter_elapsed:.2f}s ===")

        total_elapsed = time.time() - loop_start_time
        logger.info(f"[AgentLoop] Agent 循环结束, 总耗时: {total_elapsed:.2f}s, 总迭代次数: {iteration}")

        if final_content is None and iteration >= self.max_iterations:
            logger.warning(f"达到最大迭代次数 ({self.max_iterations})")
            final_content = (
                f"我达到了工具调用的最大迭代次数 ({self.max_iterations}) "
                "仍未完成任务。你可以尝试将任务分解为更小的步骤。"
            )

        return final_content, tools_used, messages

    async def _run_agent_loop_stream(
        self,
        initial_messages: list[dict],
        on_stream: Callable[..., Awaitable[None]] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """
        流式运行 Agent 循环 - 实时推送事件

        Args:
            initial_messages: 初始消息列表
            on_stream: 流式事件回调函数 (event: StreamEvent) -> None

        Returns:
            (最终内容, 使用的工具列表, 所有消息)
        """
        from ..providers.base import StreamEvent

        import time
        loop_start_time = time.time()
        logger.info(f"[AgentLoop] 开始流式 Agent 循环, 初始消息数: {len(initial_messages)}")

        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1
            iter_start_time = time.time()
            logger.info(f"[AgentLoop] === 第 {iteration}/{self.max_iterations} 次流式迭代开始 ===")

            # 发送迭代开始事件
            if on_stream:
                await on_stream(StreamEvent(
                    event_type="iteration_start",
                    data={"iteration": iteration, "max_iterations": self.max_iterations},
                ))

            try:
                # 调用流式 LLM API
                response_content = ""
                response_tool_calls = []
                finish_reason = None
                reasoning_parts = []

                llm_start = time.time()
                logger.info(f"[AgentLoop] 调用流式 LLM API... (model={self.model}, messages={len(messages)})")

                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    tools=self.tools.get_definitions(),
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                ):
                    # 文本内容 - 立即推送给客户端
                    if chunk.delta:
                        response_content += chunk.delta

                        if on_stream:
                            await on_stream(StreamEvent(
                                event_type="content",
                                data={
                                    "content": chunk.delta,
                                    "full_content": response_content,
                                },
                            ))

                    # 推理过程（DeepSeek-R1 等）
                    if chunk.reasoning_content:
                        reasoning_parts.append(chunk.reasoning_content)

                        if on_stream:
                            await on_stream(StreamEvent(
                                event_type="reasoning",
                                data={"content": chunk.reasoning_content},
                            ))

                    # 工具调用完成
                    if chunk.is_tool_call and chunk.tool_calls:
                        response_tool_calls = chunk.tool_calls
                        finish_reason = chunk.finish_reason

                llm_elapsed = time.time() - llm_start
                logger.info(f"[AgentLoop] 流式 LLM 响应完成, 耗时: {llm_elapsed:.2f}s, finish_reason={finish_reason}")

            except Exception as e:
                logger.error(f"[AgentLoop] 流式 LLM API 调用失败: {type(e).__name__}: {e}")
                if on_stream:
                    await on_stream(StreamEvent(event_type="error", data={"error": str(e)}))
                raise

            # 处理响应
            if response_tool_calls:
                # 有工具调用 - 推送工具调用事件
                if on_stream:
                    await on_stream(StreamEvent(
                        event_type="tool_calls",
                        data={"tools": response_tool_calls},
                    ))

                # 构建工具调用消息格式
                tool_call_dicts = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False) if isinstance(tc["arguments"], dict) else tc["arguments"]
                        }
                    }
                    for tc in response_tool_calls
                ]

                messages = self.context.add_assistant_message(
                    messages, response_content, tool_call_dicts,
                    reasoning_content="\n".join(reasoning_parts) if reasoning_parts else None,
                )

                # 执行每个工具调用
                for tool_call in response_tool_calls:
                    tools_used.append(tool_call["name"])
                    args_str = json.dumps(tool_call.get("arguments", {}), ensure_ascii=False)
                    logger.info(f"[AgentLoop] 执行工具: {tool_call['name']}({args_str[:200]})")

                    # 推送工具开始事件
                    if on_stream:
                        await on_stream(StreamEvent(
                            event_type="tool_start",
                            data={
                                "name": tool_call["name"],
                                "args": tool_call.get("arguments", {}),
                            },
                        ))

                    # 执行工具
                    tool_start = time.time()
                    result = await self.tools.execute(tool_call["name"], tool_call.get("arguments", {}))
                    tool_elapsed = time.time() - tool_start

                    logger.info(f"[AgentLoop] 工具执行完成: {tool_call['name']}, 耗时: {tool_elapsed:.2f}s")

                    # 添加工具结果到消息
                    messages = self.context.add_tool_result(
                        messages, tool_call["id"], tool_call["name"], result
                    )

                    # 推送工具结果事件
                    if on_stream:
                        result_preview = str(result)[:500]
                        await on_stream(StreamEvent(
                            event_type="tool_result",
                            data={
                                "name": tool_call["name"],
                                "result": result_preview,
                                "elapsed": tool_elapsed,
                            },
                        ))
            else:
                # 无工具调用 - 最终文本响应
                clean = self._strip_think(response_content)

                if finish_reason == "error":
                    logger.error(f"LLM 返回错误: {(clean or '')[:200]}")
                    final_content = clean or "抱歉，调用 AI 模型时遇到错误。"
                else:
                    messages = self.context.add_assistant_message(
                        messages, clean,
                        reasoning_content="\n".join(reasoning_parts) if reasoning_parts else None,
                    )
                    final_content = clean
                    logger.info(f"[AgentLoop] 获得 LLM 文本响应, 长度: {len(clean) if clean else 0}")

                # 推送完成事件
                if on_stream:
                    await on_stream(StreamEvent(
                        event_type="complete",
                        data={
                            "content": final_content,
                            "iteration": iteration,
                            "tools_used": tools_used,
                        },
                    ))

                break

            iter_elapsed = time.time() - iter_start_time
            logger.info(f"[AgentLoop] === 第 {iteration} 次流式迭代结束, 耗时: {iter_elapsed:.2f}s ===")

        total_elapsed = time.time() - loop_start_time
        logger.info(f"[AgentLoop] 流式 Agent 循环结束, 总耗时: {total_elapsed:.2f}s, 总迭代次数: {iteration}")

        if final_content is None and iteration >= self.max_iterations:
            logger.warning(f"达到最大迭代次数 ({self.max_iterations})")
            final_content = (
                f"我达到了工具调用的最大迭代次数 ({self.max_iterations}) "
                "仍未完成任务。你可以尝试将任务分解为更小的步骤。"
            )

            if on_stream:
                await on_stream(StreamEvent(
                    event_type="complete",
                    data={"content": final_content, "iteration": iteration, "max_reached": True},
                ))

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
        import time
        start_time = time.time()
        logger.info(f"[AgentLoop] ====== 开始处理消息: {content[:100]}... (session={session_key}) ======")
        
        session = self.sessions.get_or_create(session_key)
        logger.debug(f"[AgentLoop] 会话信息: messages_count={len(session.messages)}, last_consolidated={session.last_consolidated}")

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
        logger.info(f"[AgentLoop] 消息构建完成, history={len(history)}, total_messages={len(initial_messages)}")

        # 运行 Agent 循环
        try:
            final_content, _, all_msgs = await self._run_agent_loop(
                initial_messages, on_progress=on_progress
            )
        except Exception as e:
            logger.error(f"[AgentLoop] Agent 循环执行失败: {type(e).__name__}: {e}")
            raise

        if final_content is None:
            final_content = "我已完成处理，但没有响应内容。"

        # 保存会话
        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)
        
        elapsed = time.time() - start_time
        logger.info(f"[AgentLoop] ====== 消息处理完成, 总耗时: {elapsed:.2f}s ======")

        return final_content

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """保存新一轮消息到会话（带去重机制）"""
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

                # 去重：检查是否与上一条 user 消息完全相同
                if len(session.messages) > 0:
                    last_msg = session.messages[-1]
                    content_str = str(content or "").strip()
                    last_content = str(last_msg.get("content", "")).strip()
                    if (last_msg.get("role") == "user" and
                        content_str == last_content):
                        logger.debug(f"跳过重复消息: {content_str[:50]}...")
                        continue

            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)

        # 限制最大历史条数，防止无限增长
        if len(session.messages) > self.max_history:
            removed = len(session.messages) - self.max_history
            session.messages = session.messages[-self.max_history:]
            logger.info(f"历史消息超出限制({self.max_history})，移除了 {removed} 条旧消息")

        session.updated_at = datetime.now()

    async def process_message_stream(
        self,
        content: str,
        session_key: str = "default",
        on_stream: Callable[..., Awaitable[None]] | None = None,
    ):
        """
        流式处理消息 - 实时返回事件

        用法示例:
            async for event in agent.process_message_stream("你好"):
                print(event.event_type, event.data)

            # 或者使用回调
            await agent.process_message_stream("你好", on_stream=my_callback)

        Args:
            content: 用户消息内容
            session_key: 会话标识
            on_stream: 可选的事件回调函数 (event: StreamEvent) -> None

        Yields:
            StreamEvent: 流式事件（当不使用 on_stream 回调时）
        """
        from ..providers.base import StreamEvent

        import time
        start_time = time.time()
        logger.info(f"[AgentLoop] ====== 开始流式处理消息: {content[:100]}... (session={session_key}) ======")

        session = self.sessions.get_or_create(session_key)
        logger.debug(f"[AgentLoop] 会话信息: messages_count={len(session.messages)}, last_consolidated={session.last_consolidated}")

        # 检查记忆整合（与 process_message 保持一致）
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
        logger.info(f"[AgentLoop] 消息构建完成, history={len(history)}, total_messages={len(initial_messages)}")

        # 发送开始事件
        if on_stream:
            await on_stream(StreamEvent(
                event_type="start",
                data={
                    "session": session_key,
                    "message": content,
                    "history_count": len(history),
                },
            ))

        try:
            # 运行流式 Agent 循环
            final_content, tools_used, all_msgs = await self._run_agent_loop_stream(
                initial_messages, on_stream=on_stream
            )

            # 保存会话
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)

            elapsed = time.time() - start_time
            logger.info(f"[AgentLoop] ====== 流式消息处理完成, 总耗时: {elapsed:.2f}s ======")

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[AgentLoop] 流式 Agent 循环执行失败: {type(e).__name__}: {e} (耗时: {elapsed:.2f}s)")

            if on_stream:
                await on_stream(StreamEvent(
                    event_type="error",
                    data={"error": str(e), "elapsed": elapsed},
                ))

            raise

        # 如果没有回调，返回空（实际使用时应该总是传入 on_stream 或使用 async for）
        return

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """直接处理消息（用于 CLI 或定时任务）"""
        return await self.process_message(content, session_key, on_progress)
