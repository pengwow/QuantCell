"""多因子对比服务测试（合成数据）。"""

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from factor.service import FactorError, FactorNotFoundError, FactorService


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


def test_compare_two_factors_rows_and_aligned_ic_series():
    res = FactorService().compare_factors(
        factor_names=["momentum_5d", "rsi_14d"],
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="1h",
        candle_type="spot",
        start=None,
        end=None,
        method="spearman",
        n_groups=5,
        window=20,
        forward=1,
        provider=_KlineProvider(),
    )
    assert [r["factor_name"] for r in res["factors"]] == ["momentum_5d", "rsi_14d"]
    row = res["factors"][0]
    assert {
        "factor_name",
        "label",
        "coverage",
        "turnover",
        "ic_mean",
        "ic_ir",
        "annualized_ir",
        "t_stat",
        "ic_positive_rate",
        "long_short_return",
        "monotonicity_spearman",
        "stability_autocorr",
        "n_groups",
        "bar_count",
    } <= set(row)
    series = res["ic_series"]
    assert set(series["series"]) == {"momentum_5d", "rsi_14d"}
    assert len(series["dates"]) == len(series["series"]["momentum_5d"])
    assert len(series["dates"]) == len(series["series"]["rsi_14d"])


def test_compare_unknown_factor_raises():
    with pytest.raises((FactorNotFoundError, FactorError)):
        FactorService().compare_factors(
            factor_names=["momentum_5d", "ghost"],
            symbols=["BTCUSDT"],
            interval="1h",
            candle_type="spot",
            start=None,
            end=None,
            provider=_KlineProvider(),
        )


def test_compare_request_enforces_factor_count():
    from factor.schemas import FactorCompareRequest

    base = dict(
        instruments=["BTCUSDT"],
        interval="1h",
        candle_type="spot",
        start_time=None,
        end_time=None,
        method="spearman",
        n_groups=5,
        window=20,
        forward=1,
    )
    with pytest.raises(ValidationError):
        FactorCompareRequest(factor_names=["only_one"], **base)
    with pytest.raises(ValidationError):
        FactorCompareRequest(factor_names=[f"f{i}" for i in range(6)], **base)
