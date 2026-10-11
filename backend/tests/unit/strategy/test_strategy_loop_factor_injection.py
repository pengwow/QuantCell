"""StrategyLoop 因子注入端到端测试。

验证：启动时 fetch_ohlcv → KlineBuffer，逐 tick 更新，FactorInjector 计算因子，
注入 StrategyContext.features，策略通过 ctx.get_feature 读取。
"""

from __future__ import annotations

import time

import pytest

from strategy.base import StrategyConfig
from strategy.loop import StrategyLoop
from strategy.templates.factor_timing import FactorTiming


class FakeAdapter:
    """模拟适配器：支持 get_ticker + fetch_ohlcv。"""

    def __init__(self, ticker_last: float = 65000.0):
        self._ticker_last = ticker_last
        self.orders: list[dict] = []

    def connect(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, symbols):
        pass

    def get_ticker(self, symbol):
        return {
            "open": self._ticker_last,
            "high": self._ticker_last + 100,
            "low": self._ticker_last - 100,
            "last": self._ticker_last,
            "volume": 1000.0,
        }

    def place_order(self, order_dict):
        self.orders.append(order_dict)
        return {"order_id": "test_123", "status": "accepted"}

    def fetch_ohlcv(self, symbol, interval, limit):
        """返回 10 根历史 K 线（毫秒时间戳）。"""
        base_ts = int(time.time() * 1000)
        return [
            {
                "timestamp": base_ts - (10 - i) * 3_600_000,
                "open": 60000.0 + i * 100,
                "high": 60100.0 + i * 100,
                "low": 59900.0 + i * 100,
                "close": 60050.0 + i * 100,
                "volume": 100.0,
            }
            for i in range(10)
        ]


def test_factor_injection_ma5d():
    """验证因子注入：ma_5d 因子值正确注入 ctx.features。"""
    adapter = FakeAdapter(ticker_last=65000.0)

    # FactorTiming 策略：ma_5d >= 0 买入
    config = StrategyConfig(
        name="factor_timing_test",
        symbol="BTCUSDT",
        params={
            "factor_name": "ma_5d",
            "buy_threshold": 0.0,
            "sell_threshold": -1.0,
            "position_limit": 0.1,
        },
    )
    strategy = FactorTiming(config)

    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        factor_names=["ma_5d"],
        timeframe="1h",
        kline_buffer_len=100,
    )

    # 手动执行一轮（不启动线程）
    loop._adapter = adapter
    loop._init_factor_injection()
    assert loop._kline_buffer is not None
    assert loop._kline_buffer.len() == 10  # fetch_ohlcv 返回 10 根

    # 模拟一轮 tick
    ticker = adapter.get_ticker("BTCUSDT")
    close_price = float(ticker["last"])
    timestamp_ns = int(time.time() * 1_000_000_000)
    bar = {
        "open": float(ticker["open"]),
        "high": float(ticker["high"]),
        "low": float(ticker["low"]),
        "close": close_price,
        "volume": float(ticker["volume"]),
        "symbol": "BTCUSDT",
        "timestamp_ns": timestamp_ns,
    }

    ctx = loop._build_ctx(bar, timestamp_ns, close_price)
    # ma_5d 应该被计算并注入
    assert "ma_5d" in ctx.features
    assert ctx.features["ma_5d"] > 0  # 价格上行趋势，MA5 > 0

    # 策略应该能读到因子值并产生 buy 信号
    action = strategy.on_bar(bar, ctx)
    assert str(action.action_type) == "buy"


def test_factor_injection_disabled_when_no_factors():
    """未配置 factor_names 时，KlineBuffer 和 FactorInjector 不初始化。"""
    adapter = FakeAdapter()
    config = StrategyConfig(name="test", symbol="BTCUSDT", params={})
    strategy = FactorTiming(config)

    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
    )
    loop._init_factor_injection()
    assert loop._kline_buffer is None
    assert loop._factor_injector is None


def test_factor_injection_falls_back_on_ohlcv_failure():
    """fetch_ohlcv 失败时，因子注入退化为无历史数据模式。"""

    class FailingOhlcvAdapter(FakeAdapter):
        def fetch_ohlcv(self, symbol, interval, limit):
            raise RuntimeError("network error")

    adapter = FailingOhlcvAdapter()
    config = StrategyConfig(
        name="test",
        symbol="BTCUSDT",
        params={"factor_name": "ma_5d"},
    )
    strategy = FactorTiming(config)

    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        factor_names=["ma_5d"],
    )
    # 不应抛异常，KlineBuffer 仍创建但为空
    loop._init_factor_injection()
    assert loop._kline_buffer is not None
    assert loop._kline_buffer.is_empty()
