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
