"""P0-04 验收：interrupted 状态收口链路

验证三点：
1. INTERRUPTED 已纳入 WorkerState 枚举与转换表（running→interrupted 唯一收口入口，
   interrupted→{starting, stopped} 恢复出口）；
2. interrupted 仍在 RECOVERABLE_STATUSES（水合按 stopped 处理的原逻辑不受影响）；
3. core/lifespan._mark_interrupted_workers 必须走状态机 transition，禁止裸 .update( 旁路。
"""

from pathlib import Path

from worker.worker_state import (
    RECOVERABLE_STATUSES,
    WorkerState,
    is_valid_transition,
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
    """恢复出口：interrupted 可重新启动或手动确认停机"""
    assert is_valid_transition("interrupted", "starting") is True
    assert is_valid_transition("interrupted", "stopped") is True


def test_interrupted_has_no_other_entries_or_exits():
    """除收口入口与两个恢复出口外，其余进出边均非法，防止 interrupted 被滥用为通用状态"""
    assert is_valid_transition("stopped", "interrupted") is False
    assert is_valid_transition("starting", "interrupted") is False
    assert is_valid_transition("interrupted", "running") is False
    assert is_valid_transition("interrupted", "stopping") is False


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
