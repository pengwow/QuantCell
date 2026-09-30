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


class _KlineProvider:
    def __init__(self, n=200):
        self.n = n

    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        rng = np.random.default_rng(abs(hash(symbol)) % 1000)
        close = 100 + np.cumsum(rng.normal(0, 1, self.n))
        ts = pd.date_range("2026-01-01", periods=self.n, freq="1h")
        return pd.DataFrame(
            {
                "open": close,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": rng.uniform(100, 1000, self.n),
                "quote_volume": close * rng.uniform(100, 1000, self.n),
                "timestamp": ts.astype("int64"),
            }
        )


def test_analyze_includes_inspection_single_symbol():
    res = FactorService().analyze("momentum_5d", ["BTCUSDT"], "1h", "spot", None, None, provider=_KlineProvider())
    insp = res["inspection"]
    assert 0 < insp["coverage"] <= 1
    assert insp["turnover"] is not None and insp["turnover"] >= 0
    assert [d["lag"] for d in insp["decay"]] == [1, 2, 3, 5, 10]
    st = insp["ic_stats"]
    assert st["periods_per_year"] == 8760
    assert set(st) == {
        "n",
        "ic_mean",
        "ic_std",
        "ic_ir",
        "periods_per_year",
        "annualized_ir",
        "t_stat",
        "nw_t_stat",
        "nw_lag",
    }


def test_analyze_inspection_coverage_unaffected_by_forward_tail():
    # forward=3 时 coverage 必须等于 forward=1（尾部是标签缺失，不是因子缺失）
    kw = dict(
        factor_name="momentum_5d",
        symbols=["BTCUSDT"],
        interval="1h",
        candle_type="spot",
        start=None,
        end=None,
        provider=_KlineProvider(),
    )
    r1 = FactorService().analyze(**kw, forward=1)
    r3 = FactorService().analyze(**kw, forward=3)
    assert r3["inspection"]["coverage"] == pytest.approx(r1["inspection"]["coverage"])


def test_analyze_legacy_fields_unchanged():
    res = FactorService().analyze("momentum_5d", ["BTCUSDT"], "1h", "spot", None, None, provider=_KlineProvider())
    for key in (
        "factor_name",
        "instruments",
        "interval",
        "bar_count",
        "stats",
        "ic",
        "groups",
        "long_short_return",
        "monotonicity",
        "stability",
        "series",
    ):
        assert key in res
    assert "inspection" in res


def test_analyze_multi_symbol_inspection_decay():
    res = FactorService().analyze(
        "momentum_5d", ["BTCUSDT", "ETHUSDT"], "1h", "spot", None, None, provider=_KlineProvider()
    )
    assert res["inspection"]["decay"][0]["spearman"] is not None


# ---------------- Newey-West t-stat ----------------


def test_nw_tstat_matches_manual_formula():
    # 构造有正自相关的序列，NW t 绝对值应 <= 普通 t（标准误被放大）
    rng = np.random.default_rng(7)
    x = pd.Series(np.cumsum(rng.normal(0, 1, 500)) * 0.01 + 0.02)
    nw_t, lag = FactorService._nw_tstat(x)
    n = len(x)
    plain_t = x.mean() / (x.std() / np.sqrt(n))
    assert lag == int(np.floor(4 * (n / 100) ** (2 / 9)))
    assert nw_t is not None
    assert abs(nw_t) < abs(plain_t)  # 正自相关 → NW 更保守

    # 手算 Bartlett HAC 复核
    e = (x - x.mean()).to_numpy()
    g0 = np.dot(e, e) / n
    var = g0
    for ell in range(1, lag + 1):
        var += 2 * (1 - ell / (lag + 1)) * np.dot(e[ell:], e[:-ell]) / n
    expected = x.mean() / np.sqrt(var / n)
    assert nw_t == pytest.approx(float(expected), abs=1e-10)


def test_nw_tstat_independent_series_close_to_plain():
    # 独立白噪声：NW 与普通 t 应接近（自相关≈0）
    rng = np.random.default_rng(11)
    x = pd.Series(rng.normal(0.3, 1, 2000))
    nw_t, _ = FactorService._nw_tstat(x)
    plain = x.mean() / (x.std() / np.sqrt(2000))
    assert nw_t == pytest.approx(plain, rel=0.15)


def test_nw_tstat_short_series_is_none():
    assert FactorService._nw_tstat(pd.Series([1.0, 2.0])) == (None, 0)
    assert FactorService._nw_tstat(pd.Series(dtype=float)) == (None, 0)


def test_ic_stats_contains_nw_fields():
    res = FactorService().analyze("momentum_5d", ["BTCUSDT"], "1h", "spot", None, None, provider=_KlineProvider())
    st = res["inspection"]["ic_stats"]
    assert "nw_t_stat" in st and "nw_lag" in st
    assert st["nw_lag"] >= 0


# ---------------- 分位净值 ----------------


def _analyze_df_single(provider=_KlineProvider()):
    """复刻 analyze 内单品种 df（f/r 长表）与 5 分组标签。"""
    svc = FactorService()
    from factor.engine import close_panel_from_raw, factor_panel_from_raw, load_raw_ohlcv

    raw = load_raw_ohlcv(["BTCUSDT"], "1h", "spot", None, None, provider)
    factor = factor_panel_from_raw("momentum_5d", raw, svc._custom_store.all())
    close = close_panel_from_raw(raw)
    aligned = pd.concat([factor.rename("f"), close.rename("c")], axis=1).dropna()
    fr = aligned["c"].groupby(level=1).shift(-1) / aligned["c"] - 1
    df = pd.concat([aligned["f"], fr.rename("r")], axis=1).dropna()
    grp = pd.qcut(df["f"], 5, labels=False, duplicates="drop") + 1
    return df, grp


def test_quantile_nav_time_series_groups_cover_all_bars():
    """单品种时序 qcut：每个时点只属一个组，每组 coverage≈1/5，五组之和≈1。"""
    df, grp = _analyze_df_single()
    nav = FactorService._quantile_nav(df, grp, 5)
    assert len(nav["dates"]) == len(df.index.get_level_values(0).unique())
    assert len(nav["groups"]) == 5
    coverages = [g["coverage"] for g in nav["groups"]]
    assert sum(coverages) == pytest.approx(1.0, abs=1e-9)  # 五组轮值覆盖全部 bar
    for g in nav["groups"]:
        assert set(g) == {"group", "coverage", "turnover", "returns", "nav", "returns_net", "nav_net"}
        assert len(g["nav"]) == len(nav["dates"]) == len(g["returns"])
        valid = [v for v in g["nav"] if v is not None]
        assert all(np.isfinite(v) and v > 0 for v in valid)
    # 时序口径同一时点不同时持有 Q1/Q5，多空净值不可构造 → null（静态多空收益仍在顶层）
    assert nav["long_short_nav"] is None


def test_quantile_nav_cross_section_long_short():
    """2 组截面：每组每时点各持有一个品种，Q2-Q1 同期可得，多空净值可累计。"""
    idx = pd.date_range("2026-01-01", periods=50, freq="1h")
    syms = ["A", "B"]
    # 构造因子：A 恒为高值、B 恒为低值；收益 A 正、B 负 → 多空持续为正
    f = pd.DataFrame([[1.0, 0.0]] * 50, index=idx, columns=syms)
    r = pd.DataFrame([[0.01, -0.01]] * 50, index=idx, columns=syms)
    df = pd.DataFrame({"f": f.stack(), "r": r.stack()})
    df.index.set_names(["datetime", "symbol"], inplace=True)
    grp = FactorService._cross_section_groups(df["f"], 2)

    nav = FactorService._quantile_nav(df, grp, 2)
    assert nav["long_short_nav"] is not None
    assert nav["long_short_returns"][0] == pytest.approx(0.02, abs=1e-12)  # 0.01-(-0.01)
    final = nav["long_short_nav"][-1]
    assert final == pytest.approx(1.02**50, rel=1e-9) and final > 1
    # 两组 coverage 均为 1（每期各持一个）
    assert {g["group"]: g["coverage"] for g in nav["groups"]} == {1: 1.0, 2: 1.0}


def test_quantile_nav_empty_groups_are_zero_return_not_nan_pollution():
    # 2 品种 5 组：中间分位常空，组净值必须连续（空仓按 0 收益），多空在两端不齐时为 null
    provider = _KlineProvider()
    from factor.engine import close_panel_from_raw, factor_panel_from_raw, load_raw_ohlcv

    svc = FactorService()
    raw = load_raw_ohlcv(["BTCUSDT", "ETHUSDT"], "1h", "spot", None, None, provider)
    factor = factor_panel_from_raw("momentum_5d", raw, svc._custom_store.all())
    close = close_panel_from_raw(raw)
    aligned = pd.concat([factor.rename("f"), close.rename("c")], axis=1).dropna()
    fr = aligned["c"].groupby(level=1).shift(-1) / aligned["c"] - 1
    df = pd.concat([aligned["f"], fr.rename("r")], axis=1).dropna()
    wide = df["f"].unstack(level=1)
    buckets = np.ceil(wide.rank(axis=1, pct=True) * 5).clip(1, 5).stack().reindex(df["f"].index)

    nav = FactorService._quantile_nav(df, buckets, 5)
    for g in nav["groups"]:
        # 空组 coverage=0 时净值恒为 1.0（全程空仓）；有覆盖的组净值连续有限
        valid = [v for v in g["nav"] if v is not None]
        assert all(np.isfinite(v) for v in valid)
        if g["coverage"] == 0.0:
            assert all(v == pytest.approx(1.0) for v in valid)


def test_analyze_inspection_includes_quantile_nav():
    res = FactorService().analyze("momentum_5d", ["BTCUSDT"], "1h", "spot", None, None, provider=_KlineProvider())
    qn = res["inspection"]["quantile_nav"]
    assert {"dates", "groups", "long_short_returns", "long_short_nav"} <= set(qn)
    assert len(qn["groups"]) == 5


# ---------------- 自定义 horizon ----------------


def test_decay_custom_horizons():
    svc = FactorService()
    res = svc.analyze(
        "momentum_5d",
        ["BTCUSDT"],
        "1h",
        "spot",
        None,
        None,
        horizons=[1, 4, 8],
        provider=_KlineProvider(),
    )
    lags = [d["lag"] for d in res["inspection"]["decay"]]
    assert lags == [1, 4, 8]


def test_decay_default_horizons_unchanged():
    res = FactorService().analyze("momentum_5d", ["BTCUSDT"], "1h", "spot", None, None, provider=_KlineProvider())
    assert [d["lag"] for d in res["inspection"]["decay"]] == [1, 2, 3, 5, 10]


# ---------------- 双边换手与费后净值 ----------------


def test_quantile_nav_zero_cost_net_equals_gross():
    res = FactorService().analyze(
        "momentum_5d",
        ["BTCUSDT"],
        "1h",
        "spot",
        None,
        None,
        n_groups=5,
        cost_bps=0.0,
        provider=_KlineProvider(),
    )
    qn = res["inspection"]["quantile_nav"]
    assert qn["fee_rate"] == 0.0
    for g in qn["groups"]:
        assert g["nav_net"] == pytest.approx(g["nav"], abs=1e-12)
        assert g["turnover"] >= 0.0


def test_quantile_nav_cost_reduces_nav_and_turnover_bounded():
    res0 = FactorService().analyze(
        "momentum_5d",
        ["BTCUSDT", "ETHUSDT"],
        "1h",
        "spot",
        None,
        None,
        n_groups=2,
        cost_bps=0.0,
        provider=_KlineProvider(),
    )
    res10 = FactorService().analyze(
        "momentum_5d",
        ["BTCUSDT", "ETHUSDT"],
        "1h",
        "spot",
        None,
        None,
        n_groups=2,
        cost_bps=10.0,
        provider=_KlineProvider(),
    )
    q0, q10 = res0["inspection"]["quantile_nav"], res10["inspection"]["quantile_nav"]
    assert q0["fee_rate"] == 0.0 and q10["fee_rate"] == pytest.approx(0.001)
    for g0, g10 in zip(q0["groups"], q10["groups"], strict=True):
        assert 0.0 <= g10["turnover"] <= 2.0
        # 有换手时，费后每一期净值 ≤ 费前（成本非负）
        for net, gross in zip(g10["nav_net"], g0["nav"], strict=True):
            assert net <= gross + 1e-12
    # 截面多空换手在 (0,2]，费后多空净值 ≤ 费前
    assert q0["long_short_turnover"] is not None and 0 < q0["long_short_turnover"] <= 2.0
    if q0["long_short_nav"] and q10["long_short_nav_net"]:
        gross_final = [v for v in q0["long_short_nav"] if v is not None][-1]
        net_final = [v for v in q10["long_short_nav_net"] if v is not None][-1]
        assert net_final <= gross_final + 1e-12


def test_quantile_nav_schema_fields():
    res = FactorService().analyze(
        "momentum_5d",
        ["BTCUSDT", "ETHUSDT"],
        "1h",
        "spot",
        None,
        None,
        n_groups=2,
        cost_bps=5.0,
        provider=_KlineProvider(),
    )
    qn = res["inspection"]["quantile_nav"]
    g = qn["groups"][0]
    assert set(g) == {
        "group",
        "coverage",
        "turnover",
        "returns",
        "nav",
        "returns_net",
        "nav_net",
    }
    assert {"fee_rate", "long_short_turnover", "long_short_nav_net"} <= set(qn)
