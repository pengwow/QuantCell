"""会话管理 - 管理用户对话历史"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.APPLICATION)


@dataclass
class Session:
    """会话数据结构"""
    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_consolidated: int = 0  # 上次整合的消息索引

    def get_history(self, max_messages: int = 100) -> list[dict[str, Any]]:
        """获取历史消息（限制数量，支持智能过滤）"""
        if not self.messages:
            return []

        messages = self.messages[-max_messages:]

        # 智能过滤：移除过短的测试消息（如 "test", "hello", "hi" 等）
        filtered = []
        test_patterns = {"test", "hello", "hi", "hey", "ok", "yes", "no", "1", "123", "abc"}

        for msg in messages:
            content = str(msg.get("content", "")).strip().lower()
            role = msg.get("role", "")

            # 保留系统消息和工具消息
            if role in ("system", "tool"):
                filtered.append(msg)
                continue

            # 过滤掉明显的测试消息（仅针对 user 角色的短消息）
            if role == "user" and len(content) <= 10 and content in test_patterns:
                logger.debug(f"过滤测试消息: {content}")
                continue

            filtered.append(msg)

        logger.info(f"历史消息: 原始={len(messages)}, 过滤后={len(filtered)}")
        return filtered

    def clear(self) -> None:
        """清空会话"""
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "key": self.key,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_consolidated": self.last_consolidated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """从字典反序列化"""
        session = cls(key=data["key"])
        session.messages = data.get("messages", [])
        session.created_at = datetime.fromisoformat(data["created_at"])
        session.updated_at = datetime.fromisoformat(data["updated_at"])
        session.last_consolidated = data.get("last_consolidated", 0)
        return session


class SessionManager:
    """会话管理器"""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.sessions_dir = workspace / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Session] = {}

    def _get_session_file(self, key: str) -> Path:
        """获取会话文件路径"""
        # 使用安全的文件名
        safe_key = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
        return self.sessions_dir / f"{safe_key}.json"

    def get_or_create(self, key: str) -> Session:
        """获取或创建会话"""
        if key in self._cache:
            return self._cache[key]

        session_file = self._get_session_file(key)
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                session = Session.from_dict(data)
                self._cache[key] = session
                return session
            except Exception as e:
                logger.warning(f"加载会话 {key} 失败: {e}")

        session = Session(key=key)
        self._cache[key] = session
        return session

    def save(self, session: Session) -> None:
        """保存会话"""
        session_file = self._get_session_file(session.key)
        try:
            session_file.write_text(
                json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"保存会话 {session.key} 失败: {e}")

    def invalidate(self, key: str) -> None:
        """从缓存中移除会话"""
        self._cache.pop(key, None)

    def delete(self, key: str) -> bool:
        """删除会话"""
        self.invalidate(key)
        session_file = self._get_session_file(key)
        if session_file.exists():
            try:
                session_file.unlink()
                return True
            except Exception as e:
                logger.error(f"删除会话 {key} 失败: {e}")
        return False
