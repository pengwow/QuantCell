"""共享测试数据 fixture 消费冒烟测试。

评估报告 5.1 指出 tests/data/sample_btcusdt_1h.csv 处于 0 引用闲置状态。
本文件让 conftest 的 3 个共享 fixture 真正进入测试流水线:
- trending_kline / flat_kline: 合成数据的方向性与不变量
- sample_btcusdt_1h: 真实样本只做方向/有限性断言,不做精确 PnL 断言
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_OHLCV = ["open", "high", "low", "close", "volume"]


def test_trending_kline_shape_and_direction(trending_kline: pd.DataFrame) -> None:
    assert isinstance(trending_kline.index, pd.DatetimeIndex)
    assert len(trending_kline) == 200
    assert list(trending_kline.columns) == _OHLCV
    # 单边上涨:close 单调递增
    assert trending_kline["close"].is_monotonic_increasing
    assert np.isfinite(trending_kline[_OHLCV].to_numpy()).all()


def test_flat_kline_flat_price_invariants(flat_kline: pd.DataFrame) -> None:
    assert len(flat_kline) == 180
    assert (flat_kline["close"] == 100.0).all()
    # OHLC 几何不变量:high 不低于 close,low 不高于 close
    assert (flat_kline["high"] >= flat_kline["close"]).all()
    assert (flat_kline["low"] <= flat_kline["close"]).all()


def test_sample_btcusdt_1h_real_data_loaded(sample_btcusdt_1h: pd.DataFrame) -> None:
    """真实 CSV 样本接入:100 根 1h K 线,DatetimeIndex 单调递增,呈上涨趋势,数据有限。"""
    assert len(sample_btcusdt_1h) == 100
    assert isinstance(sample_btcusdt_1h.index, pd.DatetimeIndex)
    assert sample_btcusdt_1h.index.is_monotonic_increasing
    closes = sample_btcusdt_1h["close"]
    # 样本为 42000 -> 67000+ 上涨趋势,断言明显涨幅与数据完整
    assert closes.iloc[-1] > closes.iloc[0] * 1.2
    assert np.isfinite(sample_btcusdt_1h[_OHLCV].to_numpy()).all()
