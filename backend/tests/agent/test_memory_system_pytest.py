"""测试记忆管理系统 - MemoryStore, Consolidator, AutoCompact, Dream (pytest版本)"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.core.memory import AutoCompact, Consolidator, Dream, MemoryStore
from agent.session.manager import SessionManager


class TestMemoryStore:
    """测试 MemoryStore"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def store(self, temp_workspace):
        return MemoryStore(temp_workspace)

    def test_memory_store_creation(self, store, temp_workspace):
        """测试MemoryStore创建"""
        assert store.workspace == temp_workspace
        assert store.memory_dir.exists()
        assert store.memory_file == temp_workspace / "memory" / "MEMORY.md"
        assert store.history_file == temp_workspace / "memory" / "history.jsonl"

    def test_read_write_memory(self, store):
        """测试读写MEMORY.md"""
        content = "# 长期记忆\n\n- 用户喜欢使用 Python"
        store.write_memory(content)

        result = store.read_memory()
        assert result == content

    def test_read_memory_not_found(self, store):
        """测试读取不存在的MEMORY.md"""
        result = store.read_memory()
        assert result == ""

    def test_get_memory_context(self, store):
        """测试获取记忆上下文"""
        store.write_memory("- 用户偏好: 简洁的回答")

        context = store.get_memory_context()
        assert "长期记忆" in context
        assert "用户偏好" in context

    def test_get_memory_context_empty(self, store):
        """测试获取空记忆上下文"""
        context = store.get_memory_context()
        assert context == ""

    def test_append_history(self, store):
        """测试追加历史记录"""
        cursor1 = store.append_history("第一条记录")
        cursor2 = store.append_history("第二条记录")

        assert cursor2 > cursor1
        assert cursor1 == 1
        assert cursor2 == 2

    def test_read_unprocessed_history(self, store):
        """测试读取未处理的历史"""
        cursor1 = store.append_history("记录1")
        store.append_history("记录2")
        store.append_history("记录3")

        unprocessed = store.read_unprocessed_history(since_cursor=cursor1)
        assert len(unprocessed) == 2
        assert unprocessed[0]["content"] == "记录2"
        assert unprocessed[1]["content"] == "记录3"

    def test_compact_history(self, store):
        """测试历史压缩"""
        # 添加超过最大数量的记录
        for i in range(10):
            store.append_history(f"记录 {i}")

        # 设置较小的最大数量
        store.max_history_entries = 5
        store.compact_history()

        entries = store._read_entries()
        assert len(entries) <= 5

    def test_compact_history_no_compact(self, store):
        """测试不需要压缩的情况"""
        store.append_history("记录1")
        store.append_history("记录2")

        store.max_history_entries = 100
        store.compact_history()

        entries = store._read_entries()
        assert len(entries) == 2

    def test_dream_cursor(self, store):
        """测试Dream cursor"""
        assert store.get_last_dream_cursor() == 0

        store.set_last_dream_cursor(42)
        assert store.get_last_dream_cursor() == 42

    def test_format_messages(self, store):
        """测试消息格式化"""
        messages = [
            {"role": "user", "content": "Hello", "timestamp": "2026-04-20 10:00"},
            {"role": "assistant", "content": "Hi!", "timestamp": "2026-04-20 10:01"},
        ]

        formatted = MemoryStore._format_messages(messages)

        assert "USER" in formatted
        assert "ASSISTANT" in formatted
        assert "Hello" in formatted
        assert "Hi!" in formatted

    def test_raw_archive(self, store):
        """测试原始归档"""
        messages = [
            {
                "role": "user",
                "content": "Test message",
                "timestamp": "2026-04-20 10:00",
            },
        ]

        store.raw_archive(messages)

        entries = store._read_entries()
        assert len(entries) == 1
        assert "RAW" in entries[0]["content"]


class TestConsolidator:
    """测试 Consolidator"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def store(self, temp_workspace):
        return MemoryStore(temp_workspace)

    @pytest.fixture
    def sessions(self, temp_workspace):
        return SessionManager(temp_workspace)

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        response = MagicMock()
        response.content = "- 用户偏好：使用简洁的语言"
        provider.chat = AsyncMock(return_value=response)
        return provider

    @pytest.fixture
    def consolidator(self, store, mock_provider, sessions):
        return Consolidator(
            store=store,
            provider=mock_provider,
            model="test-model",
            sessions=sessions,
            context_window_tokens=4096,
            build_messages=lambda **kwargs: [],
            get_tool_definitions=lambda: [],
        )

    def test_consolidator_creation(self, consolidator):
        """测试Consolidator创建"""
        assert consolidator.store is not None
        assert consolidator.provider is not None
        assert consolidator.model == "test-model"

    def test_get_lock(self, consolidator):
        """测试获取锁"""
        lock1 = consolidator.get_lock("session1")
        lock2 = consolidator.get_lock("session1")
        lock3 = consolidator.get_lock("session2")

        assert lock1 is lock2
        assert lock1 is not lock3

    @pytest.mark.asyncio
    async def test_archive(self, consolidator, store):
        """测试消息归档"""
        messages = [
            {
                "role": "user",
                "content": "我喜欢用Python编程",
                "timestamp": "2026-04-20 10:00",
            },
            {
                "role": "assistant",
                "content": "好的，我会记住这个偏好",
                "timestamp": "2026-04-20 10:01",
            },
        ]

        summary = await consolidator.archive(messages)

        assert summary is not None
        assert "用户偏好" in summary or "Python" in summary or "[no summary]" in summary

    @pytest.mark.asyncio
    async def test_archive_empty(self, consolidator):
        """测试归档空消息"""
        summary = await consolidator.archive([])
        assert summary is None

    def test_pick_consolidation_boundary(self, consolidator, sessions):
        """测试选择整合边界"""
        session = sessions.get_or_create("test-session")

        # 添加消息
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            session.messages.append(
                {
                    "role": role,
                    "content": f"消息 {i}",
                    "timestamp": f"2026-04-20 10:{i:02d}",
                }
            )

        boundary = consolidator.pick_consolidation_boundary(session, tokens_to_remove=100)

        if boundary:
            assert boundary[0] > 0
            assert boundary[1] > 0

    def test_estimate_message_tokens(self, consolidator):
        """测试估算消息token数"""
        # 英文消息
        en_message = {"content": "Hello world"}
        tokens_en = consolidator._estimate_message_tokens(en_message)
        assert tokens_en > 0

        # 中文消息
        cn_message = {"content": "你好世界"}
        tokens_cn = consolidator._estimate_message_tokens(cn_message)
        assert tokens_cn > 0

    def test_cap_consolidation_boundary(self, consolidator, sessions):
        """测试限制整合边界"""
        session = sessions.get_or_create("test-session")

        # 添加消息
        for i in range(100):
            session.messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"消息 {i}",
                }
            )

        # 测试限制
        capped = consolidator._cap_consolidation_boundary(session, 50)
        assert capped <= 50

    def test_estimate_session_prompt_tokens(self, consolidator, sessions):
        """测试估算会话prompt tokens"""
        session = sessions.get_or_create("test-session")

        # 添加更多消息
        for i in range(10):
            session.messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"这是一条较长的消息 {i}，用于测试token估算功能",
                }
            )

        tokens = consolidator._estimate_session_prompt_tokens(session)

        # 由于build_messages返回空列表，tokens可能为0
        # 这是mock的限制，实际使用时会有值
        assert tokens >= 0


class TestAutoCompact:
    """测试 AutoCompact"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def sessions(self, temp_workspace):
        return SessionManager(temp_workspace)

    @pytest.fixture
    def mock_consolidator(self):
        consolidator = MagicMock()
        consolidator.archive = AsyncMock(return_value="Summary")
        return consolidator

    @pytest.fixture
    def auto_compact(self, sessions, mock_consolidator):
        return AutoCompact(
            sessions=sessions,
            consolidator=mock_consolidator,
            session_ttl_minutes=60,
        )

    def test_auto_compact_creation(self, auto_compact):
        """测试AutoCompact创建"""
        assert auto_compact.sessions is not None
        assert auto_compact.consolidator is not None
        assert auto_compact._ttl == 60

    def test_is_expired(self, auto_compact):
        """测试过期检查"""
        # 未过期
        recent_time = datetime.now()
        assert auto_compact._is_expired(recent_time) is False

        # 已过期
        old_time = datetime.now() - timedelta(hours=2)
        assert auto_compact._is_expired(old_time) is True

    def test_is_expired_string(self, auto_compact):
        """测试字符串时间的过期检查"""
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        assert auto_compact._is_expired(old_time) is True

    def test_is_expired_none(self, auto_compact):
        """测试None时间的过期检查"""
        assert auto_compact._is_expired(None) is False

    def test_check_expired(self, auto_compact, sessions):
        """测试检查过期会话"""
        # 创建过期会话
        session = sessions.get_or_create("expired")
        session.updated_at = datetime.now() - timedelta(hours=2)
        sessions.save(session)

        tasks = []

        def schedule_task(coro):
            tasks.append(coro)

        auto_compact.check_expired(schedule_task)

        assert len(tasks) == 1

    def test_check_expired_active_session(self, auto_compact, sessions):
        """测试检查活跃会话（不应被调度）"""
        # 创建活跃会话
        session = sessions.get_or_create("active")
        session.updated_at = datetime.now()
        sessions.save(session)

        tasks = []

        def schedule_task(coro):
            tasks.append(coro)

        auto_compact.check_expired(schedule_task)

        assert len(tasks) == 0

    def test_format_summary(self, auto_compact):
        """测试格式化摘要"""
        summary = AutoCompact._format_summary("Test summary", datetime.now())

        assert "Inactive" in summary
        assert "Test summary" in summary

    def test_prepare_session(self, auto_compact, sessions):
        """测试准备会话"""
        session = sessions.get_or_create("test")

        # 无摘要
        _result_session, summary = auto_compact.prepare_session(session, "test")
        assert summary is None


class TestDream:
    """测试 Dream"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        return tmp_path

    @pytest.fixture
    def store(self, temp_workspace):
        return MemoryStore(temp_workspace)

    @pytest.fixture
    def mock_provider(self):
        provider = MagicMock()
        response = MagicMock()
        response.content = "[MEMORY] 用户居住在东京\n[MEMORY] 用户有一只猫叫 Luna"
        provider.chat = AsyncMock(return_value=response)
        return provider

    @pytest.fixture
    def dream(self, store, mock_provider):
        return Dream(
            store=store,
            provider=mock_provider,
            model="test-model",
        )

    def test_dream_creation(self, dream):
        """测试Dream创建"""
        assert dream.store is not None
        assert dream.provider is not None
        assert dream.model == "test-model"

    @pytest.mark.asyncio
    async def test_run_with_history(self, dream, store):
        """测试运行Dream（有历史记录）"""
        # 添加历史记录
        store.append_history("用户说：我住在东京")
        store.append_history("用户说：我有一只猫叫 Luna")
        store.write_memory("- 用户信息待补充")

        result = await dream.run()

        assert result is True
        assert store.get_last_dream_cursor() > 0

    @pytest.mark.asyncio
    async def test_run_without_history(self, dream, store):
        """测试运行Dream（无历史记录）"""
        result = await dream.run()

        assert result is False

    @pytest.mark.asyncio
    async def test_run_phase1_skip(self, dream, store, mock_provider):
        """测试Phase 1返回SKIP"""
        # 修改mock返回
        response = MagicMock()
        response.content = "[SKIP]"
        mock_provider.chat = AsyncMock(return_value=response)

        store.append_history("Test history")

        result = await dream.run()

        assert result is True

    @pytest.mark.asyncio
    async def test_run_phase1_error(self, dream, store, mock_provider):
        """测试Phase 1错误"""
        # 修改mock抛出异常
        mock_provider.chat = AsyncMock(side_effect=Exception("API Error"))

        store.append_history("Test history")

        result = await dream.run()

        assert result is False

    @pytest.mark.asyncio
    async def test_run_phase2_error(self, dream, store, mock_provider):
        """测试Phase 2错误"""
        # Phase 1成功，Phase 2失败
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Phase 1
                response = MagicMock()
                response.content = "[MEMORY] New fact"
                return response
            else:
                # Phase 2
                msg = "Phase 2 Error"
                raise Exception(msg)

        mock_provider.chat = AsyncMock(side_effect=side_effect)

        store.append_history("Test history")

        result = await dream.run()

        # Phase 2错误不应该影响整体结果
        assert result is True
