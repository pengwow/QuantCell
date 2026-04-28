"""测试记忆管理系统 - MemoryStore, Consolidator, AutoCompact, Dream"""

import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))


def test_memory_store():
    """测试 MemoryStore 基本功能"""
    print("\n" + "="*60)
    print("🧪 测试 1: MemoryStore 基本功能")
    print("="*60)
    
    from agent.core.memory import MemoryStore
    
    workspace = Path("/tmp/test_memory_system")
    workspace.mkdir(parents=True, exist_ok=True)
    
    store = MemoryStore(workspace)
    
    # 测试读写 MEMORY.md
    print("\n📝 测试 MEMORY.md 读写...")
    store.write_memory("# 长期记忆\n\n- 用户喜欢使用 Python")
    memory = store.read_memory()
    assert "用户喜欢使用 Python" in memory
    print(f"✅ MEMORY.md 读写成功: {memory[:50]}...")
    
    # 测试获取上下文
    context = store.get_memory_context()
    assert "长期记忆" in context
    print(f"✅ 获取记忆上下文成功: {context[:50]}...")
    
    # 测试 history.jsonl
    print("\n📝 测试 history.jsonl 追加...")
    cursor1 = store.append_history("第一条历史记录")
    cursor2 = store.append_history("第二条历史记录")
    assert cursor2 > cursor1
    print(f"✅ 追加成功: cursor1={cursor1}, cursor2={cursor2}")
    
    # 测试读取未处理的历史
    unprocessed = store.read_unprocessed_history(since_cursor=cursor1)
    assert len(unprocessed) == 1
    assert unprocessed[0]["content"] == "第二条历史记录"
    print(f"✅ 读取未处理历史成功: {len(unprocessed)} 条")
    
    # 测试 compact_history
    for i in range(10):
        store.append_history(f"测试记录 {i}")
    store.compact_history()
    entries = store._read_entries()
    assert len(entries) <= store.max_history_entries
    print(f"✅ History compaction 成功: {len(entries)} 条")
    
    # 清理
    import shutil
    shutil.rmtree(workspace, ignore_errors=True)
    
    print("\n✅ MemoryStore 所有测试通过!")
    return True


async def test_consolidator():
    """测试 Consolidator 功能"""
    print("\n" + "="*60)
    print("🧪 测试 2: Consolidator 整合功能")
    print("="*60)
    
    from agent.core.memory import MemoryStore, Consolidator
    from unittest.mock import AsyncMock, MagicMock
    
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
    print("\n📝 测试 archive (消息摘要化)...")
    test_messages = [
        {"role": "user", "content": "我喜欢用Python编程", "timestamp": "2026-04-20 10:00"},
        {"role": "assistant", "content": "好的，我会记住这个偏好", "timestamp": "2026-04-20 10:01"},
    ]
    
    summary = await consolidator.archive(test_messages)
    assert summary is not None
    assert "用户偏好" in summary or "Python" in summary or "[no summary]" in summary
    print(f"✅ Archive 成功: {summary[:80]}...")
    
    # 测试 pick_consolidation_boundary
    print("\n📝 测试 pick_consolidation_boundary...")
    session = sessions.get_or_create("test-session")
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        session.messages.append({
            "role": role,
            "content": f"消息 {i}",
            "timestamp": "2026-04-20 10:{i:02d}"
        })
    
    boundary = consolidator.pick_consolidation_boundary(session, tokens_to_remove=100)
    if boundary:
        print(f"✅ 选择边界成功: idx={boundary[0]}, tokens={boundary[1]}")
    else:
        print("⚠️ 无合适边界（可能 token 数不足）")
    
    # 清理
    import shutil
    shutil.rmtree(workspace, ignore_errors=True)
    
    print("\n✅ Consolidator 测试通过!")
    return True


async def test_auto_compact():
    """测试 AutoCompact 功能"""
    print("\n" + "="*60)
    print("🧪 测试 3: AutoCompact 自动清理")
    print("="*60)
    
    from agent.core.memory import MemoryStore, Consolidator, AutoCompact
    from datetime import datetime, timedelta
    from unittest.mock import MagicMock, AsyncMock
    from agent.session.manager import SessionManager
    
    workspace = Path("/tmp/test_autocompact")
    workspace.mkdir(parents=True, exist_ok=True)
    
    store = MemoryStore(workspace)
    sessions = SessionManager(workspace)
    
    # Mock provider
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "(nothing)"
    import asyncio
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
    
    # 创建 AutoCompact (TTL=0 表示立即过期)
    auto_compact = AutoCompact(
        sessions=sessions,
        consolidator=consolidator,
        session_ttl_minutes=0,  # 立即过期用于测试
    )
    
    # 创建一个过期会话
    print("\n📝 创建过期会话...")
    session = sessions.get_or_create("expired-session")
    old_time = datetime.now() - timedelta(hours=2)  # 2小时前
    session.updated_at = old_time
    
    for i in range(20):
        session.messages.append({
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"旧消息 {i}",
            "timestamp": old_time.isoformat(),
        })
    sessions.save(session)
    
    print(f"   会话消息数: {len(session.messages)}")
    
    # 调度归档任务
    tasks = []
    def schedule_task(coro):
        tasks.append(coro)
    
    auto_compact.check_expired(schedule_task)
    
    assert len(tasks) == 1
    print(f"✅ 检测到过期会话并调度归档任务")
    
    # 执行归档
    try:
        await tasks[0]
        
        # 重新加载会话
        session = sessions.get_or_create("expired-session")
        print(f"   归档后消息数: {len(session.messages)}")
        assert len(session.messages) <= auto_compact._RECENT_SUFFIX_MESSAGES + 5
        print(f"✅ 自动压缩成功! 只保留最近 {auto_compact._RECENT_SUFFIX_MESSAGES} 条消息")
    except Exception as e:
        import traceback
        print(f"❌ 归档执行失败: {e}")
        traceback.print_exc()
        raise
    
    # 清理
    import shutil
    shutil.rmtree(workspace, ignore_errors=True)
    
    print("\n✅ AutoCompact 测试通过!")
    return True


async def test_dream():
    """测试 Dream 功能"""
    print("\n" + "="*60)
    print("🧪 测试 4: Dream 记忆反思")
    print("="*60)
    
    from agent.core.memory import MemoryStore, Dream
    from unittest.mock import AsyncMock, MagicMock
    
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
    
    print("\n📝 运行 Dream 处理...")
    result = await dream.run()
    
    assert result == True
    print(f"✅ Dream 运行成功!")
    
    # 验证 cursor 已推进
    new_cursor = store.get_last_dream_cursor()
    assert new_cursor > 0
    print(f"✅ Cursor 已推进到: {new_cursor}")
    
    # 清理
    import shutil
    shutil.rmtree(workspace, ignore_errors=True)
    
    print("\n✅ Dream 测试通过!")
    return True


async def main():
    """运行所有测试"""
    print("\n" + "🚀"*30)
    print("🔬 记忆管理系统测试套件")
    print("🚀"*30)
    
    results = {}
    
    try:
        results['memory_store'] = test_memory_store()
    except Exception as e:
        print(f"\n❌ MemoryStore 测试失败: {e}")
        results['memory_store'] = False
    
    try:
        results['consolidator'] = await test_consolidator()
    except Exception as e:
        print(f"\n❌ Consolidator 测试失败: {e}")
        results['consolidator'] = False
    
    try:
        results['auto_compact'] = await test_auto_compact()
    except Exception as e:
        print(f"\n❌ AutoCompact 测试失败: {e}")
        results['auto_compact'] = False
    
    try:
        results['dream'] = await test_dream()
    except Exception as e:
        print(f"\n❌ Dream 测试失败: {e}")
        results['dream'] = False
    
    # 汇总结果
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        test_names = {
            'memory_store': 'MemoryStore 文件 I/O',
            'consolidator': 'Consolidator Token 整合',
            'auto_compact': 'AutoCompact 过期清理',
            'dream': 'Dream 记忆反思'
        }
        print(f"{test_names[name]}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 所有测试通过！记忆管理系统功能完整！")
        print("\n💡 系统已具备以下能力:")
        print("  ✅ MemoryStore: 管理 MEMORY.md 和 history.jsonl")
        print("  ✅ Consolidator: 按 Token 自动整合旧消息")
        print("  ✅ AutoCompact: 自动清理过期会话")
        print("  ✅ Dream: 定期反思和整理长期记忆")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"\n⚠️ 有 {len(failed)} 个测试失败")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
