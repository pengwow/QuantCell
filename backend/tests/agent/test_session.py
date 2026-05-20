"""会话管理测试 - Session 和 SessionManager"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from agent.session.manager import Session, SessionManager


class TestSession:
    """测试 Session 数据结构"""

    def test_session_creation(self):
        """测试会话创建"""
        session = Session(key="test-session")
        
        assert session.key == "test-session"
        assert session.messages == []
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)
        assert session.last_consolidated == 0

    def test_session_with_messages(self):
        """测试带消息的会话"""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        session = Session(key="test", messages=messages)
        
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[1]["role"] == "assistant"

    def test_session_serialization(self):
        """测试会话序列化/反序列化"""
        session = Session(key="test-serial")
        session.messages = [
            {"role": "user", "content": "Test message"},
            {"role": "assistant", "content": "Response"},
        ]
        session.last_consolidated = 1
        
        # 序列化
        data = session.to_dict()
        assert data["key"] == "test-serial"
        assert len(data["messages"]) == 2
        assert data["last_consolidated"] == 1
        assert "created_at" in data
        assert "updated_at" in data
        
        # 反序列化
        restored = Session.from_dict(data)
        assert restored.key == session.key
        assert len(restored.messages) == len(session.messages)
        assert restored.last_consolidated == session.last_consolidated

    def test_session_history(self):
        """测试历史消息获取"""
        session = Session(key="test-history")
        
        # 添加多条消息
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            session.messages.append({
                "role": role,
                "content": f"Message {i}",
            })
        
        # 测试限制数量
        history = session.get_history(max_messages=5)
        assert len(history) == 5
        assert history[0]["content"] == "Message 15"
        assert history[-1]["content"] == "Message 19"

    def test_session_history_filtering(self):
        """测试历史消息过滤"""
        session = Session(key="test-filter")
        session.messages = [
            {"role": "user", "content": "test"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
        ]
        
        history = session.get_history(max_messages=100)
        
        # 应该过滤掉 "test" 和 "hi"，保留其他消息
        assert len(history) == 4
        assert history[0]["content"] == "Hello!"
        assert history[1]["content"] == "Hi there!"
        assert history[2]["content"] == "What is 2+2?"
        assert history[3]["content"] == "4"

    def test_session_clear(self):
        """测试清空会话"""
        session = Session(key="test-clear")
        session.messages = [{"role": "user", "content": "Test"}]
        session.last_consolidated = 5
        
        session.clear()
        
        assert session.messages == []
        assert session.last_consolidated == 0
        assert isinstance(session.updated_at, datetime)


class TestSessionManager:
    """测试 SessionManager"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def manager(self, temp_workspace):
        return SessionManager(temp_workspace)

    def test_get_or_create_new(self, manager):
        """测试获取或创建新会话"""
        session = manager.get_or_create("new-session")
        
        assert session.key == "new-session"
        assert session.messages == []

    def test_get_or_create_existing(self, manager, temp_workspace):
        """测试获取已存在的会话"""
        # 先创建一个会话文件
        session_data = {
            "key": "existing-session",
            "messages": [{"role": "user", "content": "Hello"}],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "last_consolidated": 0,
        }
        session_file = temp_workspace / "sessions" / "existing-session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps(session_data), encoding="utf-8")
        
        # 获取会话
        session = manager.get_or_create("existing-session")
        
        assert session.key == "existing-session"
        assert len(session.messages) == 1
        assert session.messages[0]["content"] == "Hello"

    def test_get_or_create_cache(self, manager):
        """测试会话缓存"""
        session1 = manager.get_or_create("cached-session")
        session2 = manager.get_or_create("cached-session")
        
        assert session1 is session2

    def test_save_session(self, manager, temp_workspace):
        """测试保存会话"""
        session = manager.get_or_create("save-test")
        session.messages = [{"role": "user", "content": "Save me"}]
        
        manager.save(session)
        
        # 验证文件已创建
        session_file = temp_workspace / "sessions" / "save-test.json"
        assert session_file.exists()
        
        # 验证内容
        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert data["key"] == "save-test"
        assert len(data["messages"]) == 1

    def test_invalidate_session(self, manager):
        """测试使会话缓存失效"""
        session = manager.get_or_create("invalidate-test")
        manager.invalidate("invalidate-test")
        
        # 重新获取应该创建新实例
        session2 = manager.get_or_create("invalidate-test")
        assert session is not session2

    def test_delete_session(self, manager, temp_workspace):
        """测试删除会话"""
        # 创建并保存会话
        session = manager.get_or_create("delete-test")
        manager.save(session)
        
        # 验证文件存在
        session_file = temp_workspace / "sessions" / "delete-test.json"
        assert session_file.exists()
        
        # 删除会话
        result = manager.delete("delete-test")
        
        assert result is True
        assert not session_file.exists()

    def test_create_session(self, manager):
        """测试创建会话（带名称）"""
        result = manager.create_session("My Session")
        
        assert "id" in result
        assert result["name"] == "My Session"
        assert "created_at" in result
        assert "updated_at" in result

    def test_get_session_info(self, manager):
        """测试获取会话信息"""
        session = manager.get_or_create("info-test")
        session.messages = [{"role": "user", "content": "Test"}]
        manager.save(session)
        
        info = manager.get_session_info("info-test")
        
        assert info is not None
        assert info["id"] == "info-test"
        assert info["message_count"] == 1

    def test_get_history(self, manager):
        """测试获取会话历史"""
        session = manager.get_or_create("history-test")
        for i in range(10):
            session.messages.append({"role": "user", "content": f"Message {i}"})
        manager.save(session)
        
        result = manager.get_history("history-test", limit=5)
        
        assert result["session_id"] == "history-test"
        assert len(result["history"]) == 5
        assert result["total_messages"] == 10

    def test_clear_session(self, manager):
        """测试清空会话"""
        session = manager.get_or_create("clear-test")
        session.messages = [{"role": "user", "content": "To be cleared"}]
        manager.save(session)
        
        result = manager.clear_session("clear-test")
        
        assert result is True
        session = manager.get_or_create("clear-test")
        assert len(session.messages) == 0

    def test_list_sessions(self, manager, temp_workspace):
        """测试列出所有会话"""
        # 创建几个会话
        for i in range(3):
            session = manager.get_or_create(f"session-{i}")
            session.messages = [{"role": "user", "content": f"Message {i}"}]
            manager.save(session)
        
        sessions = manager.list_sessions()
        
        assert len(sessions) >= 3
        session_keys = [s["key"] for s in sessions]
        assert "session-0" in session_keys
        assert "session-1" in session_keys
        assert "session-2" in session_keys

    def test_safe_key_generation(self, manager, temp_workspace):
        """测试安全文件名生成"""
        # 使用包含特殊字符的key
        session = manager.get_or_create("test/special:chars")
        manager.save(session)
        
        # 验证文件名是安全的
        session_file = temp_workspace / "sessions" / "test_special_chars.json"
        assert session_file.exists()
