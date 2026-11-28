"""P0-04 验收：interrupted 状态收口链路

验证四点：
1. INTERRUPTED 已纳入 WorkerState 枚举与转换表（running→interrupted 唯一收口入口，
   interrupted→{starting, stopping, stopped} 恢复/停机出口）；
2. interrupted 仍在 RECOVERABLE_STATUSES（水合按 stopped 处理的原逻辑不受影响）；
3. 走正常停止链路：收口后缓存停留 interrupted 时 async_stop_worker 能按
   stopping→stopped 收敛（驱动线程已死，stop_worker 对无运行时幂等成功），
   而不是抛「当前状态 (interrupted) 不允许停止」；
4. core/lifespan._mark_interrupted_workers 必须走状态机 transition，禁止裸 .update( 旁路。
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from worker.core_service import WorkerCoreService
from worker.worker_state import (
    RECOVERABLE_STATUSES,
    WorkerState,
    WorkerStateRecord,
    is_valid_transition,
    worker_state_manager,
)

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def test_interrupted_is_enum_member():
    """interrupted 必须是合法枚举值，否则 transition('interrupted') 直接 ValueError"""
    assert WorkerState.INTERRUPTED.value == "interrupted"
    assert WorkerState("interrupted") is WorkerState.INTERRUPTED


def test_running_to_interrupted_is_valid():
    """启动收口边：running → interrupted（唯一合法入口，调用方为 lifespan 恢复扫描）"""
    assert is_valid_transition("running", "interrupted") is True


def test_interrupted_recovery_exits():
    """恢复出口：interrupted 可重新启动、走正常停止链路或手动确认停机"""
    assert is_valid_transition("interrupted", "starting") is True
    assert is_valid_transition("interrupted", "stopping") is True
    assert is_valid_transition("interrupted", "stopped") is True


def test_interrupted_has_no_other_entries_or_exits():
    """除收口入口与恢复/停机出口外，其余进出边均非法，防止 interrupted 被滥用为通用状态"""
    assert is_valid_transition("stopped", "interrupted") is False
    assert is_valid_transition("starting", "interrupted") is False
    assert is_valid_transition("interrupted", "running") is False


@pytest.mark.asyncio
async def test_stop_worker_after_interrupted_settlement_converges():
    """端到端回归：启动收口 transition(interrupted) 成功后缓存停留 interrupted
    （_hydrate_locked 只在缓存 miss 时才把 interrupted 修正为 stopped，缓存命中
    永不水合），此时 async_stop_worker 必须走 stopping→stopped 正常停止链路收敛，
    而不是抛「当前状态 (interrupted) 不允许停止」。

    状态机用真实单例（转换表正是故障点）；仅 mock DB 持久化与进程内收尾——
    驱动线程已随旧进程消亡，stop_worker 对无运行时幂等视为已停止。
    """
    wid = 990_001
    WorkerCoreService.reset_instance()
    try:
        service = WorkerCoreService()
        # 复现启动收口现场：lifespan 恢复扫描 transition(interrupted) 成功后的缓存状态
        worker_state_manager._state_cache[wid] = WorkerStateRecord(worker_id=wid, status="interrupted")
        with (
            patch.object(worker_state_manager, "_persist_state", new=AsyncMock()),
            patch.object(service, "stop_worker", return_value={"worker_id": wid, "status": "stopped"}),
        ):
            # 修复前此处抛 WorkerOperationException("当前状态 (interrupted) 不允许停止")
            result = await service.async_stop_worker(wid)
            assert result["status"] == "stopping"
            # 等后台收尾 runner 跑完（幂等 stop 收尾 + 状态机补转 stopped）
            for _ in range(100):
                await asyncio.sleep(0.01)
            assert worker_state_manager._state_cache[wid].status == "stopped"
    finally:
        worker_state_manager._state_cache.pop(wid, None)
        WorkerCoreService.reset_instance()


def test_interrupted_still_recoverable():
    """interrupted 必须留在可恢复集合内：重启水合逻辑按 stopped 处理依赖此集合"""
    assert "interrupted" in RECOVERABLE_STATUSES


def test_lifespan_recovery_scan_uses_state_machine():
    """门禁：lifespan 恢复扫描必须走 transition，禁止退回裸 SQL .update( 旁路"""
    lifespan_path = BACKEND_ROOT / "core" / "lifespan.py"
    source = lifespan_path.read_text(encoding="utf-8")

    # 截取 _mark_interrupted_workers 函数体：从 def 起到下一个顶层 def
    start = source.index("def _mark_interrupted_workers")
    next_def = source.find("\ndef ", start + 1)
    body = source[start : next_def if next_def != -1 else len(source)]

    assert "transition(" in body, "恢复扫描应通过 worker_state_manager.transition 收口状态"
    assert ".update(" not in body, "恢复扫描禁止裸 SQL .update( 直写，必须走状态机"
