# FactorService.analyze / calculate 单测：FakeProvider 合成数据，不读真实 parquet
import numpy as np
import pandas as pd
import pytest

from factor.service import FactorError, FactorNotFoundError, FactorService


class FakeProvider:
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


def test_analyze_single_symbol():
    res = FactorService().analyze("momentum_20d", ["BTCUSDT"], "1h", "spot", None, None, provider=FakeProvider())
    assert res["bar_count"] > 0
    assert len(res["groups"]) == 5
    assert set(res["series"]["factor"]) == set(res["series"]["dates"])
    assert isinstance(res["stability"]["mean_autocorr"], float)


def test_analyze_multi_symbol():
    res = FactorService().analyze(
        "momentum_5d", ["BTCUSDT", "ETHUSDT"], "1h", "spot", None, None, provider=FakeProvider()
    )
    assert len(res["ic"]["series"]) > 0


def test_analyze_unsupported_and_unknown():
    with pytest.raises(FactorError):
        FactorService().analyze("pe", ["BTCUSDT"], "1h", "spot", None, None, provider=FakeProvider())
    with pytest.raises(FactorNotFoundError):
        FactorService().analyze("nope", ["BTCUSDT"], "1h", "spot", None, None, provider=FakeProvider())


def test_calculate_factor_signature_and_frame():
    svc = FactorService()
    df = svc.calculate_factor("momentum_5d", ["BTCUSDT"], None, None, interval="1h", provider=FakeProvider())
    assert df.index.names == ["datetime", "symbol"]
    assert list(df.columns) == ["momentum_5d"]


class CountingProvider(FakeProvider):
    def __init__(self, n=200):
        super().__init__(n)
        self.read_count = 0

    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        self.read_count += 1
        return super().get_kline_data(symbol, interval, candle_type, start, end)


def test_analyze_reads_each_symbol_only_once():
    # 因子面板与收盘价面板必须复用同一次读盘结果（2 品种 = 2 次而非 4 次）
    provider = CountingProvider()
    FactorService().analyze("momentum_5d", ["BTCUSDT", "ETHUSDT"], "1h", "spot", None, None, provider=provider)
    assert provider.read_count == 2


def _make_multi_symbol_panel(n_dates=120, n_symbols=8, seed=7):
    """构造 datetime×symbol 的 (factor, forward_return) 长表面板。"""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_dates, freq="1h")
    symbols = [f"S{i}" for i in range(n_symbols)]
    factor, returns = {}, {}
    for s in symbols:
        base = rng.normal(0, 1, n_dates)
        ret = 0.6 * base + rng.normal(0, 0.5, n_dates)  # 因子与未来收益正相关
        factor[s] = base
        returns[s] = ret
    fw = pd.DataFrame(factor, index=dates)
    rw = pd.DataFrame(returns, index=dates)
    f = fw.stack()
    r = rw.stack()
    f.index.names = ["datetime", "symbol"]
    r.index.names = ["datetime", "symbol"]
    return f, r


def test_reference_ic_series():
    f, r = _make_multi_symbol_panel()
    ic = FactorService._ic_series(f, r, "spearman", 20)
    assert len(ic) == 120
    assert ic.mean() > 0.3  # 构造上强正相关


def test_vectorized_ic_matches_groupby_reference():
    f, r = _make_multi_symbol_panel()
    # 在两侧不同位置注入缺失，考验成对有效掩码（不掩码会导致 rank 池不一致）
    f_w, r_w = f.unstack(level=1), r.unstack(level=1)
    f_w.iloc[3, 2] = np.nan
    r_w.iloc[10, 1] = np.nan
    f, r = f_w.stack(), r_w.stack()

    # 参考实现：逐日期截面 spearman（改造前的口径）
    joined = pd.concat([f.rename("f"), r.rename("r")], axis=1).dropna()
    ref = joined.groupby(level=0).apply(lambda g: g["f"].corr(g["r"], method="spearman")).dropna()

    got = FactorService._ic_series(f, r, "spearman", 20)
    aligned = pd.concat([ref.rename("ref"), got.rename("got")], axis=1).dropna()
    assert np.allclose(aligned["ref"], aligned["got"], atol=1e-10, equal_nan=True)

    # pearson 同样一致
    ref_p = joined.groupby(level=0).apply(lambda g: g["f"].corr(g["r"], method="pearson")).dropna()
    got_p = FactorService._ic_series(f, r, "pearson", 20)
    ap = pd.concat([ref_p.rename("ref"), got_p.rename("got")], axis=1).dropna()
    assert np.allclose(ap["ref"], ap["got"], atol=1e-10, equal_nan=True)


def test_ic_series_single_symbol_keeps_rolling_path():
    # 单品种仍走滚动窗口相关，返回非空序列
    f, r = _make_multi_symbol_panel(n_symbols=1)
    ic = FactorService._ic_series(f, r, "spearman", 20)
    assert len(ic) > 0
