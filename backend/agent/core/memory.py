"""Agent 记忆系统 - 持久化存储"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logger import get_logger, LogType

if TYPE_CHECKING:
    from ..providers.base import LLMProvider
    from ..session.manager import Session

logger = get_logger(__name__, LogType.APPLICATION)

_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "将记忆整合结果保存到持久存储",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "总结关键事件/决策/主题的段落（2-5句）。以 [YYYY-MM-DD HH:MM] 开头。包含对 grep 搜索有用的细节。",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "完整的更新后的长期记忆（markdown 格式）。包含所有现有事实和新事实。如果没有新内容则返回原样。",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


class MemoryStore:
    """双层记忆: MEMORY.md（长期事实）+ HISTORY.md（可搜索日志）"""

    def __init__(self, workspace: Path):
        self.memory_dir = workspace / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"

    def read_long_term(self) -> str:
        """读取长期记忆"""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """写入长期记忆"""
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """追加历史记录"""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        """获取记忆上下文"""
        long_term = self.read_long_term()
        return f"## 长期记忆\n{long_term}" if long_term else ""

    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
    ) -> bool:
        """
        将旧消息整合到 MEMORY.md + HISTORY.md
        
        通过 LLM 工具调用完成
        成功返回 True
        """
        if archive_all:
            old_messages = session.messages
            keep_count = 0
            logger.info(f"记忆整合 (archive_all): {len(session.messages)} 条消息")
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return True
            if len(session.messages) - session.last_consolidated <= 0:
                return True
            old_messages = session.messages[session.last_consolidated:-keep_count]
            if not old_messages:
                return True
            logger.info(f"记忆整合: {len(old_messages)} 条待整合, {keep_count} 条保留")

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [工具: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}")

        current_memory = self.read_long_term()
        prompt = f"""处理这段对话并调用 save_memory 工具进行整合。

## 当前长期记忆
{current_memory or "(空)"}

## 待处理的对话
{chr(10).join(lines)}"""

        try:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "你是记忆整合代理。调用 save_memory 工具整合对话。"},
                    {"role": "user", "content": prompt},
                ],
                tools=_SAVE_MEMORY_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning("记忆整合: LLM 未调用 save_memory，跳过")
                return False

            args = response.tool_calls[0].arguments
            # 某些提供者将参数作为 JSON 字符串返回
            if isinstance(args, str):
                args = json.loads(args)
            # 处理参数为列表的边缘情况
            if isinstance(args, list):
                if args and isinstance(args[0], dict):
                    args = args[0]
                else:
                    logger.warning("记忆整合: 意外的参数格式（空列表或非字典列表）")
                    return False
            if not isinstance(args, dict):
                logger.warning(f"记忆整合: 意外的参数类型 {type(args).__name__}")
                return False

            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
            if update := args.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    self.write_long_term(update)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info(f"记忆整合完成: {len(session.messages)} 条消息, last_consolidated={session.last_consolidated}")
            return True
        except Exception:
            logger.exception("记忆整合失败")
            return False
