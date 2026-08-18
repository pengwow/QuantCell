"""测试记忆管理系统 - MemoryStore, Consolidator, AutoCompact, Dream"""

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))


def test_memory_store():
    """测试 MemoryStore 基本功能"""

    from agent.core.memory import MemoryStore

    workspace = Path("/tmp/test_memory_system")
    workspace.mkdir(parents=True, exist_ok=True)

    store = MemoryStore(workspace)

    # 测试读写 MEMORY.md
    store.write_memory("# 长期记忆\n\n- 用户喜欢使用 Python")
    memory = store.read_memory()
    assert "用户喜欢使用 Python" in memory

    # 测试获取上下文
    context = store.get_memory_context()
    assert "长期记忆" in context

    # 测试 history.jsonl
    cursor1 = store.append_history("第一条历史记录")
    cursor2 = store.append_history("第二条历史记录")
    assert cursor2 > cursor1

    # 测试读取未处理的历史
    unprocessed = store.read_unprocessed_history(since_cursor=cursor1)
    assert len(unprocessed) == 1
    assert unprocessed[0]["content"] == "第二条历史记录"

    # 测试 compact_history
    for i in range(10):
        store.append_history(f"测试记录 {i}")
    store.compact_history()
    entries = store._read_entries()
    assert len(entries) <= store.max_history_entries

    # 清理
    import shutil

    shutil.rmtree(workspace, ignore_errors=True)

    return True


async def test_consolidator():
    """测试 Consolidator 功能"""

    from unittest.mock import AsyncMock, MagicMock

    from agent.core.memory import Consolidator, MemoryStore

    workspace = Path("/tmp/test_consolidator")
    workspace.mkdir(parents=True, exist_ok=True)

    store = MemoryStore(workspace)

    # Mock provider
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "- 用户偏好：使用简洁的语言"
    mock_provider.chat = AsyncMock(return_value=mock_response)

    # Mock sessions
    from agent.session.manager import SessionManager

    sessions = SessionManager(workspace)

    # 创建 consolidator
    consolidator = Consolidator(
        store=store,
        provider=mock_provider,
        model="test-model",
        sessions=sessions,
        context_window_tokens=4096,
        build_messages=lambda **kwargs: [],
        get_tool_definitions=lambda: [],
    )

    # 测试 archive 方法
    test_messages = [
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

    summary = await consolidator.archive(test_messages)
    assert summary is not None
    assert "用户偏好" in summary or "Python" in summary or "[no summary]" in summary

    # 测试 pick_consolidation_boundary
    session = sessions.get_or_create("test-session")
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        session.messages.append({"role": role, "content": f"消息 {i}", "timestamp": "2026-04-20 10:{i:02d}"})

    boundary = consolidator.pick_consolidation_boundary(session, tokens_to_remove=100)
    if boundary:
        pass
    else:
        pass

    # 清理
    import shutil

    shutil.rmtree(workspace, ignore_errors=True)

    return True


async def test_auto_compact():
    """测试 AutoCompact 功能"""

    from datetime import datetime, timedelta
    from unittest.mock import AsyncMock, MagicMock

    from agent.core.memory import AutoCompact, Consolidator, MemoryStore
    from agent.session.manager import SessionManager

    workspace = Path("/tmp/test_autocompact")
    workspace.mkdir(parents=True, exist_ok=True)

    store = MemoryStore(workspace)
    sessions = SessionManager(workspace)

    # Mock provider
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "(nothing)"
    mock_provider.chat = AsyncMock(return_value=mock_response)

    consolidator = Consolidator(
        store=store,
        provider=mock_provider,
        model="test-model",
        sessions=sessions,
        context_window_tokens=4096,
        build_messages=lambda **kwargs: [],
        get_tool_definitions=lambda: [],
    )

    # 创建 AutoCompact (TTL=1 分钟，设置为立即过期)
    auto_compact = AutoCompact(
        sessions=sessions,
        consolidator=consolidator,
        session_ttl_minutes=1,  # 1分钟TTL，测试将设置更旧的updated_at
    )

    # 创建一个过期会话
    session = sessions.get_or_create("expired-session")
    old_time = datetime.now() - timedelta(hours=2)  # 2小时前
    session.updated_at = old_time

    for i in range(20):
        session.messages.append(
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"旧消息 {i}",
                "timestamp": old_time.isoformat(),
            }
        )
    sessions.save(session)

    # 调度归档任务
    tasks = []

    def schedule_task(coro):
        tasks.append(coro)

    auto_compact.check_expired(schedule_task)

    assert len(tasks) == 1

    # 执行归档
    try:
        await tasks[0]

        # 重新加载会话
        session = sessions.get_or_create("expired-session")
        assert len(session.messages) <= auto_compact._RECENT_SUFFIX_MESSAGES + 5
    except Exception:
        import traceback

        traceback.print_exc()
        raise

    # 清理
    import shutil

    shutil.rmtree(workspace, ignore_errors=True)

    return True


async def test_dream():
    """测试 Dream 功能"""

    from unittest.mock import AsyncMock, MagicMock

    from agent.core.memory import Dream, MemoryStore

    workspace = Path("/tmp/test_dream")
    workspace.mkdir(parents=True, exist_ok=True)

    store = MemoryStore(workspace)

    # 添加一些历史记录
    store.append_history("用户说：我住在东京")
    store.append_history("用户说：我有一只猫叫 Luna")
    store.write_memory("- 用户信息待补充")

    # Mock provider
    mock_provider = MagicMock()

    # Phase 1 response
    phase1_response = MagicMock()
    phase1_response.content = "[MEMORY] 用户居住在东京\n[MEMORY] 用户有一只猫叫 Luna"
    mock_provider.chat = AsyncMock(return_value=phase1_response)

    dream = Dream(
        store=store,
        provider=mock_provider,
        model="test-model",
    )

    result = await dream.run()

    assert result

    # 验证 cursor 已推进
    new_cursor = store.get_last_dream_cursor()
    assert new_cursor > 0

    # 清理
    import shutil

    shutil.rmtree(workspace, ignore_errors=True)

    return True


async def main():
    """运行所有测试"""

    results = {}

    try:
        results["memory_store"] = test_memory_store()
    except Exception:
        results["memory_store"] = False

    try:
        results["consolidator"] = await test_consolidator()
    except Exception:
        results["consolidator"] = False

    try:
        results["auto_compact"] = await test_auto_compact()
    except Exception:
        results["auto_compact"] = False

    try:
        results["dream"] = await test_dream()
    except Exception:
        results["dream"] = False

    # 汇总结果

    for _name, _passed in results.items():
        pass

    all_passed = all(results.values())

    if all_passed:
        pass
    else:
        [k for k, v in results.items() if not v]

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
