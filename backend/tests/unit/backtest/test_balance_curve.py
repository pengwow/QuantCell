"""回测权益曲线 balance（存款）字段的映射层单测。

引擎产出的 bar_balance_curve 是 MT4 口径的 balance = cash + Σ(qty × avg_cost)，
映射层必须把它逐点写进 equity_curve 的 balance 字段，供前端画存款曲线、
后端反推浮盈（equity - balance）。
"""

from types import SimpleNamespace

from backtest.engine_service import EventDrivenBacktestService

_TS_A = 1_700_000_000_000_000_000  # 纳秒
_TS_B = 1_700_000_060_000_000_000


def _rust_result(**overrides) -> SimpleNamespace:
    """最小 Rust BacktestResult 替身：只提供 _map_rust_result 读取的字段。"""
    base = dict(
        max_drawdown_pct=0.0,
        nav_peak=10_000.0,
        bar_nav_curve=[(_TS_A, 10_000.0), (_TS_B, 10_050.0)],
        bar_balance_curve=[(_TS_A, 10_000.0), (_TS_B, 10_000.0)],
        trades=[],
        total_pnl=50.0,
        orders_accepted=0,
        orders_rejected=0,
        fills=0,
        final_nav=10_050.0,
        events_processed=0,
        duration_secs=0.0,
        total_fees=0.0,
        win_rate=0.0,
        sharpe_ratio=0.0,
        final_positions={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_map_rust_result_writes_balance_per_point():
    """每个权益点都带 balance，且与 bar_nav_curve 逐帧对齐。"""
    record = EventDrivenBacktestService._map_rust_result(_rust_result(), None, "BTCUSDT", data_range=(_TS_A, _TS_B))

    curve = record.equity_curve
    assert len(curve) == 2, f"应产出 2 个权益点，got {len(curve)}"
    assert [p["balance"] for p in curve] == [10_000.0, 10_000.0]
    # 第 2 点净值 10_050 高于存款 10_000 → 浮盈 50
    assert curve[1]["equity"] - curve[1]["balance"] == 50.0


def test_map_rust_result_tolerates_missing_balance_curve():
    """旧 wheel 无 bar_balance_curve 属性时不报错，balance 退化为 0。"""
    rust = _rust_result()
    del rust.bar_balance_curve

    record = EventDrivenBacktestService._map_rust_result(rust, None, "BTCUSDT", data_range=(_TS_A, _TS_B))

    assert all(p["balance"] == 0.0 for p in record.equity_curve), "缺失时 balance 应为 0"


def test_merge_equity_curves_sums_balance_across_symbols():
    """独立资金池合并时 balance 逐品种求和（组合视角存款 = 各品种存款之和）。"""
    from backtest.service import BacktestService

    curve_a = [
        {"timestamp": 1000, "equity": 10_000.0, "balance": 10_000.0, "margin": 0.0},
        {"timestamp": 2000, "equity": 10_100.0, "balance": 10_050.0, "margin": 0.0},
    ]
    curve_b = [
        {"timestamp": 1000, "equity": 20_000.0, "balance": 20_000.0, "margin": 0.0},
        {"timestamp": 2000, "equity": 19_900.0, "balance": 19_950.0, "margin": 0.0},
    ]

    merged = BacktestService._merge_equity_curves([curve_a, curve_b])

    assert [p["balance"] for p in merged] == [30_000.0, 30_000.0], "balance 应逐品种求和"
    assert [p["equity"] for p in merged] == [30_000.0, 30_000.0]
