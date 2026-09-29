"""BacktestLoop 特征逐 bar 注入测试：SpyStrategy 记录每根 bar 看到的特征与截面 rank。"""

import numpy as np
import pandas as pd

from axon_bridge import Action
from backtest.backtest_loop import BacktestLoop
from strategy.base import BaseStrategy, StrategyConfig


class SpyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__(StrategyConfig(name="spy", symbol="BTCUSDT"))
        self.records: list[tuple[int, dict, int]] = []

    def on_bar(self, bar: dict, ctx) -> Action:
        rank = int(bar.get("cross_sectional_rank", 0))
        self.records.append((bar["timestamp_ns"], dict(ctx.features), rank))
        return Action(
            action_type="hold",
            confidence=0.0,
            target_position=0.0,
            model_id="spy",
            inference_time_us=0,
        )


def _ohlcv(n: int = 40) -> pd.DataFrame:
    close = 100 + np.arange(n) * 0.5
    hour_ns = 3_600_000_000_000
    return pd.DataFrame(
        {
            "timestamp": [hour_ns * (i + 1) for i in range(n)],
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": [1000.0] * n,
        }
    )


def _feature_frame(df: pd.DataFrame, with_rank: bool = True) -> pd.DataFrame:
    # 前 10 根 NaN（热身），之后给随 bar 递增的因子值
    vals = [np.nan] * 10 + [float(i) for i in range(len(df) - 10)]
    data = {"momentum_5d": vals}
    if with_rank:
        data["cross_sectional_rank"] = [np.nan] * 10 + [1.0] * (len(df) - 10)
    return pd.DataFrame(data, index=df["timestamp"].values)


def test_features_injected_bar_by_bar_and_aligned_by_timestamp():
    df = _ohlcv()
    feat = _feature_frame(df)
    spy = SpyStrategy()

    BacktestLoop(initial_cash=100_000.0).run(spy, df, symbol="BTCUSDT", feature_dataframe=feat)

    assert len(spy.records) == len(df)
    # 热身期：因子不注入、rank 为默认 0
    for _ts, features, rank in spy.records[:10]:
        assert "momentum_5d" not in features
        assert rank == 0
    # 有效行：特征值与帧一致、时间戳精确不错位
    for (ts, features, rank), expected_ts in zip(spy.records[10:], df["timestamp"].tolist()[10:], strict=False):
        assert ts == expected_ts
        assert features["momentum_5d"] == float(feat.loc[expected_ts, "momentum_5d"])
        assert rank == 1


def test_no_feature_dataframe_means_empty_features():
    df = _ohlcv()
    spy = SpyStrategy()
    BacktestLoop(initial_cash=100_000.0).run(spy, df, symbol="BTCUSDT")
    assert all(features == {} for _, features, _ in spy.records)
    assert all(rank == 0 for _, _, rank in spy.records)


def test_feature_frame_without_rank_column():
    df = _ohlcv()
    feat = _feature_frame(df, with_rank=False)
    spy = SpyStrategy()
    BacktestLoop(initial_cash=100_000.0).run(spy, df, symbol="BTCUSDT", feature_dataframe=feat)
    # 因子正常注入；无 rank 列时 bar 不带真实排名（默认 0）
    assert "momentum_5d" in spy.records[-1][1]
    assert spy.records[-1][2] == 0
