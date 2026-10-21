"""强平事件 / 穿仓损失从引擎结果透传到详情结果的回归测试。

链路缺口：_map_rust_result 已产出这些字段，但 format_axon_results 只挑选固定
字段重组，导致详情接口拿不到强平记录。这里锁定「格式化层必须透传 + 旧结果兜底」。
"""

import json
from unittest.mock import MagicMock

from backtest.engine_service import EventDrivenBacktestService
from backtest.result_formatter_service import ResultFormatterService

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
EVENT_ETH = {
    "timestamp_ns": 1_700_000_060_000_000_000,
    "symbol": "ETH/USDT",
    "margin_mode": "isolated",
    "tier_from": 1,
    "tier_to": 0,
    "reduced_qty": 1.0,
    "price": 200.0,
    "fee": 0.1,
    "reason": "depleted",
    "price_basis": "close",
}
EFFECTIVE_SPEC = {
    "symbol": "BTC/USDT",
    "leverage": 20.0,
    "margin_mode": "cross",
    "bracket_source": "default",
}


def _raw_results(events: list[dict], *, insurance_fund_loss: float = 12.5, **extra) -> dict:
    """与 _convert_backtest_result 同构的最小原始结果。"""
    return {
        "initial_capital": 10_000.0,
        "final_nav": 10_100.0,
        "total_pnl": 100.0,
        "trades": [],
        "equity_curve": [],
        "liquidation_events": events,
        "insurance_fund_loss": insurance_fund_loss,
        "price_basis": "close",
        "margin_applied": True,
        "margin_specs_effective": [EFFECTIVE_SPEC],
        "liquidation_count": len(events),
        "margin_shortfall_count": 2,
        **extra,
    }


def test_format_axon_results_passes_liquidation_fields():
    """单品种格式化：品种条目 / account / portfolio 都带保证金字段。"""
    formatted = ResultFormatterService.format_axon_results(
        results=_raw_results([EVENT_BTC]),
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )

    entry = formatted["BTCUSDT_1h"]
    assert entry["liquidation_events"] == [EVENT_BTC]
    assert entry["insurance_fund_loss"] == 12.5
    assert entry["price_basis"] == "close"
    assert entry["margin_applied"] is True
    assert entry["margin_specs_effective"] == [EFFECTIVE_SPEC]
    assert entry["liquidation_count"] == 1
    assert entry["margin_shortfall_count"] == 2

    for section in ("account", "portfolio"):
        assert formatted[section]["liquidation_events"] == [EVENT_BTC]
        assert formatted[section]["insurance_fund_loss"] == 12.5
        assert formatted[section]["price_basis"] == "close"
        assert formatted[section]["margin_applied"] is True
        assert formatted[section]["margin_specs_effective"] == [EFFECTIVE_SPEC]
        assert formatted[section]["liquidation_count"] == 1
        assert formatted[section]["margin_shortfall_count"] == 2

    # 结果 JSON 要落盘，时间戳必须是 int 且整体可序列化
    dumped = json.loads(json.dumps(formatted))
    assert dumped["BTCUSDT_1h"]["liquidation_events"][0]["timestamp_ns"] == EVENT_BTC["timestamp_ns"]


def test_format_axon_results_defaults_for_legacy_results():
    """旧结果没有这些字段：兜底 [] / 0.0 / "close" / False / 0，且不抛异常。"""
    formatted = ResultFormatterService.format_axon_results(
        results={"initial_capital": 10_000.0, "final_nav": 10_000.0, "trades": [], "equity_curve": []},
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )

    entry = formatted["BTCUSDT_1h"]
    assert entry["liquidation_events"] == []
    assert entry["insurance_fund_loss"] == 0.0
    assert entry["price_basis"] == "close"
    assert entry["margin_applied"] is False
    assert entry["margin_specs_effective"] == []
    assert entry["liquidation_count"] == 0
    assert entry["margin_shortfall_count"] == 0
    assert formatted["portfolio"]["liquidation_events"] == []
    json.dumps(formatted)


def _shared_per_symbol(events: list[dict]) -> dict[str, dict]:
    """共享账户：每个品种条目都复制了全账户结果（事件是全量）。"""
    return {
        symbol: {
            **_raw_results(events),
            "symbol": symbol,
            "fills": 0,
            "max_drawdown_pct": 0.0,
            "sharpe_ratio": 0.0,
        }
        for symbol in ("BTCUSDT", "ETHUSDT")
    }


def test_format_results_filters_events_per_symbol_in_shared_mode():
    """共享资金池：品种条目只含本品种事件，组合/账户视图保留全量。"""
    svc = EventDrivenBacktestService(data_provider=MagicMock())
    events = [EVENT_BTC, EVENT_ETH]

    formatted = svc._format_results(
        results={
            **_raw_results(events, final_nav=10_200.0, total_pnl=200.0),
            "equity_curve": [],
        },
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframe="1h",
        strategy_name="dual_ma",
        per_symbol_results=_shared_per_symbol(events),
        capital_mode="shared",
    )

    assert formatted["results_by_symbol"]["BTCUSDT"]["liquidation_events"] == [EVENT_BTC]
    assert formatted["results_by_symbol"]["ETHUSDT"]["liquidation_events"] == [EVENT_ETH]
    # 品种条目的强平计数按过滤后的本品种事件重算，不是账户总数
    assert formatted["results_by_symbol"]["BTCUSDT"]["liquidation_count"] == 1
    assert formatted["results_by_symbol"]["ETHUSDT"]["liquidation_count"] == 1
    assert formatted["portfolio"]["liquidation_events"] == events
    assert formatted["portfolio"]["insurance_fund_loss"] == 12.5
    assert formatted["portfolio"]["price_basis"] == "close"
    assert formatted["portfolio"]["margin_applied"] is True
    assert formatted["portfolio"]["margin_specs_effective"] == [EFFECTIVE_SPEC]
    assert formatted["portfolio"]["liquidation_count"] == 2
    assert formatted["portfolio"]["margin_shortfall_count"] == 2
    assert formatted["account"]["liquidation_events"] == events


def test_format_results_collects_events_for_independent_pools():
    """独立资金池：聚合 dict 不含列表字段，组合视图需从各品种结果拼接全量事件。"""
    svc = EventDrivenBacktestService(data_provider=MagicMock())
    per_symbol = {
        "BTCUSDT": {
            **_raw_results([EVENT_BTC], insurance_fund_loss=1.0),
            "initial_capital": 10_000.0,
            "final_nav": 10_050.0,
            "total_pnl": 50.0,
        },
        "ETHUSDT": {
            **_raw_results([EVENT_ETH], insurance_fund_loss=2.0),
            "initial_capital": 10_000.0,
            "final_nav": 10_050.0,
            "total_pnl": 50.0,
        },
    }

    formatted = svc._format_results(
        # 独立模式聚合结果只有标量，没有 liquidation_events
        results={"total_pnl": 100.0, "fills": 0, "equity_curve": []},
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframe="1h",
        strategy_name="dual_ma",
        per_symbol_results=per_symbol,
        capital_mode="per_symbol",
    )

    assert formatted["results_by_symbol"]["BTCUSDT"]["liquidation_events"] == [EVENT_BTC]
    assert formatted["results_by_symbol"]["ETHUSDT"]["liquidation_events"] == [EVENT_ETH]
    assert formatted["portfolio"]["liquidation_events"] == [EVENT_BTC, EVENT_ETH]
    # 各独立资金池的穿仓损失相加即组合总损失
    assert formatted["portfolio"]["insurance_fund_loss"] == 3.0


def test_format_results_legacy_input_uses_defaults():
    """旧多品种结果：没有保证金字段时组合/品种视图均为空值兜底。"""
    svc = EventDrivenBacktestService(data_provider=MagicMock())
    formatted = svc._format_results(
        results={"total_pnl": 0.0, "fills": 0, "equity_curve": []},
        symbols=["BTCUSDT"],
        timeframe="1h",
        strategy_name="dual_ma",
        per_symbol_results={"BTCUSDT": {"total_pnl": 0.0, "fills": 0}},
        capital_mode="per_symbol",
    )

    assert formatted["results_by_symbol"]["BTCUSDT"]["liquidation_events"] == []
    assert formatted["portfolio"]["liquidation_events"] == []
    assert formatted["portfolio"]["insurance_fund_loss"] == 0.0
    assert formatted["portfolio"]["price_basis"] == "close"
    assert formatted["portfolio"]["margin_applied"] is False
    assert formatted["portfolio"]["margin_specs_effective"] == []
    assert formatted["portfolio"]["liquidation_count"] == 0
    assert formatted["portfolio"]["margin_shortfall_count"] == 0
