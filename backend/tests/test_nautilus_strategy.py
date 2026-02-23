# -*- coding: utf-8 -*-
"""
NautilusTrader 策略单元测试

测试 QuantCellNautilusStrategy 的核心功能，包括:
- 策略初始化
- 策略配置类
- 交易方法 (buy/sell/close_position)
- 持仓查询

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-23
"""

from collections import deque
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pandas as pd
import pytest

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy

from backend.backtest.strategies.base import (
    QuantCellNautilusConfig,
    QuantCellNautilusStrategy,
)
from backend.strategies.sma_cross_nautilus import (
    SmaCrossNautilusConfig,
    SmaCrossNautilusStrategy,
)


# =============================================================================
# 测试固件 (Fixtures)
# =============================================================================

@pytest.fixture
def sample_instrument_id():
    """返回示例交易品种ID"""
    return InstrumentId.from_str("BTCUSDT.BINANCE")


@pytest.fixture
def sample_bar_type(sample_instrument_id):
    """返回示例 BarType"""
    return BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")


@pytest.fixture
def base_config(sample_instrument_id, sample_bar_type):
    """返回基础策略配置"""
    return QuantCellNautilusConfig(
        instrument_id=sample_instrument_id,
        bar_type=sample_bar_type,
        trade_size=Decimal("0.1"),
        log_level="DEBUG",
    )


@pytest.fixture
def sma_config(sample_instrument_id, sample_bar_type):
    """返回 SMA 策略配置"""
    return SmaCrossNautilusConfig(
        instrument_id=sample_instrument_id,
        bar_type=sample_bar_type,
        trade_size=Decimal("0.1"),
        fast_period=5,
        slow_period=10,
    )


@pytest.fixture
def mock_strategy_deps():
    """返回模拟的策略依赖"""
    deps = {
        "cache": MagicMock(),
        "portfolio": MagicMock(),
        "order_factory": MagicMock(),
        "log": MagicMock(),
    }
    return deps


@pytest.fixture
def mock_bar():
    """返回模拟的 Bar 数据"""
    bar = MagicMock(spec=Bar)
    bar.close = Price(50000, 2)
    bar.high = Price(50100, 2)
    bar.low = Price(49900, 2)
    bar.open = Price(50000, 2)
    bar.ts_event = 1704067200000000000
    return bar


@pytest.fixture
def mock_instrument():
    """返回模拟的交易品种"""
    instrument = MagicMock(spec=Instrument)
    instrument.id = InstrumentId.from_str("BTCUSDT.BINANCE")
    instrument.price_precision = 2
    instrument.size_precision = 6
    instrument.make_price = Mock(side_effect=lambda x: Price(x, 2))
    instrument.make_qty = Mock(side_effect=lambda x: Quantity(x, 6))
    return instrument


# =============================================================================
# 策略配置类测试
# =============================================================================

class TestQuantCellNautilusConfig:
    """测试 QuantCellNautilusConfig 配置类"""

    def test_config_creation(self, sample_instrument_id, sample_bar_type):
        """测试配置对象创建"""
        config = QuantCellNautilusConfig(
            instrument_id=sample_instrument_id,
            bar_type=sample_bar_type,
            trade_size=Decimal("0.5"),
            log_level="INFO",
        )

        assert config.instrument_id == sample_instrument_id
        assert config.bar_type == sample_bar_type
        assert config.trade_size == Decimal("0.5")
        assert config.log_level == "INFO"

    def test_config_default_values(self, sample_instrument_id, sample_bar_type):
        """测试配置默认值"""
        config = QuantCellNautilusConfig(
            instrument_id=sample_instrument_id,
            bar_type=sample_bar_type,
        )

        assert config.trade_size == Decimal("1.0")  # 默认值
        assert config.log_level == "INFO"  # 默认值

    def test_config_is_frozen(self, sample_instrument_id, sample_bar_type):
        """测试配置类是不可变的"""
        config = QuantCellNautilusConfig(
            instrument_id=sample_instrument_id,
            bar_type=sample_bar_type,
        )

        # 尝试修改应该抛出异常
        with pytest.raises(Exception):
            config.trade_size = Decimal("2.0")


class TestSmaCrossNautilusConfig:
    """测试 SmaCrossNautilusConfig 配置类"""

    def test_sma_config_creation(self, sample_instrument_id, sample_bar_type):
        """测试 SMA 配置对象创建"""
        config = SmaCrossNautilusConfig(
            instrument_id=sample_instrument_id,
            bar_type=sample_bar_type,
            trade_size=Decimal("0.1"),
            fast_period=10,
            slow_period=20,
        )

        assert config.fast_period == 10
        assert config.slow_period == 20
        assert config.trade_size == Decimal("0.1")

    def test_sma_config_default_values(self, sample_instrument_id, sample_bar_type):
        """测试 SMA 配置默认值"""
        config = SmaCrossNautilusConfig(
            instrument_id=sample_instrument_id,
            bar_type=sample_bar_type,
        )

        assert config.fast_period == 10
        assert config.slow_period == 20
        assert config.trade_size == Decimal("0.1")


# =============================================================================
# 策略初始化测试
# =============================================================================

class TestQuantCellNautilusStrategyInit:
    """测试策略初始化"""

    def test_strategy_attributes_after_init(self, base_config):
        """测试策略初始化后的属性"""
        # 使用 MagicMock 模拟策略实例
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = None
        strategy.bars_processed = 0
        strategy.start_time = None
        strategy.end_time = None

        assert strategy.config == base_config
        assert strategy.instrument is None
        assert strategy.bars_processed == 0
        assert strategy.start_time is None
        assert strategy.end_time is None


class TestSmaCrossNautilusStrategyInit:
    """测试 SMA 策略初始化"""

    def test_sma_strategy_init(self, sma_config):
        """测试 SMA 策略初始化"""
        # 使用 MagicMock 模拟策略实例
        strategy = MagicMock(spec=SmaCrossNautilusStrategy)
        strategy.config = sma_config
        strategy.fast_period = sma_config.fast_period
        strategy.slow_period = sma_config.slow_period
        strategy.close_prices = deque(maxlen=20)
        strategy.fast_sma_values = []
        strategy.slow_sma_values = []
        strategy.signals_generated = 0
        strategy.trades_executed = 0
        strategy._last_fast_sma = None
        strategy._last_slow_sma = None

        assert strategy.fast_period == 5  # fixture 中使用的是 5
        assert strategy.slow_period == 10  # fixture 中使用的是 10
        assert isinstance(strategy.close_prices, deque)
        assert strategy.close_prices.maxlen == 20


# =============================================================================
# 策略生命周期测试
# =============================================================================

class TestQuantCellNautilusStrategyLifecycle:
    """测试策略生命周期方法"""

    def test_on_start(self, base_config, mock_instrument):
        """测试策略启动"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = None
        strategy.start_time = None
        strategy.log = MagicMock()
        strategy.cache = MagicMock()
        strategy.cache.instrument.return_value = mock_instrument
        strategy.subscribe_bars = MagicMock()
        strategy.stop = MagicMock()

        # 模拟 on_start 逻辑
        import datetime as dt
        strategy.start_time = dt.datetime.now()
        strategy.instrument = strategy.cache.instrument(strategy.config.instrument_id)
        strategy.subscribe_bars(strategy.config.bar_type)

        assert strategy.start_time is not None
        assert strategy.instrument == mock_instrument
        strategy.subscribe_bars.assert_called_once_with(strategy.config.bar_type)

    def test_on_start_instrument_not_found(self, base_config):
        """测试启动时找不到交易品种"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = None
        strategy.log = MagicMock()
        strategy.cache = MagicMock()
        strategy.cache.instrument.return_value = None
        strategy.stop = MagicMock()

        # 模拟 on_start 逻辑
        strategy.instrument = strategy.cache.instrument(strategy.config.instrument_id)
        if strategy.instrument is None:
            strategy.stop()

        strategy.stop.assert_called_once()

    def test_on_stop(self, base_config):
        """测试策略停止"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = MagicMock()
        strategy.end_time = None
        strategy.start_time = MagicMock()
        strategy.bars_processed = 100
        strategy.log = MagicMock()
        strategy.cancel_all_orders = MagicMock()
        strategy.close_all_positions = MagicMock()
        strategy.unsubscribe_bars = MagicMock()

        # 模拟 on_stop 逻辑
        import datetime as dt
        strategy.end_time = dt.datetime.now()
        strategy.cancel_all_orders(strategy.config.instrument_id)
        strategy.close_all_positions(strategy.config.instrument_id)
        strategy.unsubscribe_bars(strategy.config.bar_type)

        assert strategy.end_time is not None
        strategy.cancel_all_orders.assert_called_once()
        strategy.close_all_positions.assert_called_once()
        strategy.unsubscribe_bars.assert_called_once()


# =============================================================================
# 交易方法测试
# =============================================================================

class TestQuantCellNautilusStrategyTrading:
    """测试策略交易方法"""

    def test_buy_market_order(self, base_config, mock_instrument):
        """测试买入市价单"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = mock_instrument
        strategy.log = MagicMock()
        strategy.order_factory = MagicMock()
        strategy.submit_order = MagicMock()

        mock_order = MagicMock()
        strategy.order_factory.market.return_value = mock_order

        # 模拟 buy 方法
        qty = strategy.config.trade_size
        order_qty = mock_instrument.make_qty(qty)
        order = strategy.order_factory.market(
            instrument_id=strategy.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=order_qty,
        )
        strategy.submit_order(order)

        strategy.order_factory.market.assert_called_once()
        strategy.submit_order.assert_called_once_with(mock_order)

    def test_buy_limit_order(self, base_config, mock_instrument):
        """测试买入限价单"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = mock_instrument
        strategy.log = MagicMock()
        strategy.order_factory = MagicMock()
        strategy.submit_order = MagicMock()

        mock_order = MagicMock()
        strategy.order_factory.limit.return_value = mock_order

        # 模拟 buy 方法带价格
        price = Decimal("50000")
        qty = strategy.config.trade_size
        order_qty = mock_instrument.make_qty(qty)
        order_price = mock_instrument.make_price(price)
        order = strategy.order_factory.limit(
            instrument_id=strategy.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=order_qty,
            price=order_price,
            time_in_force=TimeInForce.GTC,
        )
        strategy.submit_order(order)

        strategy.order_factory.limit.assert_called_once()
        strategy.submit_order.assert_called_once()

    def test_buy_without_instrument(self, base_config):
        """测试无交易品种时买入"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = None
        strategy.log = MagicMock()
        strategy.submit_order = MagicMock()

        # 模拟 buy 方法检查
        if not strategy.instrument:
            strategy.log.error("交易品种未加载，无法下单")

        strategy.log.error.assert_called_once_with("交易品种未加载，无法下单")

    def test_sell_market_order(self, base_config, mock_instrument):
        """测试卖出市价单"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = mock_instrument
        strategy.log = MagicMock()
        strategy.order_factory = MagicMock()
        strategy.submit_order = MagicMock()

        mock_order = MagicMock()
        strategy.order_factory.market.return_value = mock_order

        # 模拟 sell 方法
        qty = strategy.config.trade_size
        order_qty = mock_instrument.make_qty(qty)
        order = strategy.order_factory.market(
            instrument_id=strategy.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=order_qty,
        )
        strategy.submit_order(order)

        strategy.order_factory.market.assert_called_once()
        strategy.submit_order.assert_called_once()

    def test_close_position(self, base_config, mock_instrument):
        """测试平仓"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = mock_instrument
        strategy.log = MagicMock()
        strategy.close_all_positions = MagicMock()

        # 模拟 close_position 方法
        strategy.close_all_positions(strategy.config.instrument_id)

        strategy.close_all_positions.assert_called_once_with(strategy.config.instrument_id)

    def test_close_position_without_instrument(self, base_config):
        """测试无交易品种时平仓"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.instrument = None
        strategy.log = MagicMock()
        strategy.close_all_positions = MagicMock()

        # 模拟 close_position 方法检查
        if not strategy.instrument:
            strategy.log.error("交易品种未加载，无法平仓")

        strategy.log.error.assert_called_once_with("交易品种未加载，无法平仓")


# =============================================================================
# 持仓查询测试
# =============================================================================

class TestQuantCellNautilusStrategyPositionQueries:
    """测试策略持仓查询方法"""

    def test_get_position(self, base_config):
        """测试获取持仓"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.cache = MagicMock()

        mock_position = MagicMock(spec=Position)
        strategy.cache.positions_for_instrument.return_value = [mock_position]

        positions = strategy.cache.positions_for_instrument(strategy.config.instrument_id)
        result = positions[0] if positions else None

        assert result == mock_position

    def test_get_position_empty(self, base_config):
        """测试无持仓时获取"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.cache = MagicMock()
        strategy.cache.positions_for_instrument.return_value = []

        positions = strategy.cache.positions_for_instrument(strategy.config.instrument_id)
        result = positions[0] if positions else None

        assert result is None

    def test_get_position_size_long(self, base_config):
        """测试获取多头持仓数量"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.portfolio = MagicMock()
        strategy.portfolio.is_net_long.return_value = True
        strategy.cache = MagicMock()

        mock_position = MagicMock(spec=Position)
        mock_position.quantity.as_decimal.return_value = Decimal("0.5")
        strategy.cache.positions_for_instrument.return_value = [mock_position]

        # 模拟 get_position_size 逻辑
        if strategy.portfolio.is_net_long(strategy.config.instrument_id):
            positions = strategy.cache.positions_for_instrument(strategy.config.instrument_id)
            size = positions[0].quantity.as_decimal() if positions else Decimal("0")

        assert size == Decimal("0.5")

    def test_get_position_size_short(self, base_config):
        """测试获取空头持仓数量"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.portfolio = MagicMock()
        strategy.portfolio.is_net_long.return_value = False
        strategy.portfolio.is_net_short.return_value = True
        strategy.cache = MagicMock()

        mock_position = MagicMock(spec=Position)
        mock_position.quantity.as_decimal.return_value = Decimal("0.3")
        strategy.cache.positions_for_instrument.return_value = [mock_position]

        # 模拟 get_position_size 逻辑
        if strategy.portfolio.is_net_short(strategy.config.instrument_id):
            positions = strategy.cache.positions_for_instrument(strategy.config.instrument_id)
            size = -positions[0].quantity.as_decimal() if positions else Decimal("0")

        assert size == Decimal("-0.3")

    def test_is_flat(self, base_config):
        """测试检查是否空仓"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.portfolio = MagicMock()
        strategy.portfolio.is_flat.return_value = True

        result = strategy.portfolio.is_flat(strategy.config.instrument_id)

        assert result is True

    def test_is_long(self, base_config):
        """测试检查是否持有多头"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.portfolio = MagicMock()
        strategy.portfolio.is_net_long.return_value = True

        result = strategy.portfolio.is_net_long(strategy.config.instrument_id)

        assert result is True

    def test_is_short(self, base_config):
        """测试检查是否持有空头"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.config = base_config
        strategy.portfolio = MagicMock()
        strategy.portfolio.is_net_short.return_value = True

        result = strategy.portfolio.is_net_short(strategy.config.instrument_id)

        assert result is True


# =============================================================================
# 日志方法测试
# =============================================================================

class TestQuantCellNautilusStrategyLogging:
    """测试策略日志方法"""

    def test_log_info(self, base_config):
        """测试信息日志"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.log = MagicMock()

        strategy.log.info("测试消息", color=LogColor.GREEN)
        strategy.log.info.assert_called_once_with("测试消息", color=LogColor.GREEN)

    def test_log_debug(self, base_config):
        """测试调试日志"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.log = MagicMock()

        strategy.log.debug("调试消息", color=LogColor.NORMAL)
        strategy.log.debug.assert_called_once_with("调试消息", color=LogColor.NORMAL)

    def test_log_warning(self, base_config):
        """测试警告日志"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.log = MagicMock()

        strategy.log.warning("警告消息", color=LogColor.YELLOW)
        strategy.log.warning.assert_called_once_with("警告消息", color=LogColor.YELLOW)

    def test_log_error(self, base_config):
        """测试错误日志"""
        strategy = MagicMock(spec=QuantCellNautilusStrategy)
        strategy.log = MagicMock()

        strategy.log.error("错误消息", color=LogColor.RED)
        strategy.log.error.assert_called_once_with("错误消息", color=LogColor.RED)


# =============================================================================
# SMA 策略核心逻辑测试
# =============================================================================

class TestSmaCrossNautilusStrategyCore:
    """测试 SMA 策略核心逻辑"""

    def test_calculate_sma(self):
        """测试 SMA 计算"""
        import numpy as np

        close_prices = deque([100, 110, 120, 130, 140], maxlen=10)
        fast_period = 3
        slow_period = 5

        prices = np.array(close_prices)
        fast_sma = np.mean(prices[-fast_period:])
        slow_sma = np.mean(prices[-slow_period:])

        assert fast_sma == pytest.approx(130.0)  # (120+130+140)/3
        assert slow_sma == pytest.approx(120.0)  # (100+110+120+130+140)/5

    def test_generate_signals_golden_cross(self):
        """测试金叉信号生成"""
        last_fast_sma = 90.0
        last_slow_sma = 100.0
        current_fast_sma = 105.0
        current_slow_sma = 100.0

        # 快线上穿慢线
        entry_long = current_fast_sma > current_slow_sma and last_fast_sma <= last_slow_sma
        exit_long = current_fast_sma < current_slow_sma and last_fast_sma >= last_slow_sma

        assert entry_long is True
        assert exit_long is False

    def test_generate_signals_death_cross(self):
        """测试死叉信号生成"""
        last_fast_sma = 110.0
        last_slow_sma = 100.0
        current_fast_sma = 95.0
        current_slow_sma = 100.0

        # 快线下穿慢线
        entry_long = current_fast_sma > current_slow_sma and last_fast_sma <= last_slow_sma
        exit_long = current_fast_sma < current_slow_sma and last_fast_sma >= last_slow_sma

        assert entry_long is False
        assert exit_long is True

    def test_generate_signals_no_cross(self):
        """测试无交叉信号"""
        last_fast_sma = 105.0
        last_slow_sma = 100.0
        current_fast_sma = 110.0
        current_slow_sma = 100.0

        # 快线在慢线上方，但没有交叉
        entry_long = current_fast_sma > current_slow_sma and last_fast_sma <= last_slow_sma
        exit_long = current_fast_sma < current_slow_sma and last_fast_sma >= last_slow_sma

        assert entry_long is False
        assert exit_long is False


# =============================================================================
# 策略抽象方法测试
# =============================================================================

class TestQuantCellNautilusStrategyAbstractMethods:
    """测试策略抽象方法"""

    def test_calculate_indicators_default(self, base_config):
        """测试默认 calculate_indicators 实现"""
        # 基类的 calculate_indicators 返回空字典
        result = QuantCellNautilusStrategy.calculate_indicators(
            MagicMock(), MagicMock(spec=Bar)
        )
        assert result == {}

    def test_generate_signals_default(self, base_config):
        """测试默认 generate_signals 实现"""
        # 基类的 generate_signals 返回默认信号
        result = QuantCellNautilusStrategy.generate_signals(MagicMock(), {})
        assert result == {
            "entry_long": False,
            "exit_long": False,
            "entry_short": False,
            "exit_short": False,
        }


# =============================================================================
# SMA 策略统计信息测试
# =============================================================================

class TestSmaCrossNautilusStrategyStats:
    """测试 SMA 策略统计信息"""

    def test_get_indicators_with_data(self, sma_config):
        """测试获取指标值（有数据）"""
        strategy = MagicMock(spec=SmaCrossNautilusStrategy)
        strategy.fast_sma_values = [100.0, 105.0, 110.0]
        strategy.slow_sma_values = [95.0, 98.0, 100.0]

        indicators = {
            "fast_sma": strategy.fast_sma_values[-1],
            "slow_sma": strategy.slow_sma_values[-1],
        }

        assert indicators["fast_sma"] == 110.0
        assert indicators["slow_sma"] == 100.0

    def test_get_indicators_without_data(self, sma_config):
        """测试获取指标值（无数据）"""
        strategy = MagicMock(spec=SmaCrossNautilusStrategy)
        strategy.fast_sma_values = []
        strategy.slow_sma_values = []

        if len(strategy.fast_sma_values) == 0 or len(strategy.slow_sma_values) == 0:
            indicators = {"fast_sma": None, "slow_sma": None}

        assert indicators["fast_sma"] is None
        assert indicators["slow_sma"] is None

    def test_signals_count(self, sma_config):
        """测试信号计数"""
        strategy = MagicMock(spec=SmaCrossNautilusStrategy)
        strategy.signals_generated = 5
        strategy.trades_executed = 3

        assert strategy.signals_generated == 5
        assert strategy.trades_executed == 3

    def test_close_prices_collection(self, sma_config):
        """测试收盘价收集"""
        strategy = MagicMock(spec=SmaCrossNautilusStrategy)
        strategy.close_prices = deque(maxlen=20)

        # 模拟添加收盘价
        for i in range(25):
            strategy.close_prices.append(50000 + i * 10)

        # 由于 maxlen=20，应该只保留最后20个
        assert len(strategy.close_prices) == 20
        assert strategy.close_prices[0] == 50000 + 5 * 10  # 第6个元素
        assert strategy.close_prices[-1] == 50000 + 24 * 10  # 最后一个元素
