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

    # ── invariant 5：成交派生指标必须按品种归因 ──
    # 回归背景：共享分支曾整体复制聚合结果（sym_result = dict(multi_result)），
    # 只切分成交，导致详情页「切换品种」时总收益率/总盈亏/交易次数各品种完全相同。
    def _metrics(sym: str) -> dict:
        return {m["key"]: m["value"] for m in by_symbol[sym]["metrics"]}

    for sym in SYMBOLS:
        entry = by_symbol[sym]
        metrics = _metrics(sym)
        # 总盈亏 == 该品种自身成交盈亏之和（引擎 realized_pnl 可加）；
        # metrics 里的 total_pnl 已四舍五入到 2 位小数，比较容差取 0.01
        expected_pnl = sum(float(t.get("pnl") or 0.0) for t in entry["trades"])
        assert metrics["total_pnl"] == pytest.approx(expected_pnl, abs=0.01), (
            f"{sym} 的总盈亏应为自身成交盈亏之和（归因口径），实际 {metrics['total_pnl']} vs {expected_pnl}"
        )
        assert metrics["total_trades"] > 0, f"{sym} 应有成交笔数"
        # 收益率基数 = 共享账户的一笔 init_cash（贡献可加口径，不按品种摊资金）
        assert metrics["total_return"] == pytest.approx(metrics["total_pnl"] / INIT_CASH * 100, abs=0.01), (
            f"{sym} 的收益率应按共享账户初始资金计算，实际 {metrics['total_return']}"
        )

    # 成交拆分无遗漏：各品种成交笔数之和 == 账户总成交笔数
    assert sum(_metrics(s)["total_trades"] for s in SYMBOLS) == portfolio_metrics["total_trades"], (
        "各品种成交笔数之和应等于账户总成交笔数"
    )

    pnls = {sym: _metrics(sym)["total_pnl"] for sym in SYMBOLS}
    returns = {sym: _metrics(sym)["total_return"] for sym in SYMBOLS}
    assert len({round(v, 6) for v in pnls.values()}) > 1, f"各品种总盈亏不应完全相同，实际 {pnls}"
    assert len({round(v, 6) for v in returns.values()}) > 1, f"各品种总收益率不应完全相同，实际 {returns}"

    # ── invariant 6：账户级字段（夏普/回撤）在品种条目里保留账户真值 ──
    # 回归背景：曾把这两项置 0 以避免"各品种看起来一样"；口径改为前端隐藏品种视角
    # 的账户级卡片后，数据层必须保留账户真值（导出/回放消费的是真数）
    for sym in SYMBOLS:
        metrics = _metrics(sym)
        assert metrics["sharpe_ratio"] == pytest.approx(portfolio_metrics["sharpe_ratio"]), (
            f"{sym} 的夏普应为共享账户真值，实际 {metrics['sharpe_ratio']}"
        )
        assert metrics["max_drawdown"] == pytest.approx(portfolio_metrics["max_drawdown"]), (
            f"{sym} 的最大回撤应为共享账户真值，实际 {metrics['max_drawdown']}"
        )


def test_shared_portfolio_trade_stats_match_concatenated_trades(monkeypatch) -> None:
    """组合（portfolio）视图的盈利/亏损/盈亏比，必须与「各品种成交拼接」重算一致。

    回归背景：``engine_service._format_results`` 组装 portfolio payload 时曾显式传 ``trades=[]``，而
    formatter 的 winning/losing/profit_factor 都是从 ``trades`` 现算的 → 组合恒出
    「盈利交易 0 / 亏损交易 = trade_count / 盈亏比 0.0」的假值。改为传入各品种
    round-trip 拼接后，组合统计与「全部」视图成交明细同源。
    """
    results, _ = _run_shared(monkeypatch, engine_config={})

    # 各品种 round-trip 拼接 = 组合视图的成交明细（与实现同源）
    concat_trades = [t for r in results["results_by_symbol"].values() for t in (r.get("trades") or [])]
    assert concat_trades, "夹具应产生非空 round-trip 成交"

    wins = [t for t in concat_trades if float(t.get("pnl") or 0.0) > 0]
    losses = [t for t in concat_trades if float(t.get("pnl") or 0.0) <= 0]
    assert wins and losses, "夹具应同时产生盈利与亏损 round-trip，供盈亏比重算"
    expected_pf = sum(float(t["pnl"]) for t in wins) / abs(sum(float(t["pnl"]) for t in losses))

    portfolio_metrics = {m["key"]: m["value"] for m in results["portfolio"]["metrics"]}

    # ── 组合统计 == 拼接后重算（formatter 会把盈亏比四舍五入到 4 位） ──
    assert portfolio_metrics["winning_trades"] == len(wins), (
        f"组合盈利交易应等于拼接后 pnl>0 条数，实际 {portfolio_metrics['winning_trades']} vs {len(wins)}"
    )
    assert portfolio_metrics["losing_trades"] == len(losses), (
        f"组合亏损交易应等于拼接后 pnl<=0 条数，实际 {portfolio_metrics['losing_trades']} vs {len(losses)}"
    )
    assert portfolio_metrics["profit_factor"] == pytest.approx(expected_pf, abs=1e-3), (
        f"组合盈亏比应等于拼接后 Σ盈/│Σ亏│，实际 {portfolio_metrics['profit_factor']} vs {expected_pf}"
    )

    # ── 不是旧假值形态：盈利交易恒 0、亏损交易退化成 fills（交易次数） ──
    assert portfolio_metrics["winning_trades"] > 0, "组合盈利交易不应退化成 0（空 trades 假值）"
    assert portfolio_metrics["losing_trades"] != portfolio_metrics["total_trades"], (
        "组合亏损交易不应退化成 fills 口径（旧假值 = trade_count - 0）"
    )


def test_shared_mode_capital_budget_scales_with_leverage(monkeypatch) -> None:
    """资金约束预算随 leverage 线性放大：capital_budget == init_cash × leverage。"""
    leverage = 3.0
    _, captured = _run_shared(monkeypatch, engine_config={"leverage": leverage})

    assert captured["capital_budget"] == pytest.approx(INIT_CASH * leverage), "预算 = init_cash × leverage"
    assert captured["capital_budget"] != pytest.approx(INIT_CASH), "leverage>1 时预算不得退化为 init_cash"
