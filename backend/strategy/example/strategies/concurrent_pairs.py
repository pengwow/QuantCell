"""
并发多交易对策略

利用 ConcurrentEventEngine 实现多交易对的并行处理。
展示以下特性：
1. 交易对分片处理
2. 一致性哈希路由
3. 每交易对独立队列
4. 符号级别的并发控制
"""

import time
import random
import numpy as np
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger

from strategy.core import (
    ConcurrentEventEngine,
    create_concurrent_engine,
)
from strategy.core.concurrent_event_engine import SymbolEvent, EventPriority


@dataclass
class TradeSignal:
    """交易信号"""
    timestamp: float
    symbol: str
    direction: str
    price: float
    confidence: float
    shard_id: int = 0


@dataclass
class SymbolState:
    """交易对状态"""
    symbol: str
    prices: List[float] = field(default_factory=list)
    position: float = 0.0
    entry_price: float = 0.0
    signals: List[TradeSignal] = field(default_factory=list)
    last_update: float = field(default_factory=time.time)


class ConcurrentPairsStrategy:
    """
    并发多交易对策略

    使用 ConcurrentEventEngine 将不同交易对的事件路由到不同的分片，
    实现真正的并行处理。

    特性：
    1. 交易对分片：16-64个分片并行处理
    2. 一致性哈希：确保同一交易对始终路由到同一分片
    3. 独立队列：每个分片有独立的事件队列
    4. 符号级并发：不同交易对完全并行处理
    """

    def __init__(
        self,
        symbols: List[str],
        num_shards: int = 16,
        lookback_period: int = 20,
        volatility_threshold: float = 0.02,
    ):
        """
        初始化策略

        Args:
            symbols: 交易对列表
            num_shards: 分片数量
            lookback_period: 回看周期
            volatility_threshold: 波动率阈值
        """
        self.symbols = symbols
        self.num_shards = num_shards
        self.lookback_period = lookback_period
        self.volatility_threshold = volatility_threshold

        # 创建并发事件引擎
        self.engine = create_concurrent_engine(
            num_shards=num_shards,
            max_queue_size_per_shard=10000,
            enable_backpressure=True,
        )

        # 注册事件处理器
        self._setup_handlers()

        # 交易对状态
        self.symbol_states: Dict[str, SymbolState] = {
            symbol: SymbolState(symbol=symbol)
            for symbol in symbols
        }

        # 性能统计
        self.stats = {
            "total_events": 0,
            "events_by_symbol": defaultdict(int),
            "signals_generated": 0,
            "processing_time_ms": 0.0,
        }

        logger.info(
            f"并发多交易对策略初始化完成: "
            f"symbols={len(symbols)}, shards={num_shards}"
        )

    def _setup_handlers(self):
        """设置事件处理器"""
        self.engine.register("tick", self._handle_tick)
        self.engine.register("bar", self._handle_bar)
        self.engine.register("signal", self._handle_signal)

    def _handle_tick(self, data: Dict[str, Any]):
        """处理Tick事件"""
        start_time = time.time()

        symbol = data.get("symbol", "UNKNOWN")
        price = data.get("price", 0.0)

        # 更新交易对状态
        if symbol in self.symbol_states:
            state = self.symbol_states[symbol]
            state.prices.append(price)
            state.last_update = time.time()

            # 保持价格历史在合理范围内
            if len(state.prices) > self.lookback_period * 2:
                state.prices = state.prices[-self.lookback_period:]

        self.stats["total_events"] += 1
        self.stats["events_by_symbol"][symbol] += 1

        processing_time = (time.time() - start_time) * 1000
        self.stats["processing_time_ms"] += processing_time

    def _handle_bar(self, data: Dict[str, Any]):
        """处理K线事件"""
        start_time = time.time()

        symbol = data.get("symbol", "UNKNOWN")
        bar = data.get("bar", {})

        if symbol in self.symbol_states:
            state = self.symbol_states[symbol]
            close_price = bar.get("close", 0.0)
            state.prices.append(close_price)

            # 生成交易信号
            signal = self._generate_signal(symbol, state)
            if signal:
                state.signals.append(signal)
                self.stats["signals_generated"] += 1

        self.stats["total_events"] += 1
        self.stats["events_by_symbol"][symbol] += 1

        processing_time = (time.time() - start_time) * 1000
        self.stats["processing_time_ms"] += processing_time

    def _handle_signal(self, data: Dict[str, Any]):
        """处理信号事件"""
        signal = data.get("signal")
        if signal:
            logger.info(
                f"处理信号: {signal.symbol} {signal.direction} "
                f"@ {signal.price:.4f} (shard={signal.shard_id})"
            )

    def _generate_signal(self, symbol: str, state: SymbolState) -> Optional[TradeSignal]:
        """
        生成交易信号

        基于波动率突破策略：
        - 当价格突破近期波动区间时产生信号
        """
        if len(state.prices) < self.lookback_period:
            return None

        prices = np.array(state.prices[-self.lookback_period:])

        # 计算波动率
        if len(prices) < 2:
            return None

        returns = np.diff(prices) / prices[:-1]
        if len(returns) == 0:
            return None

        volatility = np.std(returns)

        # 计算价格位置
        current_price = prices[-1]
        price_mean = np.mean(prices)
        price_std = np.std(prices)

        # 生成信号
        direction = "hold"
        confidence = 0.0

        if volatility > self.volatility_threshold:
            # 高波动环境
            z_score = (current_price - price_mean) / (price_std + 1e-10)

            if z_score > 1.5:
                direction = "sell"
                confidence = min(abs(z_score) / 3.0, 1.0)
            elif z_score < -1.5:
                direction = "buy"
                confidence = min(abs(z_score) / 3.0, 1.0)

        if direction != "hold":
            # 获取分片ID
            shard_id = self.engine._get_shard_id(symbol)

            return TradeSignal(
                timestamp=time.time(),
                symbol=symbol,
                direction=direction,
                price=current_price,
                confidence=confidence,
                shard_id=shard_id,
            )

        return None

    def on_tick(self, symbol: str, price: float, volume: float = 0.0):
        """
        处理Tick数据

        Args:
            symbol: 交易对
            price: 价格
            volume: 成交量
        """
        data = {
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "timestamp": time.time(),
        }

        # 根据信号重要性设置优先级
        priority = EventPriority.NORMAL
        if symbol in self.symbol_states:
            state = self.symbol_states[symbol]
            if state.position != 0:  # 有持仓时提高优先级
                priority = EventPriority.HIGH

        self.engine.put(
            event_type="tick",
            data=data,
            symbol=symbol,
            priority=priority,
        )

    def on_bar(self, symbol: str, bar: Dict[str, Any]):
        """
        处理K线数据

        Args:
            symbol: 交易对
            bar: K线数据
        """
        data = {
            "symbol": symbol,
            "bar": bar,
            "timestamp": time.time(),
        }

        self.engine.put(
            event_type="bar",
            data=data,
            symbol=symbol,
            priority=EventPriority.NORMAL,
        )

    def submit_signal(self, signal: TradeSignal):
        """
        提交交易信号

        Args:
            signal: 交易信号
        """
        data = {"signal": signal}

        # 信号使用高优先级
        self.engine.put(
            event_type="signal",
            data=data,
            symbol=signal.symbol,
            priority=EventPriority.HIGH,
        )

    def simulate_market_data(
        self,
        duration_seconds: float = 10.0,
        tick_rate: float = 100.0,
    ) -> Dict[str, Any]:
        """
        模拟市场数据流

        Args:
            duration_seconds: 模拟时长（秒）
            tick_rate: 每秒Tick数

        Returns:
            Dict: 模拟结果统计
        """
        start_time = time.time()
        tick_count = 0

        logger.info(
            f"开始模拟市场数据: duration={duration_seconds}s, "
            f"rate={tick_rate}ticks/s, symbols={len(self.symbols)}"
        )

        while time.time() - start_time < duration_seconds:
            # 为每个交易对生成Tick
            for symbol in self.symbols:
                # 模拟价格变动
                base_price = 100.0 + random.gauss(0, 5)
                price = base_price * (1 + random.gauss(0, 0.001))
                volume = random.uniform(100, 10000)

                self.on_tick(symbol, price, volume)
                tick_count += 1

            # 控制发送速率
            time.sleep(1.0 / tick_rate)

        total_time = time.time() - start_time

        return {
            "total_ticks": tick_count,
            "duration_seconds": total_time,
            "ticks_per_second": tick_count / total_time,
            "symbols": len(self.symbols),
            "shards": self.num_shards,
        }

    def start(self):
        """启动策略"""
        self.engine.start()
        logger.info("并发事件引擎已启动")

    def stop(self):
        """停止策略"""
        self.engine.stop()
        logger.info("并发事件引擎已停止")

    def get_stats(self) -> Dict[str, Any]:
        """获取策略统计信息"""
        stats = self.stats.copy()

        # 添加引擎统计
        engine_stats = self.engine.get_stats()
        stats["engine"] = engine_stats

        # 添加各分片统计
        shard_stats = []
        for i in range(self.num_shards):
            shard_stats.append(self.engine.get_shard_stats(i))
        stats["shards"] = shard_stats

        # 添加交易对统计
        symbol_stats = {}
        for symbol, state in self.symbol_states.items():
            symbol_stats[symbol] = {
                "price_count": len(state.prices),
                "position": state.position,
                "signal_count": len(state.signals),
            }
        stats["symbols"] = symbol_stats

        return stats

    def get_shard_distribution(self) -> Dict[str, int]:
        """
        获取交易对的分片分布

        Returns:
            Dict[str, int]: 交易对到分片的映射
        """
        distribution = {}
        for symbol in self.symbols:
            shard_id = self.engine._get_shard_id(symbol)
            distribution[symbol] = shard_id
        return distribution

    def reset(self):
        """重置策略状态"""
        self.symbol_states = {
            symbol: SymbolState(symbol=symbol)
            for symbol in self.symbols
        }
        self.stats = {
            "total_events": 0,
            "events_by_symbol": defaultdict(int),
            "signals_generated": 0,
            "processing_time_ms": 0.0,
        }
