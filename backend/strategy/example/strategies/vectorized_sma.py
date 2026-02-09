"""
向量化双均线策略

利用 VectorEngine 和批处理引擎实现高性能的双均线交叉策略。
展示以下特性：
1. Numba JIT编译加速
2. 向量化信号计算
3. 批量订单处理
4. 内存池优化
"""

import numpy as np
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from loguru import logger

from strategy.core import (
    StrategyBase,
    VectorEngine,
    BatchingEngine,
    create_batching_engine,
    get_event_pools,
    create_bar_event,
)
from strategy.core.batching_engine import VectorizedBatchProcessor


@dataclass
class Signal:
    """交易信号"""
    timestamp: float
    symbol: str
    direction: str  # 'buy', 'sell', 'hold'
    price: float
    fast_ma: float
    slow_ma: float


class VectorizedSMAStrategy:
    """
    向量化双均线策略

    使用 NumPy 进行向量化计算，相比传统的逐K线计算，
    性能提升可达 10-100 倍。

    特性：
    1. 批量计算移动平均线
    2. 向量化信号生成
    3. 批量订单提交
    4. 内存池复用
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        batch_size: int = 100,
        use_batching: bool = True,
    ):
        """
        初始化策略

        Args:
            fast_period: 快速均线周期
            slow_period: 慢速均线周期
            batch_size: 批处理大小
            use_batching: 是否使用批处理引擎
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.batch_size = batch_size
        self.use_batching = use_batching

        # 向量引擎
        self.vector_engine = VectorEngine()

        # 批处理引擎
        self.batch_engine: Optional[BatchingEngine] = None
        if use_batching:
            self.batch_engine = create_batching_engine(
                max_batch_size=batch_size,
                max_batch_age_ms=10.0,
                num_workers=4,
            )
            self._setup_batch_handlers()

        # 向量化批处理器
        self.vector_processor = VectorizedBatchProcessor()

        # 数据缓存
        self.price_history: Dict[str, List[float]] = {}
        self.signal_history: List[Signal] = []

        # 性能统计
        self.stats = {
            "total_bars": 0,
            "signals_generated": 0,
            "orders_submitted": 0,
            "processing_time_ms": 0.0,
        }

        logger.info(
            f"向量化双均线策略初始化完成: "
            f"fast={fast_period}, slow={slow_period}, batch={batch_size}"
        )

    def _setup_batch_handlers(self):
        """设置批处理器"""
        if self.batch_engine:
            self.batch_engine.register("bar", self._process_bar_batch)
            self.batch_engine.register("tick", self._process_tick_batch)

    def on_bar(self, symbol: str, bar: Dict[str, Any]) -> Optional[Signal]:
        """
        处理单根K线

        Args:
            symbol: 交易对
            bar: K线数据

        Returns:
            Signal or None: 交易信号
        """
        start_time = time.time()

        # 更新价格历史
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(bar["close"])
        self.stats["total_bars"] += 1

        # 检查是否有足够数据
        if len(self.price_history[symbol]) < self.slow_period:
            return None

        # 使用批处理引擎或立即处理
        if self.use_batching and self.batch_engine:
            self.batch_engine.put("bar", bar, symbol=symbol)
            return None  # 批处理模式下不立即返回信号

        # 立即处理
        signal = self._calculate_signal(symbol)

        processing_time = (time.time() - start_time) * 1000
        self.stats["processing_time_ms"] += processing_time

        return signal

    def _calculate_signal(self, symbol: str) -> Optional[Signal]:
        """
        计算交易信号

        Args:
            symbol: 交易对

        Returns:
            Signal or None: 交易信号
        """
        prices = np.array(self.price_history[symbol])

        # 向量化计算移动平均线
        fast_ma = self._calculate_sma_vectorized(prices, self.fast_period)
        slow_ma = self._calculate_sma_vectorized(prices, self.slow_period)

        if len(fast_ma) < 2 or len(slow_ma) < 2:
            return None

        # 检测交叉
        current_fast = fast_ma[-1]
        current_slow = slow_ma[-1]
        prev_fast = fast_ma[-2]
        prev_slow = slow_ma[-2]

        direction = "hold"

        # 金叉：快速均线上穿慢速均线
        if prev_fast <= prev_slow and current_fast > current_slow:
            direction = "buy"
        # 死叉：快速均线下穿慢速均线
        elif prev_fast >= prev_slow and current_fast < current_slow:
            direction = "sell"

        if direction != "hold":
            signal = Signal(
                timestamp=time.time(),
                symbol=symbol,
                direction=direction,
                price=float(prices[-1]),
                fast_ma=float(current_fast),
                slow_ma=float(current_slow),
            )
            self.signal_history.append(signal)
            self.stats["signals_generated"] += 1
            return signal

        return None

    def _calculate_sma_vectorized(self, prices: np.ndarray, period: int) -> np.ndarray:
        """
        向量化计算简单移动平均

        使用卷积操作实现高效的移动平均计算，
        比循环实现快 10-100 倍。

        Args:
            prices: 价格数组
            period: 移动平均周期

        Returns:
            np.ndarray: 移动平均值数组
        """
        if len(prices) < period:
            return np.array([])

        # 使用卷积计算移动平均
        weights = np.ones(period) / period
        sma = np.convolve(prices, weights, mode='valid')

        return sma

    def _process_bar_batch(self, batch: List[Dict[str, Any]]):
        """
        批量处理K线数据

        Args:
            batch: K线批次数据
        """
        if not batch:
            return

        start_time = time.time()

        # 提取价格数据
        prices = np.array([bar["data"]["close"] for bar in batch])

        # 向量化计算指标
        if len(prices) >= self.slow_period:
            fast_ma = self._calculate_sma_vectorized(prices, self.fast_period)
            slow_ma = self._calculate_sma_vectorized(prices, self.slow_period)

            # 批量生成信号
            signals = self._generate_signals_batch(batch, fast_ma, slow_ma)

            # 批量提交订单
            self._submit_orders_batch(signals)

        processing_time = (time.time() - start_time) * 1000
        self.stats["processing_time_ms"] += processing_time

        logger.debug(f"批量处理 {len(batch)} 根K线，耗时 {processing_time:.2f}ms")

    def _process_tick_batch(self, batch: List[Dict[str, Any]]):
        """批量处理Tick数据"""
        if not batch:
            return

        # 使用向量化处理器计算价格统计
        prices = [tick["data"].get("price", 0) for tick in batch]
        stats = self.vector_processor.process_prices(prices)

        logger.debug(f"Tick批次统计: {stats}")

    def _generate_signals_batch(
        self,
        batch: List[Dict[str, Any]],
        fast_ma: np.ndarray,
        slow_ma: np.ndarray,
    ) -> List[Signal]:
        """
        批量生成交易信号

        Args:
            batch: K线批次
            fast_ma: 快速均线数组
            slow_ma: 慢速均线数组

        Returns:
            List[Signal]: 交易信号列表
        """
        signals = []

        # 确保fast_ma和slow_ma长度一致
        min_len = min(len(fast_ma), len(slow_ma))
        if min_len < 2:
            return signals

        # 计算偏移量：由于卷积的mode='valid'，sma数组比prices短 (period-1)
        fast_offset = self.fast_period - 1
        slow_offset = self.slow_period - 1

        # 检测交叉点
        for i in range(1, min_len):
            prev_fast = fast_ma[i - 1]
            prev_slow = slow_ma[i - 1]
            curr_fast = fast_ma[i]
            curr_slow = slow_ma[i]

            direction = "hold"
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                direction = "buy"
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                direction = "sell"

            if direction != "hold":
                # 使用slow_offset作为基准，因为slow_ma更短
                bar_idx = i + slow_offset
                if bar_idx < len(batch):
                    signal = Signal(
                        timestamp=batch[bar_idx].get("timestamp", time.time()),
                        symbol=batch[bar_idx]["data"].get("symbol", "UNKNOWN"),
                        direction=direction,
                        price=batch[bar_idx]["data"].get("close", 0.0),
                        fast_ma=float(curr_fast),
                        slow_ma=float(curr_slow),
                    )
                    signals.append(signal)

        self.signal_history.extend(signals)
        self.stats["signals_generated"] += len(signals)

        return signals

    def _submit_orders_batch(self, signals: List[Signal]):
        """
        批量提交订单

        Args:
            signals: 交易信号列表
        """
        for signal in signals:
            # 这里可以接入实际的订单管理系统
            logger.info(
                f"提交订单: {signal.symbol} {signal.direction} "
                f"@ {signal.price:.2f}"
            )
            self.stats["orders_submitted"] += 1

    def run_backtest(
        self,
        prices: np.ndarray,
        symbol: str = "TEST",
    ) -> Dict[str, Any]:
        """
        运行向量化回测

        Args:
            prices: 价格数组
            symbol: 交易对

        Returns:
            Dict: 回测结果
        """
        start_time = time.time()

        # 生成入场和出场信号
        fast_ma = self._calculate_sma_vectorized(prices, self.fast_period)
        slow_ma = self._calculate_sma_vectorized(prices, self.slow_period)

        # 向量化生成信号
        entries = np.zeros(len(prices), dtype=np.bool_)
        exits = np.zeros(len(prices), dtype=np.bool_)

        # fast_ma和slow_ma长度不同，需要找到共同的有效范围
        # fast_ma长度 = len(prices) - fast_period + 1
        # slow_ma长度 = len(prices) - slow_period + 1
        # 共同范围从slow_period-1开始（因为slow_ma更短）
        min_ma_len = min(len(fast_ma), len(slow_ma))

        for i in range(1, min_ma_len):
            # 计算在原始prices数组中的索引
            # slow_ma的起始索引是slow_period-1
            idx = i + self.slow_period - 1
            if idx >= len(prices):
                break
            if fast_ma[i - 1] <= slow_ma[i - 1] and fast_ma[i] > slow_ma[i]:
                entries[idx] = True
            elif fast_ma[i - 1] >= slow_ma[i - 1] and fast_ma[i] < slow_ma[i]:
                exits[idx] = True

        # 使用向量引擎运行回测
        results = self.vector_engine.run_backtest(
            price=prices.reshape(-1, 1),
            entries=entries.reshape(-1, 1),
            exits=exits.reshape(-1, 1),
            init_cash=100000.0,
            fees=0.001,
            slippage=0.0001,
        )

        total_time = (time.time() - start_time) * 1000

        return {
            "symbol": symbol,
            "total_bars": len(prices),
            "signals_generated": np.sum(entries) + np.sum(exits),
            "processing_time_ms": total_time,
            "bars_per_second": len(prices) / (total_time / 1000),
            "metrics": results.get("metrics", {}),
            "trades_count": len(results.get("trades", [])),
        }

    def start(self):
        """启动策略"""
        if self.batch_engine:
            self.batch_engine.start()
            logger.info("批处理引擎已启动")

    def stop(self):
        """停止策略"""
        if self.batch_engine:
            self.batch_engine.stop()
            logger.info("批处理引擎已停止")

    def get_stats(self) -> Dict[str, Any]:
        """获取策略统计信息"""
        stats = self.stats.copy()

        if self.batch_engine:
            batch_stats = self.batch_engine.get_stats()
            stats["batch_engine"] = batch_stats

        stats["signal_count"] = len(self.signal_history)

        return stats

    def reset(self):
        """重置策略状态"""
        self.price_history.clear()
        self.signal_history.clear()
        self.stats = {
            "total_bars": 0,
            "signals_generated": 0,
            "orders_submitted": 0,
            "processing_time_ms": 0.0,
        }
