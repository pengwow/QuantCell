"""FactorFeatureBuilder 单测：合成 K 线，不读真实 parquet。"""

import numpy as np
import pandas as pd
import pytest

from factor.engine import FactorExpressionError, _timestamps_to_datetime
from factor.features import attach_feature_frames, build_feature_frames


def _raw(n: int = 60, seed: int = 1, start_ns: int = 1_704_067_200_000_000_000) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    hour_ns = 3_600_000_000_000
    return pd.DataFrame(
        {
            "timestamp": [start_ns + i * hour_ns for i in range(n)],
            "open": close + rng.normal(0, 0.2, n),
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": rng.uniform(100, 1000, n),
            "quote_volume": close * rng.uniform(100, 1000, n),
        }
    )


class FakeProvider:
    def __init__(self, raw_map):
        self._raw_map = raw_map

    def get_kline_data(self, symbol, interval, candle_type, start, end, columns=None):
        return self._raw_map[symbol]


def _provider(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    return FakeProvider({s: _raw(seed=abs(hash(s)) % 100) for s in symbols})


def test_single_symbol_frame_columns_and_index():
    frames = build_feature_frames(
        ["momentum_5d", "rsi_14d"],
        ["BTCUSDT"],
        "1h",
        "spot",
        None,
        None,
        provider=_provider(("BTCUSDT",)),
    )
    assert set(frames) == {"BTCUSDT"}
    frame = frames["BTCUSDT"]
    assert list(frame.columns) == ["momentum_5d", "rsi_14d"]
    # 单品种不产生截面 rank
    assert "cross_sectional_rank" not in frame.columns
    # 索引归一为 DatetimeIndex（与回测 K 线 normalize 后形态一致），与 K 线等长同序
    raw = _raw(seed=abs(hash("BTCUSDT")) % 100)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert len(frame) == len(raw)
    pd.testing.assert_index_equal(frame.index, pd.DatetimeIndex(_timestamps_to_datetime(raw["timestamp"])))


def test_warmup_values_are_nan():
    frames = build_feature_frames(
        ["momentum_5d"],
        ["BTCUSDT"],
        "1h",
        "spot",
        None,
        None,
        provider=_provider(("BTCUSDT",)),
    )
    s = frames["BTCUSDT"]["momentum_5d"]
    assert s.iloc[:5].isna().all()
    assert s.iloc[5:].notna().any()


def test_factor_value_matches_direct_eval():
    from factor.engine import evaluate_factor

    raw = _raw()
    provider = FakeProvider({"BTCUSDT": raw})
    frames = build_feature_frames(["momentum_5d"], ["BTCUSDT"], "1h", "spot", None, None, provider=provider)
    expected = evaluate_factor("momentum_5d", raw, {})
    pd.testing.assert_series_equal(
        frames["BTCUSDT"]["momentum_5d"].reset_index(drop=True),
        expected.reset_index(drop=True),
        check_names=False,
    )


def test_cross_section_rank_is_one_for_highest_factor():
    provider = _provider()
    frames = build_feature_frames(
        ["momentum_5d"],
        ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        "1h",
        "spot",
        None,
        None,
        rank_factor="momentum_5d",
        provider=provider,
    )
    for frame in frames.values():
        assert "cross_sectional_rank" in frame.columns
    # 取一个热身已结束、三品种都有值的时间点
    ts = frames["BTCUSDT"].index[40]
    vals = {s: frames[s].loc[ts, "momentum_5d"] for s in frames}
    ranks = {s: frames[s].loc[ts, "cross_sectional_rank"] for s in frames}
    top = max(vals, key=vals.get)
    assert ranks[top] == 1.0
    assert sorted(v for v in ranks.values() if pd.notna(v)) == [1.0, 2.0, 3.0]


def test_rank_nan_during_warmup():
    frames = build_feature_frames(
        ["momentum_5d"],
        ["BTCUSDT", "ETHUSDT"],
        "1h",
        "spot",
        None,
        None,
        rank_factor="momentum_5d",
        provider=_provider(),
    )
    assert frames["BTCUSDT"]["cross_sectional_rank"].iloc[:5].isna().all()


def test_rank_factor_not_in_list_raises():
    with pytest.raises(FactorExpressionError):
        build_feature_frames(
            ["momentum_5d"],
            ["BTCUSDT", "ETHUSDT"],
            "1h",
            "spot",
            None,
            None,
            rank_factor="ghost_factor",
            provider=_provider(),
        )


def test_unknown_and_unsupported_factor_raise():
    with pytest.raises(FactorExpressionError):
        build_feature_frames(["ghost"], ["BTCUSDT"], "1h", "spot", None, None, provider=_provider(("BTCUSDT",)))
    with pytest.raises(FactorExpressionError):
        build_feature_frames(["pe"], ["BTCUSDT"], "1h", "spot", None, None, provider=_provider(("BTCUSDT",)))


def test_custom_factor_expression():
    frames = build_feature_frames(
        ["my_spread"],
        ["BTCUSDT"],
        "1h",
        "spot",
        None,
        None,
        provider=_provider(("BTCUSDT",)),
        custom_expressions={"my_spread": "close - open"},
    )
    raw = _raw(seed=abs(hash("BTCUSDT")) % 100)
    assert np.allclose(frames["BTCUSDT"]["my_spread"].dropna(), (raw["close"] - raw["open"]).dropna())


def test_attach_feature_frames_backfills_loaded_data():
    frames = {"BTCUSDT": pd.DataFrame({"momentum_5d": [0.1]}, index=[1])}
    loaded = {
        "BTCUSDT_1h": {"data": pd.DataFrame(), "features": None, "feature_dataframe": None},
        "ETHUSDT_1h": {"data": pd.DataFrame(), "features": None, "feature_dataframe": None},
    }
    attach_feature_frames(loaded, frames)
    assert loaded["BTCUSDT_1h"]["feature_dataframe"] is frames["BTCUSDT"]
    assert loaded["ETHUSDT_1h"]["feature_dataframe"] is None
