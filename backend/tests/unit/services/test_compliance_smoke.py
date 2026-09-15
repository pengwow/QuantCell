"""P2:compliance 合规审计冒烟测试。

覆盖评估报告 O 区「compliance 审计:交易记录字段、事件类型」缺口:
- record_trade 记录交易(必填字段缺失 → KeyError)
- query_trades 按条件过滤,返回记录含完整 20 字段
- get_trade_stats 时间窗统计
- generate_daily_report 日报字段
- verify_audit_integrity 审计链完整性
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from axon_quant.compliance import AuditEventType, ComplianceConfig, ComplianceModule


@pytest.fixture()
def compliance_module(tmp_path: Path) -> ComplianceModule:
    """含 3 笔交易的合规模块(2 笔 strat-0,1 笔 strat-1)。"""
    cfg = ComplianceConfig(
        account_id="acc-001",
        base_currency="USDT",
        large_trade_threshold=100_000.0,
        position_limit=1_000_000.0,
        max_portfolio_concentration=0.4,
        data_retention_years=7,
        regulators=["SEC"],
    )
    module = ComplianceModule(cfg, str(tmp_path / "audit.db"))
    for i in range(3):
        module.record_trade(
            {
                "strategy_id": f"strat-{i % 2}",
                "symbol": "BTC/USDT",
                "side": "buy" if i % 2 == 0 else "sell",
                "quantity": 0.5 + i,
                "price": 100.0 + i,
                "fee": 0.01,
                "fee_currency": "USDT",
                "exchange": "binance",
            }
        )
    return module


def test_record_trade_count_and_missing_field(compliance_module: ComplianceModule) -> None:
    """record_trade:成功计数;缺必填字段抛 KeyError。"""
    assert compliance_module.trade_count == 3
    with pytest.raises(KeyError):
        compliance_module.record_trade(
            {"strategy_id": "s", "symbol": "BTC/USDT"}  # 缺 side/quantity/price 等
        )


def test_query_trades_filter_by_strategy(compliance_module: ComplianceModule) -> None:
    """query_trades 按策略过滤,记录含完整字段集。"""
    trades = compliance_module.query_trades({"strategy_id": "strat-0"})
    assert len(trades) == 2

    expected_fields = {
        "trade_id",
        "order_id",
        "strategy_id",
        "symbol",
        "side",
        "quantity",
        "price",
        "fee",
        "fee_currency",
        "exchange",
        "status",
        "notional_value",
        "execution_time",
        "created_at",
        "order_type",
        "liquidity",
        "realized_pnl",
        "settlement_time",
        "slippage",
        "exchange_trade_id",
    }
    assert expected_fields.issubset(set(trades[0].keys()))
    assert all(t["strategy_id"] == "strat-0" for t in trades)


def test_trade_stats_window(compliance_module: ComplianceModule) -> None:
    """get_trade_stats:时间窗覆盖全部记录,统计量与记账一致。"""
    now = datetime.datetime.now(datetime.UTC)
    start = (now - datetime.timedelta(days=1)).isoformat()
    end = (now + datetime.timedelta(days=1)).isoformat()

    stats = compliance_module.get_trade_stats(start, end)
    assert stats["total_trades"] == 3
    # 3 笔手续费 0.01
    assert stats["total_fees"] == pytest.approx(0.03)
    assert stats["total_volume"] > 0


def test_daily_report_fields(compliance_module: ComplianceModule) -> None:
    """generate_daily_report:日报字段完整,余额守恒(start - fees = end)。"""
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    report = compliance_module.generate_daily_report(today, 100_000.0)

    assert report["date"] == today
    assert report["account_id"] == "acc-001"
    assert report["total_trades"] == 3
    assert report["total_fees"] == pytest.approx(0.03)
    # 无持仓无盈亏时:期末 = 期初 - 费用
    assert report["ending_balance"] == pytest.approx(100_000.0 - 0.03)


def test_audit_integrity_and_event_types(compliance_module: ComplianceModule) -> None:
    """审计链完整性校验通过;AuditEventType 枚举含交易生命周期事件。"""
    assert compliance_module.verify_audit_integrity() is True
    # 每笔 trade 记录对应一个 TradeExecuted 审计事件
    assert compliance_module.audit_event_count >= 3

    required_events = {"TradeExecuted", "OrderPlaced", "OrderCancelled", "PositionOpened"}
    assert required_events.issubset({e for e in dir(AuditEventType) if not e.startswith("_")})
