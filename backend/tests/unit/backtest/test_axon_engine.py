# -*- coding: utf-8 -*-
"""AxonBacktestEngine 单元测试

本测试**不 mock 任何 axon_quant 内部组件**——这是修复 'unsupported event type: market_data'
的关键。Mock 会让 bug 隐藏，但生产环境会暴露。真实测比 mock 测慢一点，但能保护接口契约。

测试设计：
- TestUnitBehavior: 测试参数校验、API 存在性
- TestE2EBehavior: 测试真实 _AxonBacktestEngine 集成（来自 tests/integration 的回归）
- TestBackwardCompatibility: 测试废弃方法抛 NotImplementedError
"""
import math
import pandas as pd
import pytest


def _make_series(n: int = 30, start: float = 100.0) -> pd.DataFrame:
    """生成测试用 K 线（Binance schema：大写列名）"""
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    closes = [start]
    for i in range(1, n):
        closes.append(closes[-1] * (1 + 0.001 * math.sin(i / 3.0)))
    close_series = pd.Series(closes)
    return pd.DataFrame({
        "open": close_series.values,
        "high": close_series.values * 1.001,
        "low": close_series.values * 0.999,
        "close": close_series.values,
        "volume": [1000.0] * n,
    }, index=idx)


class TestUnitBehavior:
    """单元行为测试（不涉及真实 axon_quant）"""

    def test_creation_with_config(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        assert engine._config["initial_capital"] == 100000.0
        assert engine._is_initialized is False

    def test_creation_without_config(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine()
        assert engine._config == {}

    def test_initialize_without_axon_raises(self):
        """axon_quant 未安装时应抛 ImportError"""
        from backtest import engines as _engines_mod
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(_engines_mod.axon_engine, "AXON_AVAILABLE", False)
            # 重新创建实例
            engine = _engines_mod.axon_engine.AxonBacktestEngine({"initial_capital": 100000.0})
            with pytest.raises(ImportError, match="axon_quant 未安装"):
                engine.initialize()

    def test_initialize_with_negative_capital_raises(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": -1})
        with pytest.raises(ValueError, match="initial_capital"):
            engine.initialize()

    def test_run_with_strategy_without_init_raises(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        with pytest.raises(RuntimeError, match="未初始化"):
            engine.run_with_strategy(strategy=None, data=pd.DataFrame(), symbol="BTCUSDT")

    def test_run_with_strategy_with_empty_data_raises(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        engine.initialize()
        with pytest.raises(ValueError, match="data 不能为空"):
            engine.run_with_strategy(strategy=None, data=pd.DataFrame(), symbol="BTCUSDT")


class TestBackwardCompatibility:
    """废弃方法应抛 NotImplementedError，明确告知正确用法"""

    def test_add_data_raises_with_helpful_message(self):
        """add_data 是 bug 源头（push market_data 事件被 axon_quant 拒绝）"""
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        engine.initialize()
        df = _make_series(n=5)
        with pytest.raises(NotImplementedError) as exc_info:
            engine.add_data(df, "BTCUSDT")
        # 错误信息应告知正确用法
        assert "run_with_strategy" in str(exc_info.value)
        assert "market_data" in str(exc_info.value)

    def test_submit_order_raises_with_helpful_message(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        engine.initialize()
        with pytest.raises(NotImplementedError, match=r"on_bar"):
            engine.submit_order({}, 0)

    def test_run_raises_with_helpful_message(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100000.0})
        engine.initialize()
        with pytest.raises(NotImplementedError, match="run_with_strategy"):
            engine.run()


@pytest.mark.integration
class TestE2EBehavior:
    """真实 _AxonBacktestEngine 集成测试"""

    def test_full_backtest_flow_via_run_with_strategy(self):
        """端到端：构造数据 + 策略 + 跑出 PnL"""
        from backtest.engines.axon_engine import AxonBacktestEngine
        from strategy.core.bar import Bar
        from strategy.core.order import Order, OrderSide
        from strategy.core.unified_strategy import StrategyContext, UnifiedStrategy

        class BuyOnceStrategy(UnifiedStrategy):
            def __init__(self):
                super().__init__()
                self._done = False

            def on_bar(self, bar: Bar, ctx: StrategyContext):
                if self._done:
                    return []
                self._done = True
                return [Order(symbol=bar.symbol, side=OrderSide.BUY,
                              quantity=0.1, price=bar.close)]

        engine = AxonBacktestEngine({"initial_capital": 100_000.0})
        engine.initialize()

        df = _make_series(n=30)
        strategy = BuyOnceStrategy()

        result = engine.run_with_strategy(strategy=strategy, data=df, symbol="BTCUSDT")

        # 验证返回字段
        assert "final_nav" in result
        assert "total_pnl" in result
        assert "orders_accepted" in result
        assert "fills" in result
        # 实际产生了一笔订单
        assert result["orders_accepted"] >= 1

    def test_cleanup_marks_uninitialized(self):
        from backtest.engines.axon_engine import AxonBacktestEngine
        engine = AxonBacktestEngine({"initial_capital": 100_000.0})
        engine.initialize()
        assert engine._is_initialized is True
        engine.cleanup()
        assert engine._is_initialized is False
