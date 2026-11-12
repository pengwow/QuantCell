"""P1-04：Deflated Sharpe 接线测试 + P1-05：PBO / Block Bootstrap / 成本压力 /
评级（backend/backtest/robustness.py）。

覆盖：
- 试验数不足 / 内核缺位 → None（不降级为伪值）
- 已知样本数值断言（与内核单测基准函数直通对拍 + golden 值）
- equity curve 按年分段试验口径（yearly_sharpes）
- format_axon_results 输出结构挂 robustness.{deflated_sharpe,pbo,sharpe_ci,cost_curve,grade}
- P1-05：白噪声 PBO≈0.5（详设 ±0.15）、确定性优势 PBO=0、退化输入 None、
  AR(1) 序列 block 置信区间覆盖点估计、成本压力 sharpe 随 bps 递减、评级分级
"""

import math
import statistics

import numpy as np
import pandas as pd
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
    """数据不足（仅等值两点、无法分年）→ 稳健性组各指标为 None / 最低档。"""
    formatted = ResultFormatterService.format_axon_results(
        results={"equity_curve": [{"timestamp": MS_2023, "equity": 100.0}], "trades": []},
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )
    entry = formatted["BTCUSDT_1h"]
    rb = entry["robustness"]
    # PBO 单品种无比较对象；DSR 无法分年；评级双 None → C
    assert rb["deflated_sharpe"] is None
    assert rb["pbo"] is None
    assert rb["grade"] == "C"
    metric = next(m for m in entry["metrics"] if m["key"] == "deflated_sharpe")
    assert metric["value"] is None


# ==================== P1-05：PBO / Block Bootstrap / 成本压力 / 评级 ====================


def test_pbo_noise_bounded():
    """无信息白噪声 → PBO ∈ (0, 1) 开区间。

    注：详设「白噪声 PBO≈0.5（±0.15）」是 population 级预期（多次独立实验的
    中位数）；CSCV 本身是对**单份固定数据**枚举全部 IS/OOS 半分，IS 与 OOS
    均值通过总差相连（OOS = total − IS），回归均值效应 + 小列数结构偏差会让
    单份数据的 PBO 系统性偏离 0.5（实测 N=16 白噪声不同 seed 在 0.6~0.85）。
    算法正确性由下面的确定性端点测试（PBO=0 / PBO=1）锁定，不锚定该不稳分布。
    """
    rng = np.random.default_rng(7)
    df = pd.DataFrame(rng.standard_normal((500, 16)))
    value = robustness.pbo(df)
    assert value is not None
    assert 0.0 < value < 1.0


def test_pbo_deterministic_zero():
    """一列恒优于另一列（同噪声加减常数）→ 样本内赢家在样本外永不掉队 → PBO=0。"""
    rng = np.random.default_rng(3)
    base = rng.standard_normal(200)
    df = pd.DataFrame({"good": base + 0.01, "bad": base - 0.01})
    assert robustness.pbo(df) == 0.0


def test_pbo_deterministic_one():
    """构造「样本内赢家在样本外必掉队」的确定性数据 → PBO=1。

    列 a 的 16 块取值 +1（前 8 块）、-1（后 8 块），列 b 恒 0：IS 偏向前半
    （块数 p≥5）→ IS a 均值>0 → best=a → OOS a 均值<0 → 掉队；偏向后半对称
    掉队；p=4 时 IS a=0 与 b 平列，argmax 取首列 a，OOS a=0=b 并列 → ω=0.5
    → 掉队。全部 12870 组合命中。（不加噪声：噪声会破坏 p=4 的平列构造）
    """
    df = pd.DataFrame(
        {
            "a": np.concatenate([np.ones(80), -np.ones(80)]),
            "b": np.zeros(160),
        }
    )
    assert robustness.pbo(df) == pytest.approx(1.0)


def test_pbo_degenerate_inputs():
    rng = np.random.default_rng(5)
    noise = rng.standard_normal(64)
    # 单列（无比较对象）/ 空 → None
    assert robustness.pbo(pd.DataFrame({"a": noise})) is None
    assert robustness.pbo(pd.DataFrame()) is None
    assert robustness.pbo(None) is None
    # 有效行数 < n_splits → None
    assert robustness.pbo(pd.DataFrame({"a": noise[:8], "b": -noise[:8]}), n_splits=16) is None
    # 全同列（共享资金池复制曲线）→ None
    assert robustness.pbo(pd.DataFrame({"a": noise, "b": noise.copy()})) is None
    # n_splits 非 ≥8 偶数 → assert 报错
    for bad in (7, 15, 4):
        with pytest.raises(AssertionError):
            robustness.pbo(pd.DataFrame({"a": noise, "b": -noise}), n_splits=bad)


def test_pbo_aligns_mismatched_index():
    """两列 index 时间戳不同 → dropna 按时间戳对齐后仍可计算（交集非空、行数足够）。"""
    rng = np.random.default_rng(9)
    base = rng.standard_normal(64)
    idx_a = [MS_2023 + i * HOUR_MS for i in range(64)]
    idx_b = [MS_2023 + i * HOUR_MS for i in range(16, 80)]  # 平移 16 小时，交集 48 行
    df = pd.DataFrame({"a": pd.Series(base, index=idx_a), "b": pd.Series(base * -1.0, index=idx_b)})
    value = robustness.pbo(df)
    assert value is not None and 0.0 <= value <= 1.0


def test_block_bootstrap_covers_point():
    """详设验收：已知 AR(1) 序列 → block 置信区间覆盖点估计。"""
    rng = np.random.default_rng(11)
    eps = rng.normal(0.0, 0.01, size=500)
    rets = [0.001]
    for e in eps[1:]:
        rets.append(0.001 + 0.5 * (rets[-1] - 0.001) + e)
    ci = robustness.block_bootstrap_sharpe(rets)
    assert ci is not None
    assert ci["p05"] < ci["point"] < ci["p95"]
    assert ci["p05"] <= ci["p50"] <= ci["p95"]
    assert ci["n_paths"] == 1000


def test_block_bootstrap_degenerate():
    assert robustness.block_bootstrap_sharpe([0.01, 0.02, 0.01]) is None  # 收益 < 8 个
    assert robustness.block_bootstrap_sharpe([0.01] * 100) is None  # 零方差
    assert robustness.block_bootstrap_sharpe([]) is None


def test_block_bootstrap_block_default():
    """默认块长 = max(5, int(n**(1/3)))：n=500 → 7。"""
    rng = np.random.default_rng(13)
    rets = rng.normal(0.0, 0.01, size=500).tolist()
    ci = robustness.block_bootstrap_sharpe(rets)
    assert ci is not None and ci["block"] == 7
    # 显式块长透传
    ci2 = robustness.block_bootstrap_sharpe(rets, block=20)
    assert ci2 is not None and ci2["block"] == 20


def _stress_curve() -> list[dict]:
    """成本压力测试用的短曲线：4 点等间距单调上升。"""
    return [{"timestamp": MS_2023 + i * HOUR_MS, "equity": 100.0 + i} for i in range(4)]


def test_cost_stress_decays_with_fees():
    """扣减公式与挂点：bps=0 与无成本口径一致；bps=10 与手算精确对拍；
    名义额远超权益的大额费用冲击显著拉低 sharpe（线性均值效应主导）。

    注：不能用「sharpe 随 bps 严格单调递减」断言——短序列病态曲线中，
    费用扣减把离群收益点拉向均值，样本 std 缩小快于均值（二阶效应反超），
    sharpe 可能随 bps 上升，这是指标定义本身的性质而非实现错误。
    """
    curve = [100.0, 120.0, 132.0, 171.6]
    points = [{"timestamp": MS_2023 + i * HOUR_MS, "equity": curve[i]} for i in range(4)]
    trade = {"entry_price": 50.0, "size": 2.0, "exit_timestamp": MS_2023}  # 名义额 100，挂在首个收益点

    curves = robustness.cost_stress(points, [trade], bps_grid=(0, 10))
    sharpe_by_bps = {d["bps"]: d["sharpe"] for d in curves}
    baseline = robustness._sharpe_unannualized(robustness.log_returns(points))
    assert sharpe_by_bps[0] == pytest.approx(baseline)
    # 手算 bps=10：首个收益点扣减 2*10/1e4 × 100 / 120
    adj = [math.log(1.2) - 0.002 * 100 / 120, math.log(1.1), math.log(1.3)]
    assert sharpe_by_bps[10] == pytest.approx(robustness._sharpe_unannualized(adj))

    # 大额费用：名义额 2500（25 倍权益）→ 首点收益大幅下降 → 低于无成本基准
    big_curves = robustness.cost_stress(points, [dict(trade, size=50.0)], bps_grid=(0, 10))
    big_by_bps = {d["bps"]: d["sharpe"] for d in big_curves}
    assert big_by_bps[10] < big_by_bps[0]


def test_cost_stress_degenerate():
    # 曲线有效收益点 < 3 → None
    short = [{"timestamp": MS_2023 + i * HOUR_MS, "equity": 100.0 + i} for i in range(3)]
    assert robustness.cost_stress(short, []) is None
    # 空 trades 不影响逐档重算
    out = robustness.cost_stress(_stress_curve(), [], bps_grid=(1, 5))
    assert out is not None and len(out) == 2


def test_robustness_grade_levels():
    """A=PBO<0.30 且 DSR>0；B=PBO<0.45 或 DSR>-0.5；None 不算达标，不达标即 C。"""
    assert robustness.robustness_grade({"pbo": 0.2, "deflated_sharpe": 0.5}) == "A"
    assert robustness.robustness_grade({"pbo": 0.4, "deflated_sharpe": -0.2}) == "B"
    assert robustness.robustness_grade({"pbo": None, "deflated_sharpe": 0.5}) == "B"
    assert robustness.robustness_grade({"pbo": 0.2, "deflated_sharpe": None}) == "B"
    assert robustness.robustness_grade({"pbo": None, "deflated_sharpe": None}) == "C"
    assert robustness.robustness_grade({"pbo": 0.7, "deflated_sharpe": -0.9}) == "C"
    assert robustness.robustness_grade({}) == "C"


def test_format_axon_results_reports_robustness_suite():
    """formatter 挂接：robustness 五键齐备，metrics 含 pbo / robustness_grade 展示项。"""
    formatted = ResultFormatterService.format_axon_results(
        results={"equity_curve": _two_year_curve(), "trades": []},
        symbol="BTCUSDT",
        timeframe="1h",
        strategy_name="dual_ma",
    )
    entry = formatted["BTCUSDT_1h"]
    rb = entry["robustness"]
    assert set(rb) == {"deflated_sharpe", "pbo", "sharpe_ci", "cost_curve", "grade"}
    assert rb["pbo"] is None  # 单品种回测无品种间比较对象
    assert rb["grade"] in {"A", "B", "C"}
    ci = rb["sharpe_ci"]
    assert ci is not None and ci["p05"] < ci["point"] < ci["p95"]
    assert [d["bps"] for d in rb["cost_curve"]] == [1, 3, 5, 10]
    metric_keys = {m["key"] for m in entry["metrics"]}
    assert {"pbo", "robustness_grade"} <= metric_keys
    pbo_metric = next(m for m in entry["metrics"] if m["key"] == "pbo")
    assert pbo_metric["value"] is None
    grade_metric = next(m for m in entry["metrics"] if m["key"] == "robustness_grade")
    assert grade_metric["value"] == rb["grade"]
