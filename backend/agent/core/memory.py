"""记忆管理系统：MemoryStore + Consolidator + AutoCompact + Dream

参考 Nanobot 实现：
- MemoryStore: 纯文件 I/O 层，管理 MEMORY.md, history.jsonl
- Consolidator: 按 Token 数量自动整合旧消息到历史记录
- AutoCompact: 自动清理过期会话
- Dream: 定期反思和整理长期记忆（简化版）
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from utils.logger import get_logger, LogType

if TYPE_CHECKING:
    from ..providers.base import LLMProvider
    from ..session.manager import Session, SessionManager


logger = get_logger(__name__, LogType.APPLICATION)


# ---------------------------------------------------------------------------
# MemoryStore — 纯文件 I/O 层
# ---------------------------------------------------------------------------

class MemoryStore:
    """纯文件 I/O 用于记忆文件：MEMORY.md, history.jsonl"""

    _DEFAULT_MAX_HISTORY = 1000

    def __init__(self, workspace: Path, max_history_entries: int = _DEFAULT_MAX_HISTORY):
        self.workspace = workspace
        self.max_history_entries = max_history_entries
        
        # 确保目录存在
        self.memory_dir = workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件路径
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "history.jsonl"
        self._cursor_file = self.memory_dir / ".cursor"
        self._dream_cursor_file = self.memory_dir / ".dream_cursor"

    # -- MEMORY.md (长期记忆) -----------------------------------------------

    def read_memory(self) -> str:
        """读取长期记忆文件"""
        try:
            return self.memory_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def write_memory(self, content: str) -> None:
        """写入长期记忆文件"""
        self.memory_file.write_text(content, encoding="utf-8")

    def get_memory_context(self) -> str:
        """获取记忆上下文（用于注入到 LLM prompt）"""
        long_term = self.read_memory()
        return f"## 长期记忆\n{long_term}" if long_term else ""

    # -- history.jsonl — 追加式 JSONL 格式历史记录 --------------------------

    def append_history(self, entry: str) -> int:
        """追加条目到 history.jsonl 并返回自增的 cursor"""
        cursor = self._next_cursor()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        record = {
            "cursor": cursor,
            "timestamp": ts,
            "content": entry.rstrip() if entry else ""
        }
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._cursor_file.write_text(str(cursor), encoding="utf-8")
        return cursor

    def read_unprocessed_history(self, since_cursor: int) -> list[dict[str, Any]]:
        """返回 cursor > since_cursor 的历史条目"""
        return [e for e in self._read_entries() if e.get("cursor", 0) > since_cursor]

    def compact_history(self) -> None:
        """如果超过最大条数则删除最旧的条目"""
        if self.max_history_entries <= 0:
            return
        entries = self._read_entries()
        if len(entries) <= self.max_history_entries:
            return
        kept = entries[-self.max_history_entries:]
        self._write_entries(kept)
        logger.info(f"History compacted: {len(entries)} -> {len(kept)} entries")

    # -- JSONL 辅助方法 ----------------------------------------------------

    def _next_cursor(self) -> int:
        """读取当前 cursor 计数器并返回下一个值"""
        if self._cursor_file.exists():
            try:
                return int(self._cursor_file.read_text(encoding="utf-8").strip()) + 1
            except (ValueError, OSError):
                pass
        last = self._read_last_entry()
        if last and last.get("cursor"):
            return last["cursor"] + 1
        return 1

    def _read_entries(self) -> list[dict[str, Any]]:
        """读取 history.jsonl 的所有条目"""
        entries: list[dict[str, Any]] = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except FileNotFoundError:
            pass
        return entries

    def _read_last_entry(self) -> dict[str, Any] | None:
        """高效读取最后一条记录"""
        try:
            with open(self.history_file, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return None
                read_size = min(size, 4096)
                f.seek(size - read_size)
                data = f.read().decode("utf-8")
                lines = [l for l in data.split("\n") if l.strip()]
                if not lines:
                    return None
                return json.loads(lines[-1])
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        """覆盖 history.jsonl"""
        with open(self.history_file, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # -- dream cursor --------------------------------------------------------

    def get_last_dream_cursor(self) -> int:
        """获取最后一次 Dream 处理的 cursor"""
        if self._dream_cursor_file.exists():
            try:
                return int(self._dream_cursor_file.read_text(encoding="utf-8").strip())
            except (ValueError, OSError):
                pass
        return 0

    def set_last_dream_cursor(self, cursor: int) -> None:
        """设置最后一次 Dream 处理的 cursor"""
        self._dream_cursor_file.write_text(str(cursor), encoding="utf-8")

    # -- 消息格式化工具 ----------------------------------------------------

    @staticmethod
    def _format_messages(messages: list[dict]) -> str:
        """格式化消息列表为文本"""
        lines = []
        for message in messages:
            if not message.get("content"):
                continue
            tools = f" [tools: {', '.join(message['tools_used'])}]" if message.get("tools_used") else ""
            lines.append(
                f"[{message.get('timestamp', '?')[:16]}] {message['role'].upper()}{tools}: {message['content']}"
            )
        return "\n".join(lines)

    def raw_archive(self, messages: list[dict]) -> None:
        """回退方案：将原始消息直接转储到 history.jsonl（无 LLM 摘要）"""
        self.append_history(
            f"[RAW] {len(messages)} 条消息\n"
            f"{self._format_messages(messages)}"
        )
        logger.warning(f"Memory consolidation degraded: raw-archived {messages} messages")


# ---------------------------------------------------------------------------
# Consolidator — 基于 Token 预算触发的轻量级整合
# ---------------------------------------------------------------------------


class Consolidator:
    """轻量级整合器：将淘汰的消息摘要化到 history.jsonl"""

    _MAX_CONSOLIDATION_ROUNDS = 5
    _MAX_CHUNK_MESSAGES = 60  # 每轮整合的最大消息数
    _SAFETY_BUFFER = 1024  # Tokenizer 估计偏差的安全缓冲区

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        sessions: SessionManager,
        context_window_tokens: int,
        build_messages: Callable[..., list[dict[str, Any]]],
        get_tool_definitions: Callable[[], list[dict[str, Any]]],
        max_completion_tokens: int = 4096,
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.sessions = sessions
        self.context_window_tokens = context_window_tokens
        self.max_completion_tokens = max_completion_tokens
        self._build_messages = build_messages
        self._get_tool_definitions = get_tool_definitions
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, session_key: str) -> asyncio.Lock:
        """返回指定会话的共享整合锁"""
        if session_key not in self._locks:
            self._locks[session_key] = asyncio.Lock()
        return self._locks[session_key]

    def pick_consolidation_boundary(
        self,
        session: Session,
        tokens_to_remove: int,
    ) -> tuple[int, int] | None:
        """选择一个用户轮次边界以移除足够的旧 prompt tokens"""
        start = session.last_consolidated
        if start >= len(session.messages) or tokens_to_remove <= 0:
            return None

        removed_tokens = 0
        last_boundary: tuple[int, int] | None = None
        for idx in range(start, len(session.messages)):
            message = session.messages[idx]
            if idx > start and message.get("role") == "user":
                last_boundary = (idx, removed_tokens)
                if removed_tokens >= tokens_to_remove:
                    return last_boundary
            removed_tokens += self._estimate_message_tokens(message)

        return last_boundary

    def _cap_consolidation_boundary(
        self,
        session: Session,
        end_idx: int,
    ) -> int | None:
        """限制块大小而不破坏用户轮次边界"""
        start = session.last_consolidated
        if end_idx - start <= self._MAX_CHUNK_MESSAGES:
            return end_idx

        capped_end = start + self._MAX_CHUNK_MESSAGES
        for idx in range(capped_end, start, -1):
            if session.messages[idx].get("role") == "user":
                return idx
        return None

    @staticmethod
    def _estimate_message_tokens(message: dict) -> int:
        """估算单条消息的 token 数"""
        content = str(message.get("content", ""))
        # 粗略估算：约 4 字符/token（中文）或 4 词/token（英文）
        if any('\u4e00' <= c <= '\u9fff' for c in content):
            return max(10, len(content))  # 中文
        else:
            return max(10, len(content.split()))  # 英文

    async def archive(self, messages: list[dict]) -> str | None:
        """通过 LLM 摘要消息并追加到 history.jsonl

        成功时返回摘要文本，无内容可归档时返回 None
        """
        if not messages:
            return None
        try:
            formatted = MemoryStore._format_messages(messages)
            
            system_prompt = """从这段对话中提取关键事实。只输出匹配以下类别的内容，跳过其他所有内容：

- 用户事实：个人信息、偏好、明确表达的观点、习惯
- 决策：做出的选择、得出的结论
- 解决方案：通过试错发现的有效方法（特别是非显而易见的成功方法）
- 事件：计划、截止日期、值得注意的发生事项
- 偏好：沟通风格、工具偏好

优先级：用户的纠正和偏好 > 解决方案 > 决策 > 事件 > 环境事实。最有价值的记忆是防止用户重复自己说过的话。

跳过：可从源代码推导的模式、git 历史、或已存在于现有记忆中的任何内容。

以简洁的项目符号输出，每行一个事实。不要前言，不要评论。
如果没有值得注意的事情，输出：(nothing)"""

            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": formatted},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=1024,
            )
            
            summary = response.content or "[no summary]"
            self.store.append_history(summary)
            logger.info(f"Consolidation archived {len(messages)} messages -> {len(summary)} chars")
            return summary
            
        except Exception as e:
            logger.warning(f"Consolidation LLM call failed, raw-dumping to history: {e}")
            self.store.raw_archive(messages)
            return None

    async def maybe_consolidate_by_tokens(self, session: Session) -> None:
        """循环：归档旧消息直到 prompt 符合安全预算

        预算为 completion tokens 和安全缓冲区预留空间，
        这样 LLM 请求永远不会超出上下文窗口。
        """
        if not session.messages or self.context_window_tokens <= 0:
            return

        lock = self.get_lock(session.key)
        async with lock:
            budget = self.context_window_tokens - self.max_completion_tokens - self._SAFETY_BUFFER
            target = budget // 2
            
            estimated = self._estimate_session_prompt_tokens(session)
            
            if estimated <= 0:
                return
            if estimated < budget:
                unconsolidated_count = len(session.messages) - session.last_consolidated
                logger.debug(
                    f"Token consolidation idle {session.key}: "
                    f"{estimated}/{self.context_window_tokens}, msgs={unconsolidated_count}"
                )
                return

            for round_num in range(self._MAX_CONSOLIDATION_ROUNDS):
                if estimated <= target:
                    return

                boundary = self.pick_consolidation_boundary(session, max(1, estimated - target))
                if boundary is None:
                    logger.debug(f"No safe boundary for {session.key} (round {round_num})")
                    return

                end_idx = boundary[0]
                end_idx = self._cap_consolidation_boundary(session, end_idx)
                if end_idx is None:
                    logger.debug(f"No capped boundary for {session.key} (round {round_num})")
                    return

                chunk = session.messages[session.last_consolidated:end_idx]
                if not chunk:
                    return

                logger.info(
                    f"Token consolidation round {round_num} for {session.key}: "
                    f"{estimated}/{self.context_window_tokens}, chunk={len(chunk)} msgs"
                )
                
                if not await self.archive(chunk):
                    return
                    
                session.last_consolidated = end_idx
                self.sessions.save(session)

                estimated = self._estimate_session_prompt_tokens(session)
                if estimated <= 0:
                    return

    def _estimate_session_prompt_tokens(self, session: Session) -> int:
        """估算当前会话的 prompt 大小"""
        history = session.get_history(max_messages=0)
        total_tokens = 0
        
        # 估算基础消息开销
        probe_messages = self._build_messages(history=history, current_message="[token-probe]")
        for msg in probe_messages:
            total_tokens += self._estimate_message_tokens(msg)
        
        # 加上工具定义的开销
        tool_defs = self._get_tool_definitions()
        if tool_defs:
            total_tokens += len(json.dumps(tool_defs, ensure_ascii=False)) // 4
        
        return total_tokens


# ---------------------------------------------------------------------------
# AutoCompact — 自动清理过期会话
# ---------------------------------------------------------------------------


class AutoCompact:
    """主动压缩空闲会话以减少 Token 成本和延迟"""

    _RECENT_SUFFIX_MESSAGES = 8  # 保留最近的消息数

    def __init__(
        self,
        sessions: SessionManager,
        consolidator: Consolidator,
        session_ttl_minutes: int = 60,  # 默认 1 小时过期
    ):
        self.sessions = sessions
        self.consolidator = consolidator
        self._ttl = session_ttl_minutes
        self._archiving: set[str] = set()
        self._summaries: dict[str, tuple[str, datetime]] = {}

    def _is_expired(self, ts: datetime | str | None, now: datetime | None = None) -> bool:
        """检查会话是否已过期"""
        if self._ttl <= 0 or not ts:
            return False
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return ((now or datetime.now()) - ts).total_seconds() >= self._ttl * 60

    @staticmethod
    def _format_summary(text: str, last_active: datetime) -> str:
        """格式化会话摘要"""
        idle_min = int((datetime.now() - last_active).total_seconds() / 60)
        return f"Inactive for {idle_min} minutes.\nPrevious conversation summary: {text}"

    def check_expired(
        self,
        schedule_background: Callable[[Any], None],
        active_session_keys: set[str] | None = None,
    ) -> None:
        """调度过期会话的归档任务，跳过正在执行 agent 任务的会话"""
        now = datetime.now()
        active_keys = active_session_keys or set()
        
        for info in self.sessions.list_sessions():
            key = info.get("key", "")
            if not key or key in self._archiving:
                continue
            if key in active_keys:
                continue
            if self._is_expired(info.get("updated_at"), now):
                self._archiving.add(key)
                schedule_background(self._archive(key))

    async def _archive(self, key: str) -> None:
        """归档指定的过期会话"""
        try:
            session = self.sessions.get_or_create(key)
            
            # 分割为可归档的前缀和保留的后缀
            tail = list(session.messages[session.last_consolidated:])
            if not tail:
                session.updated_at = datetime.now()
                self.sessions.save(session)
                return

            # 保留最近的消息
            kept_tail = tail[-self._RECENT_SUFFIX_MESSAGES:] if len(tail) > self._RECENT_SUFFIX_MESSAGES else tail
            archive_msgs = tail[:len(tail) - len(kept_tail)]

            last_active = session.updated_at
            summary = ""
            
            if archive_msgs:
                summary = await self.consolidator.archive(archive_msgs) or ""
            
            if summary and summary != "(nothing)":
                self._summaries[key] = (summary, last_active)

            # 只保留最近的消息
            session.messages = session.messages[:session.last_consolidated] + kept_tail
            session.last_consolidated = 0
            session.updated_at = datetime.now()
            self.sessions.save(session)

            if archive_msgs:
                logger.info(
                    f"Auto-compact: archived {key} "
                    f"(archived={len(archive_msgs)}, kept={len(kept_tail)}, has_summary={bool(summary)})"
                )
                
        except Exception as e:
            logger.error(f"Auto-compact failed for {key}: {e}")
        finally:
            self._archiving.discard(key)

    def prepare_session(self, session: Session, key: str) -> tuple[Session, str | None]:
        """准备会话：如果已过期则重新加载，注入之前的摘要"""
        if key in self._archiving or self._is_expired(session.updated_at):
            logger.info(f"Auto-compact: reloading session {key}")
            session = self.sessions.get_or_create(key)

        # 从内存字典获取摘要（进程未重启的情况）
        entry = self._summaries.pop(key, None)
        if entry:
            return session, self._format_summary(entry[0], entry[1])

        return session, None


# ---------------------------------------------------------------------------
# Dream — 定期反思和整理长期记忆（简化版）
# ---------------------------------------------------------------------------

_STALE_THRESHOLD_DAYS = 14  # 过期阈值（天）


class Dream:
    """两阶段记忆处理器：分析 history.jsonl，然后编辑 MEMORY.md

    Phase 1: 分析历史记录，提取新事实和发现重复内容
    Phase 2: 使用 LLM 编辑 MEMORY.md（简化版，不使用工具）
    """

    def __init__(
        self,
        store: MemoryStore,
        provider: LLMProvider,
        model: str,
        max_batch_size: int = 20,
    ):
        self.store = store
        self.provider = provider
        self.model = model
        self.max_batch_size = max_batch_size

    async def run(self) -> bool:
        """处理未处理的的历史条目。如果有工作则返回 True"""
        last_cursor = self.store.get_last_dream_cursor()
        entries = self.store.read_unprocessed_history(since_cursor=last_cursor)
        
        if not entries:
            return False

        batch = entries[: self.max_batch_size]
        logger.info(
            f"Dream: processing {len(entries)} entries "
            f"(cursor {last_cursor}->{batch[-1]['cursor']}), batch={len(batch)}"
        )

        # 构建历史文本
        history_text = "\n".join(
            f"[{e['timestamp']}] {e['content']}" for e in batch
        )

        # 当前记忆内容
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_memory = self.store.read_memory() or "(empty)"

        file_context = (
            f"## Current Date\n{current_date}\n\n"
            f"## Current MEMORY.md ({len(current_memory)} chars)\n{current_memory}"
        )

        # Phase 1: 分析
        phase1_prompt = f"""你有两个同等重要的任务：
1. 从对话历史中提取新的事实
2. 去重现有的记忆文件 — 找出冗余、重叠或过时的内容

每行输出一个发现：
[MEMORY] 原子级事实（不在已有记忆中）
[MEMORY-REMOVE] 删除原因

规则：
- 原子级事实："有一只叫 Luna 的猫"，而不是"讨论了宠物护理"
- 纠正：[MEMORY] 地点是东京，不是大阪
- 捕获用户确认过的有效方法

去重检查这些模式：
- 同一事实在多处出现
- MEMORY.md 中包含 USER.md 或 SOUL.md 已有的信息（不应重复）
- 可以压缩而不丢失信息的冗长条目
- 客观过时的内容：已过去的事件、已解决的跟踪、被替代的方法

不要添加：当前天气、临时状态、临时错误、对话填充。

如果无需更新，输出 [SKIP]。"""

        full_prompt = f"## Conversation History\n{history_text}\n\n{file_context}"

        try:
            phase1_response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": phase1_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=2048,
            )
            
            analysis = phase1_response.content or ""
            logger.debug(f"Dream Phase 1 analysis ({len(analysis)} chars): {analysis[:500]}")
            
        except Exception as e:
            logger.error(f"Dream Phase 1 failed: {e}")
            return False

        # Phase 2: 更新 MEMORY.md（简化版）
        if "[SKIP]" in analysis or not analysis.strip():
            logger.info("Dream: nothing to update")
        else:
            phase2_prompt = f"""基于以下分析更新 MEMORY.md。

## Analysis Result
{analysis}

## Current MEMORY.md
{current_memory}

规则：
- 直接编辑 — 提供了文件内容，不需要先读取
- 批量修改同一文件的多个变更
- 删除：标题+所有项目符号作为 old_text，new_text 为空
- 精确编辑 — 不要重写整个文件
- 如果没有要更新的，停止

输出格式：
只输出更新后的完整 MEMORY.md 内容，不要添加任何解释或评论。"""

            try:
                phase2_response = await self.provider.chat(
                    messages=[
                        {"role": "system", "content": "你是记忆管理助手，负责更新 MEMORY.md 文件。"},
                        {"role": "user", "content": phase2_prompt},
                    ],
                    model=self.model,
                    temperature=0.1,
                    max_tokens=4096,
                )
                
                new_memory = phase2_response.content or ""
                if new_memory and new_memory != current_memory:
                    self.store.write_memory(new_memory)
                    logger.info(f"Dream: updated MEMORY.md ({len(new_memory)} chars)")
                    
            except Exception as e:
                logger.error(f"Dream Phase 2 failed: {e}")

        # 推进 cursor
        new_cursor = batch[-1]["cursor"]
        self.store.set_last_dream_cursor(new_cursor)
        self.store.compact_history()

        logger.info(f"Dream done: cursor advanced to {new_cursor}")
        return True
