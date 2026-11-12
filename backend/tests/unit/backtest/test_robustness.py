"""P1-04：Deflated Sharpe 接线测试（backend/backtest/robustness.py）。

覆盖：
- 试验数不足 / 内核缺位 → None（不降级为伪值）
- 已知样本数值断言（与内核单测基准函数直通对拍 + golden 值）
- equity curve 按年分段试验口径（yearly_sharpes）
- format_axon_results 输出结构挂 robustness.deflated_sharpe
"""

import math
import statistics

import pytest
from axon_quant.walk_forward import py_deflated_sharpe as kernel_dsr

from backtest import robustness
from backtest.result_formatter_service import ResultFormatterService

# 内核实测 golden 值：dsr(mean=2.0, n=2, std=sqrt(2)) 与 dsr(2.0, 100, 1.0)
GOLDEN_TWO_TRIALS = 0.7117544946993933
GOLDEN_HUNDRED_TRIALS = 0.1736712238853042

# equity curve 起点毫秒时间戳：2023-01-01 / 2024-01-01 UTC
MS_2023 = 1_672_531_200_000
MS_2024 = 1_704_067_200_000
HOUR_MS = 3_600_000


def _curve(start_ms: int, hours: int) -> list[dict]:
    """确定性权益曲线：正弦波动 + 线性漂移，保证段内方差非零。"""
    points = []
    for i in range(hours + 1):
        eq = 100_000.0 * (1.0 + 0.0005 * math.sin(i / 24.0) + 0.000_002 * i)
        points.append({"timestamp": start_ms + i * HOUR_MS, "equity": eq})
    return points


def _two_year_curve() -> list[dict]:
    return _curve(MS_2023, 24 * 365) + _curve(MS_2024, 24 * 365)


def test_deflated_sharpe_insufficient_trials_returns_none():
    assert robustness.deflated_sharpe([]) is None
    assert robustness.deflated_sharpe([1.0]) is None


def test_deflated_sharpe_kernel_missing_returns_none(monkeypatch):
    monkeypatch.setattr(robustness, "_dsr", None)
    assert robustness.deflated_sharpe([3.0, 1.0, 2.0]) is None


def test_deflated_sharpe_known_sample_values():
    # 两 trial (mean=2.0, std=sqrt(2)) 内核实测 golden 值，见文件头
    assert robustness.deflated_sharpe([3.0, 1.0]) == pytest.approx(GOLDEN_TWO_TRIALS)
    # 任意序列与内核公直通对拍（statistics.stdev 即 sample std，与实现同式）
    trials = [3.0, 1.0, 2.5, 0.5, 4.0]
    assert robustness.deflated_sharpe(trials) == pytest.approx(
        kernel_dsr(statistics.mean(trials), len(trials), statistics.stdev(trials))
    )
    assert 0.0 <= robustness.deflated_sharpe(trials) <= 1.0


def test_kernel_golden_hundred_trials():
    # 锁内核行为不变：dsr(2.0, 100, 1.0) 的实取值（见文件头）
    assert kernel_dsr(2.0, 100, 1.0) == pytest.approx(GOLDEN_HUNDRED_TRIALS)


def test_yearly_sharpes_two_years():
    sharpes = robustness.yearly_sharpes(_two_year_curve())
    assert len(sharpes) == 2
    # 漂移为正的确定性曲线，两段 sharpe 均应为正
    assert all(s > 0 for s in sharpes)


def test_yearly_sharpes_single_year_returns_one_trial():
    assert len(robustness.yearly_sharpes(_curve(MS_2023, 24 * 365))) == 1
    # 单 trial 无法估 std → DSR None
    assert robustness.deflated_sharpe(robustness.yearly_sharpes(_curve(MS_2023, 24 * 365))) is None


def test_yearly_sharpes_skips_flat_segment():
    flat = [{"timestamp": MS_2023 + i * HOUR_MS, "equity": 100_000.0} for i in range(24 * 365 + 1)]
    sharpes = robustness.yearly_sharpes(flat + _curve(MS_2024, 24 * 365))
    assert len(sharpes) == 1  # 2023 全平台零方差段被跳过


def test_yearly_sharpes_degenerate_inputs():
    assert robustness.yearly_sharpes([]) == []
    assert robustness.yearly_sharpes([None, 42, "x"]) == []
    assert robustness.yearly_sharpes([{"timestamp": MS_2023, "equity": -1.0}]) == []
    # 缺 equity 字段
    assert robustness.yearly_sharpes([{"timestamp": MS_2023}]) == []


def test_format_axon_results_reports_deflated_sharpe():
    """formatter 挂接：robustness 字段 + metrics 展示项。"""
    formatted = ResultFormatterService.format_axon_results(
        results={"equity_curve": _two_year_curve(), "trades": []},
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )
    entry = formatted["BTCUSDT_1h"]
    value = entry["robustness"]["deflated_sharpe"]
    assert value is not None and 0.0 <= value <= 1.0
    metric = next(m for m in entry["metrics"] if m["key"] == "deflated_sharpe")
    assert metric["value"] == pytest.approx(round(value, 4))


def test_format_axon_results_deflated_sharpe_none_when_insufficient():
    """数据不足（仅等值两点、无法分年）→ robustness.deflated_sharpe 为 None。"""
    formatted = ResultFormatterService.format_axon_results(
        results={"equity_curve": [{"timestamp": MS_2023, "equity": 100.0}], "trades": []},
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )
    entry = formatted["BTCUSDT_1h"]
    assert entry["robustness"] == {"deflated_sharpe": None}
    metric = next(m for m in entry["metrics"] if m["key"] == "deflated_sharpe")
    assert metric["value"] is None
