"""Inspector-lite inspection 指标纯函数测试（合成数据）。"""

import numpy as np
import pandas as pd
import pytest

from factor.service import FactorService


def _multi_panel(n=120, n_sym=2, seed=1):
    """返回 (factor_wide datetime×symbol, close_wide)，因子前 10 根 NaN。"""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2026-01-01", periods=n, freq="1h")
    syms = [f"S{i}" for i in range(n_sym)]
    close = pd.DataFrame(100 + np.cumsum(rng.normal(0, 1, (n, n_sym)), axis=0), index=idx, columns=syms)
    factor = pd.DataFrame(rng.normal(0, 1, (n, n_sym)), index=idx, columns=syms)
    factor.iloc[:10] = np.nan
    return factor, close


def test_periods_per_year_mapping():
    f = FactorService._periods_per_year
    assert f("1d") == 365
    assert f("4h") == 2190
    assert f("1h") == 8760
    assert f("15m") == 35040
    assert f("5m") == 365 * 24 * 12
    assert f("30m") == 17520
    assert f("garbage") == 365 * 24  # 未知兜底按 1h


def test_coverage_excludes_forward_tail_but_counts_factor_warmup():
    factor, _ = _multi_panel(n=120)
    # 分母=总 bar（120×2=240）；分子=因子非空（每品种 110，共 220）；forward 尾部不影响 coverage
    cov = FactorService._coverage(factor, total_bars=factor.size)
    assert cov == pytest.approx(220 / 240)
    # 直接用长表 Series 口径也应一致
    cov_series = FactorService._coverage(factor.stack(), total_bars=factor.size)
    assert cov_series == pytest.approx(cov)


def test_coverage_full_when_no_nan():
    factor, _ = _multi_panel()
    full = factor.bfill().ffill()
    assert FactorService._coverage(full, total_bars=full.size) == pytest.approx(1.0)


def test_turnover_non_negative_and_zero_for_constant():
    factor, _ = _multi_panel()
    assert FactorService._turnover(factor) >= 0
    const = pd.DataFrame(
        np.ones((50, 2)), columns=["S0", "S1"], index=pd.date_range("2026-01-01", periods=50, freq="1h")
    )
    assert FactorService._turnover(const) == pytest.approx(0.0)


def test_decay_lags_and_structure_single_symbol():
    factor, close = _multi_panel(n=120, n_sym=1)
    decay = FactorService._decay(factor.stack(), close.stack(), n_symbols=1, window=20)
    assert [d["lag"] for d in decay] == [1, 2, 3, 5, 10]
    for d in decay:
        assert set(d) == {"lag", "spearman", "pearson"}
        assert d["spearman"] is None or -1 <= d["spearman"] <= 1


def test_decay_lag1_matches_direct_correlation_single():
    factor, close = _multi_panel(n=120, n_sym=1)
    fs, cs = factor.stack(), close.stack()
    r1 = cs.groupby(level=1).shift(-1) / cs - 1
    j = pd.concat([fs.rename("f"), r1.rename("r")], axis=1).dropna()
    decay = FactorService._decay(fs, cs, n_symbols=1, window=20)
    assert decay[0]["spearman"] == pytest.approx(j["f"].corr(j["r"], method="spearman"), abs=1e-10)
    assert decay[0]["pearson"] == pytest.approx(j["f"].corr(j["r"], method="pearson"), abs=1e-10)


def test_decay_multi_symbol_returns_values():
    factor, close = _multi_panel(n=120, n_sym=3)
    decay = FactorService._decay(factor.stack(), close.stack(), n_symbols=3, window=20)
    assert len(decay) == 5
    # 多品种截面 lag1 应该是有限值（构造数据样本充足）
    assert decay[0]["spearman"] is not None


def test_ic_stats_formulas():
    ic = pd.Series(np.linspace(-0.2, 0.2, 101))
    stats = FactorService._ic_stats(ic, interval="1h")
    n = 101
    mean, std = ic.mean(), ic.std()
    ir = mean / std
    assert stats["n"] == n
    assert stats["ic_mean"] == pytest.approx(mean)
    assert stats["ic_std"] == pytest.approx(std)
    assert stats["ic_ir"] == pytest.approx(ir)
    assert stats["periods_per_year"] == 8760
    assert stats["annualized_ir"] == pytest.approx(ir * np.sqrt(8760))
    assert stats["t_stat"] == pytest.approx(mean / (std / np.sqrt(n)))


def test_ic_stats_none_for_short_series():
    stats = FactorService._ic_stats(pd.Series(dtype=float), interval="1h")
    assert stats["n"] == 0 and stats["annualized_ir"] is None and stats["t_stat"] is None
