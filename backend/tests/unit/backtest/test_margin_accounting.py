"""保证金生效回显（杠杆 / 档位来源 / 强平统计）从引擎到详情接口的透传测试。

覆盖四段链路：
1. ``build_margin_specs`` 记录档位来源（DB / 快照 / 默认），供引擎原样回显；
2. ``format_axon_results`` / ``_format_results`` 把四个生效字段带到品种条目、
   account、portfolio，``build_portfolio_view`` 读取时仍然拿得到；
3. 旧结果 / 旧 wheel 缺字段时不抛异常，按 False / [] / 0 / 0 兜底；
4. 受控行情下的保证金账务行为：杠杆放大敞口、缓跌不强平、急跌强平且 NAV 不为负。
"""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from axon_bridge import Action
from backtest import margin_specs
from backtest.engine_service import EventDrivenBacktestService
from backtest.result_formatter_service import ResultFormatterService
from backtest.service import BacktestService
from strategy.base import BaseStrategy, StrategyConfig

EFFECTIVE_SPEC = {
    "symbol": "BTC/USDT",
    "leverage": 20.0,
    "margin_mode": "cross",
    "bracket_source": "default",
}
EVENT_BTC = {
    "timestamp_ns": 1_700_000_000_000_000_000,
    "symbol": "BTC/USDT",
    "margin_mode": "cross",
    "tier_from": 0,
    "tier_to": 0,
    "reduced_qty": 0.5,
    "price": 100.0,
    "fee": 0.05,
    "reason": "partial",
    "price_basis": "close",
}


def _brackets(mmr: float = 0.004, max_leverage: float = 125.0) -> list[dict]:
    return [
        {
            "notional_floor": 0.0,
            "notional_cap": None,
            "mmr": mmr,
            "cum": 0.0,
            "liquidation_fee_rate": 0.001,
            "max_leverage": max_leverage,
        }
    ]


def _raw_results(**extra) -> dict:
    """与 _convert_backtest_result 同构的最小原始结果（含生效回显字段）。"""
    return {
        "initial_capital": 10_000.0,
        "final_nav": 10_100.0,
        "total_pnl": 100.0,
        "trades": [],
        "equity_curve": [],
        "liquidation_events": [EVENT_BTC],
        "insurance_fund_loss": 5.0,
        "price_basis": "close",
        "margin_applied": True,
        "margin_specs_effective": [EFFECTIVE_SPEC],
        "liquidation_count": 1,
        "margin_shortfall_count": 3,
        **extra,
    }


def test_build_margin_specs_records_bracket_source(monkeypatch):
    """三级回退每一级都要如实记录来源，引擎回显后才能区分档位可信度。"""
    db_brackets = _brackets(mmr=0.004)
    snap_brackets = _brackets(mmr=0.006)

    monkeypatch.setattr(margin_specs, "_load_from_db", lambda symbol: db_brackets)
    monkeypatch.setattr(margin_specs, "_load_from_snapshot", lambda symbol: snap_brackets)
    assert margin_specs.build_margin_specs([("BTCUSDT", 5.0, "cross")])["BTC/USDT"]["bracket_source"] == "db"

    monkeypatch.setattr(margin_specs, "_load_from_db", lambda symbol: None)
    assert margin_specs.build_margin_specs([("BTCUSDT", 5.0, "cross")])["BTC/USDT"]["bracket_source"] == "snapshot"

    monkeypatch.setattr(margin_specs, "_load_from_snapshot", lambda symbol: None)
    assert margin_specs.build_margin_specs([("BTCUSDT", 5.0, "cross")])["BTC/USDT"]["bracket_source"] == "default"


def test_formatter_passes_effective_specs_and_counts():
    """单品种格式化与多品种组合视图都必须带全四个生效字段。"""
    # 单品种：品种条目 / account / portfolio 三处
    single = ResultFormatterService.format_axon_results(
        results=_raw_results(),
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )
    for section in ("BTCUSDT_1h", "account", "portfolio"):
        assert single[section]["margin_applied"] is True
        assert single[section]["margin_specs_effective"] == [EFFECTIVE_SPEC]
        assert single[section]["liquidation_count"] == 1
        assert single[section]["margin_shortfall_count"] == 3

    # 多品种：共享账户下每个品种条目复制全账户事件，计数按过滤后的本品种事件重算
    svc = EventDrivenBacktestService(data_provider=MagicMock())
    formatted = svc._format_results(
        results=_raw_results(),
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframe="1h",
        strategy_name="dual_ma",
        per_symbol_results={
            "BTCUSDT": {**_raw_results(), "fills": 0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0},
            "ETHUSDT": {**_raw_results(), "fills": 0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0},
        },
        capital_mode="shared",
    )
    assert formatted["results_by_symbol"]["BTCUSDT"]["margin_specs_effective"] == [EFFECTIVE_SPEC]
    assert formatted["results_by_symbol"]["BTCUSDT"]["liquidation_count"] == 1
    assert formatted["account"]["margin_applied"] is True
    assert formatted["account"]["margin_shortfall_count"] == 3
    assert formatted["portfolio"]["margin_specs_effective"] == [EFFECTIVE_SPEC]

    # 详情接口读取侧：组合视图必须原样取到这些字段
    view = BacktestService.build_portfolio_view(formatted)
    assert view["margin_applied"] is True
    assert view["margin_specs_effective"] == [EFFECTIVE_SPEC]
    assert view["liquidation_count"] == 1
    assert view["margin_shortfall_count"] == 3


def test_legacy_results_have_margin_defaults():
    """旧结果 JSON / 旧 wheel 没有生效字段：兜底 False / [] / 0 / 0 且不抛异常。"""
    legacy = {
        "initial_capital": 10_000.0,
        "final_nav": 10_000.0,
        "trades": [],
        "equity_curve": [],
    }
    single = ResultFormatterService.format_axon_results(
        results=legacy,
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )
    for section in ("BTCUSDT_1h", "account", "portfolio"):
        assert single[section]["margin_applied"] is False
        assert single[section]["margin_specs_effective"] == []
        assert single[section]["liquidation_count"] == 0
        assert single[section]["margin_shortfall_count"] == 0

    svc = EventDrivenBacktestService(data_provider=MagicMock())
    formatted = svc._format_results(
        results={"total_pnl": 0.0, "fills": 0, "equity_curve": []},
        symbols=["BTCUSDT"],
        timeframe="1h",
        strategy_name="dual_ma",
        per_symbol_results={"BTCUSDT": {"total_pnl": 0.0, "fills": 0}},
        capital_mode="per_symbol",
    )
    assert formatted["portfolio"]["margin_applied"] is False
    assert formatted["portfolio"]["margin_specs_effective"] == []
    assert formatted["portfolio"]["liquidation_count"] == 0
    assert formatted["portfolio"]["margin_shortfall_count"] == 0

    view = BacktestService.build_portfolio_view({"portfolio": {}, "results_by_symbol": {}})
    assert view["margin_applied"] is False
    assert view["margin_specs_effective"] == []
    assert view["liquidation_count"] == 0
    assert view["margin_shortfall_count"] == 0


# ─────────────────────────── 受控行情回归 ───────────────────────────
# 固定行情 + 恒定 0.5 仓位的 Buy 策略，走 QuantCell 的 Rust 单品种编排入口，
# 验证杠杆确实放大敞口、缓跌不强平、急跌强平且 NAV 不为负。行情可复现，
# 断言只依赖确定性数值，不依赖随机种子。

# 恒定目标仓位 0.5（权益占比）：适配器按 leverage 换算成绝对数量，
# 20x 时的名义约为初始权益的 10 倍，因此小幅下跌不会触发强平。
TARGET_POSITION = 0.5


class _FixedHalfBuy(BaseStrategy):
    """恒定买入策略：每根 bar 都回到 0.5 权益占比的目标仓位。"""

    def __init__(self) -> None:
        super().__init__(StrategyConfig(name="fixed_half_buy", symbol="BTCUSDT"))

    def on_bar(self, bar, ctx):
        # Action 的 target_position 是 pyo3 f32 字段，断言侧用 approx 处理精度
        return Action(
            action_type="buy",
            confidence=1.0,
            target_position=TARGET_POSITION,
            model_id="fixed_half_buy",
            inference_time_us=0,
        )


def _controlled_kline(n: int, start: float, step: float) -> pd.DataFrame:
    """线性行情：close = start + i * step，15m 周期，共 n 根。"""
    closes = np.linspace(start, start + step * (n - 1), n)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 0.05,
            "low": closes - 0.05,
            "close": closes,
            "volume": np.full(n, 1000.0),
        },
        index=pd.date_range("2024-01-01", periods=n, freq="15min"),
    )


def _margin_spec(leverage: float) -> dict:
    """单品种 1 档保证金规格（mmr 0.5%、强平费 0.1%、最高 125x）。"""
    return {
        "BTC/USDT": {
            "leverage": float(leverage),
            "mode": "cross",
            "bracket_source": "default",
            "brackets": [
                {
                    "notional_floor": 0.0,
                    "notional_cap": None,
                    "mmr": 0.005,
                    "cum": 0.0,
                    "liquidation_fee_rate": 0.001,
                    "max_leverage": 125.0,
                }
            ],
        }
    }


def _run(df: pd.DataFrame, leverage: float | None, initial_cash: float = 1000.0):
    """跑一次 Rust 单品种回测；leverage=None 表示不启用保证金模拟。"""
    svc = EventDrivenBacktestService(data_provider=None)  # _run_rust_single 不使用 provider
    return svc._run_rust_single(
        _FixedHalfBuy(),
        df,
        "BTCUSDT",
        initial_cash,
        futures=True,
        margin_specs=_margin_spec(leverage) if leverage is not None else None,
    )


def test_20x_slow_decline_does_not_liquidate():
    """20x + 1.2% 缓跌：维持保证金远低于 NAV，不应产生任何强平事件。"""
    # 100 → 98.8（120 根 15m，step -0.01）
    df = _controlled_kline(120, start=100.0, step=-0.01)
    result = _run(df, leverage=20.0)

    assert result.margin_applied is True
    assert result.liquidation_events == []
    assert result.liquidation_count == 0
    assert result.final_nav > 0


def test_1x_margin_off_matches_margin_on():
    """1x 时启用保证金与不启用：撮合与盈亏口径完全一致（保证金只做账务，不改撮合）。"""
    df = _controlled_kline(120, start=100.0, step=-0.01)
    off = _run(df, leverage=None)
    on = _run(df, leverage=1.0)

    assert on.margin_applied is True
    assert off.margin_applied is False
    assert on.fills == off.fills
    assert on.total_pnl == pytest.approx(off.total_pnl, rel=1e-9, abs=1e-9)


def test_20x_amplifies_pnl_vs_1x():
    """同一行情下 20x 的名义敞口约为 1x 的 20 倍，亏损应明显放大而不只是挂了个标签。

    注意：成交笔数不能直接对齐 —— 引擎的 rebalance 阈值是 0.001（见 axon-worker
    `REBALANCE_THRESHOLD`），1x 时逐 bar 目标增量约 0.0005，会隔 bar 才触发一次；
    20x 时增量约 0.01，每 bar 都触发。这是撮合层的既有行为，不影响盈亏放大结论。
    """
    df = _controlled_kline(120, start=100.0, step=-0.01)
    one = _run(df, leverage=1.0)
    twenty = _run(df, leverage=20.0)

    # 恒定名义仓位下 PnL 与杠杆近似线性；取 10 倍作下界，远超 f32 换算噪声
    assert abs(twenty.total_pnl) > abs(one.total_pnl) * 10


def test_steep_decline_liquidates_and_keeps_nav_non_negative():
    """急跌（100 → 20，step -0.5）：触发强平，且穿仓缺口由保险基金兜底后 NAV >= 0。"""
    # 100 → 20 需 161 根（step -0.5），保证终点落在 20
    df = _controlled_kline(161, start=100.0, step=-0.5)
    result = _run(df, leverage=20.0)

    assert result.margin_applied is True
    assert result.liquidation_count > 0
    assert result.liquidation_count == len(result.liquidation_events)
    assert result.final_nav >= 0
