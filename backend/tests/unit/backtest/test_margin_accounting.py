"""保证金生效回显（杠杆 / 档位来源 / 强平统计）从引擎到详情接口的透传测试。

覆盖三段链路：
1. ``build_margin_specs`` 记录档位来源（DB / 快照 / 默认），供引擎原样回显；
2. ``format_axon_results`` / ``_format_results`` 把四个生效字段带到品种条目、
   account、portfolio，``build_portfolio_view`` 读取时仍然拿得到；
3. 旧结果 / 旧 wheel 缺字段时不抛异常，按 False / [] / 0 / 0 兜底。
"""

from unittest.mock import MagicMock

from backtest import margin_specs
from backtest.engine_service import EventDrivenBacktestService
from backtest.result_formatter_service import ResultFormatterService
from backtest.service import BacktestService

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
