"""固定计划运行态增量的推导口径（buy 跌破触发 / sell+tp 升破触发）"""

from worker.routes import _plan_runtime_progress

LEVELS = [
    {"index": 0, "price": 100.0, "action": "buy", "target_position": 0.1, "label": "L0"},
    {"index": 1, "price": 98.0, "action": "buy", "target_position": 0.15, "label": "L1"},
    {"index": 2, "price": 96.0, "action": "buy", "target_position": 0.2, "label": "L2"},
    {"index": 3, "price": 101.5, "action": "tp", "target_position": 0.0, "label": "止盈"},
]


def test_all_above_entry_nothing_triggered():
    out = _plan_runtime_progress({"levels": LEVELS}, {"status": {"last_price": 100.0}})
    # 口径：恰在层价上（=建仓价 100）视为「未穿越」→ 0 层已触发；下一未到价层按计划层序 = L1
    assert out["triggered_count"] == 0
    assert out["triggered_indexes"] == []
    assert out["next_trigger"]["price"] == 98.0


def test_two_layers_triggered():
    out = _plan_runtime_progress({"levels": LEVELS}, {"last_price": 97.5})
    assert out["triggered_count"] == 2  # 100/98 两层已跌破
    assert out["triggered_indexes"] == [0, 1]
    assert out["next_trigger"]["price"] == 96.0
    assert out["next_trigger"]["distance_pct"] == round((96.0 - 97.5) / 97.5 * 100, 2)


def test_no_last_price_returns_zero():
    out = _plan_runtime_progress({"levels": LEVELS}, None)
    assert out == {"triggered_count": 0, "triggered_indexes": [], "next_trigger": None}


def test_zero_last_price_returns_zero():
    """刚启动快照 last_price=0：不得除零炸 500（2026-11-28 冒烟回归）"""
    out = _plan_runtime_progress({"levels": LEVELS}, {"last_price": 0.0})
    assert out == {"triggered_count": 0, "triggered_indexes": [], "next_trigger": None}
