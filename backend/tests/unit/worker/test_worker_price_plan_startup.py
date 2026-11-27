"""启动链路多标的固化公约测试（spec §4）。

只锁 _persist_worker_price_plan 公约（不测启动编排本身）：
1. per-symbol 分份：每个标的一份完整固化 entry，preview 逐标的独立调用；
2. ref 缺失（None / <=0）→ pending 占位（None），不阻塞其他标的（Partial 固化）；
3. preview 失败（PlanPreviewError）→ 不炸启动链路，该标的 pending；
4. 非计划策略（has_price_plan False）→ 不写库；
5. fixed_at 为 9 位纳秒 ISO 时间戳（项目时间戳规范）。

strategy 服务 / crud 写入全部 monkeypatch（真行情服务的异常面与限速不进公约测试）。
"""

import re

import pytest

from strategy.service import PlanPreviewError
from worker.strategy_manager import StrategyManager


class _StubSvc:
    """计划服务 stub：has_price_plan 可控；preview 返回含 ref 身份的 dict"""

    def __init__(self, supported=True, error=None):
        self.supported = supported
        self.error = error
        self.previews = []  # (name, params, ref_price) 记录，供「逐标的独立调用」断言

    def has_price_plan(self, name):
        return self.supported

    def preview_price_plan(self, name, params=None, ref_price=None):
        self.previews.append((name, params, ref_price))
        if self.error is not None:
            raise self.error
        return {"ref_price": ref_price}  # 每次新 dict，身份互不相同


@pytest.fixture
def svc(monkeypatch):
    """_persist_worker_price_plan 经 strategy.routes.get_strategy_service 取服务
    （函数内 import），patch 模块属性即可生效"""
    stub = _StubSvc()
    monkeypatch.setattr("strategy.routes.get_strategy_service", lambda: stub)
    return stub


@pytest.fixture
def saved(monkeypatch):
    calls = []

    def _fake_save(worker_id, plans):
        calls.append((int(worker_id), dict(plans)))
        return True

    monkeypatch.setattr("worker.strategy_manager.crud.save_worker_price_plans", _fake_save)
    return calls


@pytest.fixture
def manager():
    return StrategyManager()


NS_TS = re.compile(r"\.\d{9}")


def test_persist_per_symbol_entries(manager, svc, saved):
    """两个 ref 有效标的：每份 fixed entry 完整（symbol/state/ref_price/plan/fixed_at），
    plan 是逐标的独立 preview 产物（身份互不相同）"""
    manager._persist_worker_price_plan(1, "grid", {"levels": 20}, {"BTCUSDT": 100.0, "ETHUSDT": 2000.0})

    assert len(saved) == 1
    wid, plans = saved[0]
    assert wid == 1
    assert set(plans.keys()) == {"BTCUSDT", "ETHUSDT"}
    for sym, ref in (("BTCUSDT", 100.0), ("ETHUSDT", 2000.0)):
        entry = plans[sym]
        assert entry["symbol"] == sym
        assert entry["state"] == "fixed"
        assert entry["ref_price"] == ref
        assert entry["plan"] == {"ref_price": ref}
    assert plans["BTCUSDT"]["plan"] is not plans["ETHUSDT"]["plan"]  # 逐标的独立 preview
    assert svc.previews == [("grid", {"levels": 20}, 100.0), ("grid", {"levels": 20}, 2000.0)]
    # 顺序按 ref_prices 输入序
    assert list(plans.keys()) == ["BTCUSDT", "ETHUSDT"]


def test_persist_fixed_at_nanoseconds(manager, svc, saved):
    """fixed_at 是 9 位小数的 ISO 时间戳（纳秒规范，补尾零）"""
    manager._persist_worker_price_plan(1, "grid", {}, {"BTCUSDT": 100.0})
    _, plans = saved[0]
    assert NS_TS.search(plans["BTCUSDT"]["fixed_at"])


def test_persist_mixed_fixed_and_pending(manager, svc, saved):
    """部分标的有效：有价固化、无价/零/负价 pending"""
    manager._persist_worker_price_plan(1, "grid", {}, {"BTCUSDT": 100.0, "ETHUSDT": None, "LTCUSDT": 0, "XRPUSDT": -5})

    _, plans = saved[0]
    assert plans["BTCUSDT"]["state"] == "fixed"
    assert plans["ETHUSDT"] is None
    assert plans["LTCUSDT"] is None
    assert plans["XRPUSDT"] is None
    # 只有 BTCUSDT 触发 preview
    assert [p[2] for p in svc.previews] == [100.0]


def test_persist_preview_error_falls_to_pending(manager, svc, saved):
    """preview 抛 PlanPreviewError：该标的 pending，不炸启动链路"""
    svc.error = PlanPreviewError("REF_PRICE_REQUIRED", "缺参考价")

    manager._persist_worker_price_plan(1, "grid", {}, {"BTCUSDT": 100.0, "ETHUSDT": 2000.0})

    _, plans = saved[0]
    assert plans == {"BTCUSDT": None, "ETHUSDT": None}


def test_persist_no_price_plan_skips_db_write(manager, svc, saved):
    """非计划策略：早退不写库（避免无谓 config 写入）"""
    svc.supported = False

    manager._persist_worker_price_plan(1, "dual_ma", {}, {"BTCUSDT": None})

    assert saved == []
    assert svc.previews == []


def test_persist_empty_ref_prices_skips_db_write(manager, svc, saved):
    """ref_prices 为空：跳过写库（避免把旧固化清成 {"plans": {}}）"""
    manager._persist_worker_price_plan(1, "grid", {}, {})
    assert saved == []
