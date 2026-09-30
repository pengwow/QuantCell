"""cs_rank/cs_zscore 截面算子测试（合成多品种 K 线）。"""

import numpy as np
import pandas as pd
import pytest

from factor.engine import factor_panel_from_raw
from factor.service import FactorService


def _raw(n: int = 60, n_sym: int = 3, seed: int = 1) -> dict[str, pd.DataFrame]:
    """{symbol: raw_df}，确定性 OHLCV + 整数纳秒 timestamp。"""
    rng = np.random.default_rng(seed)
    out = {}
    for i in range(n_sym):
        close = 100 + np.cumsum(rng.normal(0, 1, n))
        out[f"S{i}"] = pd.DataFrame(
            {
                "open": close + rng.normal(0, 0.2, n),
                "high": close + np.abs(rng.normal(0, 0.5, n)),
                "low": close - np.abs(rng.normal(0, 0.5, n)),
                "close": close,
                "volume": rng.uniform(100, 1000, n),
                "quote_volume": close * rng.uniform(100, 1000, n),
                "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h").astype("int64"),
            }
        )
    return out


def _panel(expr: str, raw_map: dict[str, pd.DataFrame]) -> pd.Series:
    """把表达式作为临时自定义因子，经 factor_panel_from_raw 面板求值。"""
    return factor_panel_from_raw("__cs_under_test__", raw_map, {"__cs_under_test__": expr})


# ---------------- cs_rank ----------------


def test_cs_rank_two_symbols_values_are_half_and_one():
    raw = _raw(n_sym=2)
    p = _panel("cs_rank(close)", raw)
    w = p.unstack(level=1)
    vals = set(np.round(w.dropna().iloc[10], 6))
    assert vals == {0.5, 1.0}


def test_cs_rank_three_symbols_terciles():
    raw = _raw(n_sym=3)
    p = _panel("cs_rank(close)", raw)
    w = p.unstack(level=1)
    vals = sorted(np.round(w.dropna().iloc[10], 6).tolist())
    assert vals == pytest.approx([1 / 3, 2 / 3, 1.0])


def test_cs_rank_highest_value_gets_one():
    raw = _raw(n_sym=3)
    p = _panel("cs_rank(close)", raw)
    w = p.unstack(level=1)
    row = w.dropna().iloc[20]
    # 截面上 close 最大的品种 rank=1.0
    raw_close = pd.DataFrame({s: d["close"] for s, d in raw.items()})
    top_symbol = raw_close.iloc[20].idxmax()
    assert row[top_symbol] == pytest.approx(1.0)


def test_cs_rank_single_symbol_is_one():
    raw = _raw(n_sym=1)
    p = _panel("cs_rank(close)", raw)
    assert (p.dropna() == 1.0).all()


# ---------------- cs_zscore ----------------


def test_cs_zscore_matches_manual_and_row_zero_mean():
    raw = _raw(n_sym=3)
    p = _panel("cs_zscore(close)", raw)
    w = p.unstack(level=1)
    raw_close = pd.DataFrame({s: d["close"] for s, d in raw.items()})
    i = 20
    expected = (raw_close.iloc[i] - raw_close.iloc[i].mean()) / raw_close.iloc[i].std()
    assert w.iloc[i].reindex(expected.index).values == pytest.approx(expected.values, abs=1e-10)
    # 每行 z-score 均值≈0
    assert float(w.mean(axis=1).dropna().abs().max()) == pytest.approx(0.0, abs=1e-12)


def test_cs_zscore_single_symbol_is_nan():
    raw = _raw(n_sym=1)
    p = _panel("cs_zscore(close)", raw)
    # 单品种截面无法标准化 → 全 NaN（但仍是合法序列，analyze 报有效数据不足而非崩溃）
    assert p.isna().all()


def test_cs_zscore_constant_cross_section_is_nan():
    # 构造三品种 close 完全相同 → 截面 std=0 → zscore NaN（而非 inf）
    n = 30
    close = np.linspace(100, 110, n)
    raw = {
        s: pd.DataFrame(
            {
                "open": close,
                "high": close + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": np.full(n, 100.0),
                "quote_volume": close * 100,
                "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h").astype("int64"),
            }
        )
        for s in ("A", "B", "C")
    }
    p = _panel("cs_zscore(close)", raw)
    assert p.isna().all()


# ---------------- 嵌套 ----------------


def test_cs_rank_of_timeseries_inner():
    # cs_rank(MA(close,5))：截面包时序
    raw = _raw(n_sym=2)
    p = _panel("cs_rank(MA(close, 5))", raw)
    w = p.unstack(level=1).dropna(how="all")
    # MA 热身（前4根）NaN，之后每行两品种 {0.5,1.0}
    vals = set(np.round(w.iloc[5], 6))
    assert vals == {0.5, 1.0}
    assert len(w) == 60 - 4


def test_timeseries_over_cs_rank():
    # MA(cs_rank(close),3)：时序包截面，按品种滚动不跨品种
    raw = _raw(n_sym=2)
    p = _panel("MA(cs_rank(close), 3)", raw)
    btc = p.xs("S0", level=1).dropna()
    # 手工：S0 的 cs_rank 序列（0.5/1.0）前 3 根均值
    import ast

    from factor.engine import _column_env, _eval

    # 通过面板直接复算 rank
    envs = {s: _column_env(d) for s, d in raw.items()}
    pieces = []
    for s in raw:
        v = _eval(ast.parse("close", mode="eval"), envs[s])
        v = v.copy()
        v.index = pd.MultiIndex.from_arrays([v.index, [s] * len(v)], names=["datetime", "symbol"])
        pieces.append(v)
    close_long = pd.concat(pieces).sort_index()
    rank = close_long.unstack(level=1).rank(axis=1, pct=True).stack()
    manual = rank.xs("S0", level=1).rolling(3).mean().dropna()
    assert btc.values == pytest.approx(manual.values, abs=1e-12)


def test_binop_with_cs_and_scalar():
    raw = _raw(n_sym=2)
    p = _panel("cs_rank(close) - 0.5", raw)
    w = p.unstack(level=1).dropna()
    vals = set(np.round(w.iloc[10], 6))
    assert vals == {0.0, 0.5}


# ---------------- 白名单/错误 ----------------


def test_validate_accepts_cs_expressions():
    svc = FactorService()
    assert svc.validate_factor_expression("cs_rank(close)") is True
    assert svc.validate_factor_expression("cs_zscore(close - open)") is True
    assert svc.validate_factor_expression("MA(cs_rank(close), 5)") is True


def test_cs_wrong_arity_rejected():
    svc = FactorService()
    assert svc.validate_factor_expression("cs_rank()") is False
    assert svc.validate_factor_expression("cs_rank(close, 5)") is False


def test_unknown_cs_function_rejected():
    svc = FactorService()
    assert svc.validate_factor_expression("cs_mean(close)") is False
    assert svc.validate_factor_expression("__import__('os')") is False


def test_legacy_expressions_still_work():
    # 非 cs 表达式走原逐品种路径，结果不变
    raw = _raw(n_sym=2)
    p1 = _panel("close / Ref(close, 5) - 1", raw)
    p2 = _panel("MA(close, 5)", raw)
    assert p1.notna().sum() > 0
    assert p2.notna().sum() > 0
