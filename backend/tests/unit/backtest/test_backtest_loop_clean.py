"""clean_ohlcv_df 数据质量防御测试（承接旧事件路径清洗契约）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.backtest_loop import clean_ohlcv_df


def _build_df(timestamps=None, **overrides) -> pd.DataFrame:
    if timestamps is None:
        timestamps = pd.date_range("2025-01-01", periods=4, freq="1h")
    base = {
        "timestamp": timestamps,
        "open": [100.0, 101.0, 102.0, 103.0],
        "high": [105.0, 106.0, 107.0, 108.0],
        "low": [99.0, 100.0, 101.0, 102.0],
        "close": [103.0, 104.0, 105.0, 106.0],
        "volume": [1000.0, 2000.0, 3000.0, 4000.0],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def test_passthrough():
    out = clean_ohlcv_df(_build_df())
    assert len(out) == 4
    assert out["close"].tolist() == [103.0, 104.0, 105.0, 106.0]


def test_nan_filled_zero():
    out = clean_ohlcv_df(_build_df(open=[np.nan, 101.0, 102.0, 103.0]))
    assert out["open"].iloc[0] == 0.0


def test_inf_filled_zero():
    out = clean_ohlcv_df(_build_df(high=[105.0, np.inf, 107.0, 108.0]))
    assert np.isfinite(out["high"]).all()
    assert out["high"].iloc[1] == 0.0


def test_sorted():
    out = clean_ohlcv_df(
        _build_df(
            timestamps=[
                "2025-01-01 03:00:00",
                "2025-01-01 01:00:00",
                "2025-01-01 02:00:00",
                "2025-01-01 00:00:00",
            ]
        )
    )
    assert out.index.is_monotonic_increasing


def test_dedup_keep_last():
    out = clean_ohlcv_df(
        _build_df(
            timestamps=["2025-01-01 00:00:00", "2025-01-01 00:00:00", "2025-01-01 01:00:00", "2025-01-01 02:00:00"],
            open=[100.0, 101.0, 102.0, 103.0],
        )
    )
    assert len(out) == 3
    assert out["open"].iloc[0] == 101.0


def test_column_names_case_insensitive():
    df = _build_df().rename(columns={"open": "OPEN", "close": "CLOSE"})
    out = clean_ohlcv_df(df)
    assert "open" in out.columns and "close" in out.columns
