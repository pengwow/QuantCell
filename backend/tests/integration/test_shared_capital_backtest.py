"""组合共享资金池回测端到端：真实路径（不 mock 引擎）跑一次多品种共享账户回测。

锁住本需求最容易回归的 4 条口径：
1. 共享模式组合初始权益 == **一笔** init_cash（不是 init_cash × 品种数；独立模式才 ×N）
2. 每个品种**各有一个独立策略实例**（滚动状态按品种隔离，不复用同一实例）
3. ``capital_budget == init_cash × leverage``（默认 leverage=1.0 → 等于 init_cash）
4. 成交按 ``TradeRecord.instrument`` 正确拆分回各品种（不跨品种串号）

数据来源为**仓库内合成 fixture + 最小 provider**，与
``tests/unit/backtest/test_rust_runner_parity.py`` 的 ``_StubProvider`` 同一模式，
不依赖 ``data/source`` 本地下载数据，也不 mock 引擎，故会真实驱动 Rust ``run_multi``。
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from backtest.engine_service import EventDrivenBacktestService

INIT_CASH = 12_345.0
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAME = "1h"


class _StubProvider:
    """最小 provider：返回 {key: DataFrame}，供 run_backtest 多品种分支消费。

    契约与既有 engine_service 测试一致（load_multiple 返回 (dict, None)）。
    """

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        self._data = data

    def load_multiple(self, **_kwargs):
        return {k: v.copy() for k, v in self._data.items()}, None

    def load_funding_rate(self, symbol, start=None, end=None):
        return None


def _zigzag(offset: float = 0.0, n: int = 200) -> pd.DataFrame:
    """正弦震荡行情：价格反复穿越均线 → dual_ma 反复换仓，两品种都产生 round-trip。

    offset 用于给两个品种不同的价格水平，验证成交确实按品种归属（而非共用一条曲线）。
    """
    dates = pd.date_range("2024-07-01", periods=n, freq="1h")
    closes = [100.0 + offset + 20.0 * math.sin(i / 5.0) for i in range(n)]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        },
        index=dates,
    )


def _run_shared(monkeypatch, engine_config: dict) -> tuple[dict, dict]:
    """跑一次共享模式回测，返回 (格式化结果, 真实 _run_rust_multi 调用参数)。

    spy 只记录参数、仍调用真实实现，所以引擎是真跑的（不 mock 撮合）。
    """
    captured: dict = {}
    orig = EventDrivenBacktestService._run_rust_multi

    def spy(self, **kwargs):
        captured.update(kwargs)
        return orig(self, **kwargs)

    monkeypatch.setattr(EventDrivenBacktestService, "_run_rust_multi", spy)

    svc = EventDrivenBacktestService(
        data_provider=_StubProvider(
            {
                "BTCUSDT_1h": _zigzag(0.0),
                "ETHUSDT_1h": _zigzag(5.0),
            }
        )
    )
    results = svc.run_backtest(
        strategy_name="dual_ma",
        strategy_params={},
        symbols=SYMBOLS,
        timeframes=[TIMEFRAME],
        engine_config={"capital_mode": "shared", "initial_cash": INIT_CASH, "force_liquidate": True, **engine_config},
    )
    return results, captured


def test_shared_capital_pool_end_to_end(monkeypatch) -> None:
    """真实共享回测：单账户初始权益、按品种策略实例、成交拆分四口径一次锁死。"""
    results, captured = _run_shared(monkeypatch, engine_config={})
    n = len(SYMBOLS)

    # ── invariant 1：组合初始权益 == 一笔 init_cash（不是 × 品种数） ──
    portfolio_metrics = {m["key"]: m["value"] for m in results["portfolio"]["metrics"]}
    assert portfolio_metrics["initial_equity"] == pytest.approx(INIT_CASH), (
        f"共享账户初始权益应为一笔 {INIT_CASH}，实际 {portfolio_metrics['initial_equity']}"
    )
    assert portfolio_metrics["initial_equity"] != pytest.approx(INIT_CASH * n), "共享模式不得按品种数重复计初始资金"
    assert results["capital_mode"] == "shared"

    # ── invariant 2：每个品种各有一个独立策略实例（滚动状态不跨品种污染） ──
    strategies = captured["strategies_by_symbol"]
    assert set(strategies) == set(SYMBOLS)
    assert len(strategies) == n
    assert len({id(s) for s in strategies.values()}) == n, "同一策略实例被复用会污染跨品种滚动状态"

    # ── invariant 3：capital_budget == init_cash × leverage（默认 leverage=1.0） ──
    assert captured["init_cash"] == pytest.approx(INIT_CASH)
    assert captured["capital_budget"] == pytest.approx(INIT_CASH), "默认 leverage=1.0 → 预算应等于 init_cash"

    # ── invariant 4：成交按 instrument 拆分回各品种，无跨品种串号 ──
    by_symbol = results["results_by_symbol"]
    assert set(by_symbol) == set(SYMBOLS)
    for sym in SYMBOLS:
        trades = by_symbol[sym]["trades"]
        assert trades, f"{sym} 应有 round-trip 成交（正弦震荡 + force_liquidate），为空说明成交归属有误"
        assert all(t["symbol"] == sym for t in trades), f"{sym} 的成交列表里混入了其他品种（instrument 拆分错误）"


def test_shared_mode_capital_budget_scales_with_leverage(monkeypatch) -> None:
    """资金约束预算随 leverage 线性放大：capital_budget == init_cash × leverage。"""
    leverage = 3.0
    _, captured = _run_shared(monkeypatch, engine_config={"leverage": leverage})

    assert captured["capital_budget"] == pytest.approx(INIT_CASH * leverage), "预算 = init_cash × leverage"
    assert captured["capital_budget"] != pytest.approx(INIT_CASH), "leverage>1 时预算不得退化为 init_cash"
