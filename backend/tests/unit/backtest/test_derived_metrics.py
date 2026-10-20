"""派生指标纯函数单测：用最小手工样例锁定公式与退化输入行为。"""

from __future__ import annotations

import pytest

from backtest import derived_metrics as dm

# 时间基准（纳秒）：1 天 = 86400s
DAY_NS = 86_400 * 10**9

# 3 个点的小曲线：100 → 110 → 99（峰值 110，回撤 10%）
CURVE = [
    {"equity": 100.0, "timestamp": 0},
    {"equity": 110.0, "timestamp": 60_000},
    {"equity": 99.0, "timestamp": 120_000},
]


def test_periods_per_year_matches_factor_service():
    """年化因子表必须与 factor.service 的口径一致（避免两处漂移）。"""
    from factor.service import FactorService

    for interval in ("1m", "5m", "15m", "1h", "4h", "1d"):
        assert dm.periods_per_year(interval) == FactorService._periods_per_year(interval), interval


def test_avg_drawdown_pct():
    # 逐点回撤 = [0%（首点基准）, 0%（刷新峰值 110）, 10%（110→99）]，均值 = 10% / 3 ≈ 3.3333%
    assert dm.avg_drawdown_pct(CURVE) == pytest.approx(3.3333, abs=1e-3)


def test_avg_drawdown_pct_degenerate():
    assert dm.avg_drawdown_pct([]) == 0.0
    assert dm.avg_drawdown_pct([{"equity": 100.0}]) == 0.0


def test_annualized_volatility_pct():
    # 60s/bar → periods_per_year = 365*24*60 = 525600
    vol = dm.annualized_volatility_pct(CURVE, 525_600)
    assert vol > 0
    assert dm.annualized_volatility_pct(CURVE, 0) == 0.0
    assert dm.annualized_volatility_pct([], 8760) == 0.0


def test_sqn_and_kelly():
    trades = [
        {"pnl": 10.0, "return_pct": 1.0},
        {"pnl": -5.0, "return_pct": -0.5},
        {"pnl": 20.0, "return_pct": 2.0},
    ]
    # N=3，收益率 [1.0, -0.5, 2.0]：mean=0.8333%、样本标准差≈1.2583
    # → sqrt(3)*mean/std ≈ 1.1471（计划里原写 1.3871 系误把样本标准差当作 1.0408）
    assert dm.sqn(trades) == pytest.approx(1.1471, abs=1e-3)
    # W = 2/3，R = 15/5 = 3 → f = 0.6667 − 0.3333/3 = 0.5556
    assert dm.kelly_fraction(trades) == pytest.approx(0.5556, abs=1e-3)


def test_sqn_kelly_degenerate():
    assert dm.sqn([]) == 0.0
    assert dm.sqn([{"return_pct": 1.0}]) == 0.0
    # 无亏损笔 → 不外推（返回 0）
    assert dm.kelly_fraction([{"pnl": 1.0}, {"pnl": 2.0}]) == 0.0
    # 全亏 → 返回 0（建议仓位不为负）
    assert dm.kelly_fraction([{"pnl": -1.0}, {"pnl": -2.0}]) == 0.0


def test_exposure_time_pct_merges_overlapping_spans():
    """重叠区间合并后计时，不重复累计。"""
    trades = [
        {"timestamp": 0, "exit_timestamp": 3600 * 4},  # 0h → 4h
        {"timestamp": 3600 * 3, "exit_timestamp": 3600 * 6},  # 3h → 6h（与上面重叠 1h）
    ]
    # 并集 6h / 窗口 12h = 50%
    assert dm.exposure_time_pct(trades, 0, 12 * 3600 * 10**9) == pytest.approx(50.0, abs=1e-3)


def test_duration_days_and_trade_durations():
    assert dm.duration_days(0, 3.5 * DAY_NS) == 3
    assert dm.duration_days(DAY_NS, 0) == 0
    avg_h, max_h = dm.trade_duration_hours(
        [
            {"timestamp": 0, "exit_timestamp": 3600},
            {"timestamp": 0, "exit_timestamp": 3600 * 3},
        ]
    )
    assert avg_h == pytest.approx(2.0)
    assert max_h == pytest.approx(3.0)


def test_annualized_return_pct():
    # 一年整、总收益 10% → 年化 10%
    assert dm.annualized_return_pct(10.0, 0, 365 * DAY_NS) == pytest.approx(10.0, abs=1e-3)
    # 半年 10% → (1.1)^2 − 1 = 21%
    assert dm.annualized_return_pct(10.0, 0, 182.5 * DAY_NS) == pytest.approx(21.0, abs=0.1)
    # 不可年化（天数 ≤ 0 / 本金亏光）→ 回退原始总收益率
    assert dm.annualized_return_pct(10.0, DAY_NS, 0) == 10.0
    assert dm.annualized_return_pct(-100.0, 0, 30 * DAY_NS) == -100.0
