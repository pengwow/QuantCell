# 基础策略类
# 包含自研策略框架和 NautilusTrader 策略框架的实现

from __future__ import annotations

import datetime as dt
from abc import abstractmethod
from decimal import Decimal
from typing import Any

import pandas as pd
from loguru import logger
from strategy.core import StrategyCore


class BaseStrategy(StrategyCore):
    """
    基础策略类，使用自研 StrategyCore 框架
    添加获取不同时间周期数据的功能
    """

    def __init__(self, params: dict = None):
        """
        初始化策略

        Args:
            params: 策略参数
        """
        super().__init__(params or {})
        self.symbol = None
        self.data_manager = None

    def set_symbol(self, symbol: str):
        """
        设置交易对符号

        Args:
            symbol: 交易对符号
        """
        self.symbol = symbol
        logger.info(f"策略交易对设置为: {symbol}")

    def set_data_manager(self, data_manager):
        """
        设置数据管理器实例

        Args:
            data_manager: 数据管理器实例
        """
        self.data_manager = data_manager
        logger.info(f"数据管理器已设置到策略实例，交易对: {self.symbol}")

    def get_data(self, interval: str) -> pd.DataFrame:
        """
        获取指定时间周期的数据

        Args:
            interval: 时间周期，例如 '1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'

        Returns:
            pd.DataFrame: 指定周期的K线数据
        """
        if not self.data_manager:
            logger.error(f"数据管理器未初始化，交易对: {self.symbol}")
            return pd.DataFrame()

        if not self.symbol:
            logger.error("交易对符号未设置")
            return pd.DataFrame()

        try:
            # 从数据管理器获取指定周期的数据
            data = self.data_manager.get_data(self.symbol, interval)
            logger.debug(f"成功获取 {self.symbol} 的 {interval} 周期数据，共 {len(data)} 条")
            return data
        except Exception as e:
            logger.error(f"获取 {self.symbol} 的 {interval} 周期数据失败: {e}")
            logger.exception(e)
            return pd.DataFrame()

    def get_supported_intervals(self) -> list:
        """
        获取支持的时间周期列表

        Returns:
            list: 支持的时间周期列表
        """
        if self.data_manager:
            return self.data_manager.get_supported_intervals()
        return []

    def calculate_indicators(self, data: pd.DataFrame) -> dict:
        """
        计算策略所需的指标（子类必须实现）

        Args:
            data: K线数据

        Returns:
            dict: 计算得到的指标字典
        """
        # 默认实现，返回空字典
        return {}

    def generate_signals(self, indicators: dict) -> dict:
        """
        根据指标生成交易信号（子类必须实现）

        Args:
            indicators: 计算得到的指标字典

        Returns:
            dict: 交易信号字典
        """
        # 默认实现，返回空信号
        return {
            'entries': pd.Series(False, index=indicators.get('sma1', pd.Series()).index if indicators else []),
            'exits': pd.Series(False, index=indicators.get('sma1', pd.Series()).index if indicators else [])
        }


# =============================================================================
# NautilusTrader 策略基类
# =============================================================================

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.position import Position
from nautilus_trader.trading.strategy import Strategy


class QuantCellNautilusConfig(StrategyConfig, frozen=True):
    """
    QuantCell NautilusTrader 策略配置基类

    所有使用 NautilusTrader 框架的策略都需要继承此配置类
    提供基础的配置参数，子类可以扩展更多特定参数

    Parameters
    ----------
    instrument_id : InstrumentId
        策略交易的品种ID
    bar_type : BarType
        策略订阅的K线类型
    trade_size : Decimal
        每笔交易的数量
    log_level : str, default "INFO"
        日志级别，可选值: DEBUG, INFO, WARNING, ERROR

    Attributes
    ----------
    instrument_id : InstrumentId
        交易品种唯一标识符
    bar_type : BarType
        K线数据类型（时间周期、价格类型等）
    trade_size : Decimal
        标准交易数量
    log_level : str
        日志输出级别
    """

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal = Decimal("1.0")
    log_level: str = "INFO"


class QuantCellNautilusStrategy(Strategy):
    """
    QuantCell NautilusTrader 策略基类

    为 QuantCell 项目提供统一的 NautilusTrader 策略封装
    封装了常用的交易操作和生命周期管理

    子类需要实现以下方法:
    - `on_bar`: 处理K线数据的核心交易逻辑
    - `calculate_indicators`: 计算技术指标
    - `generate_signals`: 生成交易信号

    Parameters
    ----------
    config : QuantCellNautilusConfig
        策略配置对象

    Attributes
    ----------
    config : QuantCellNautilusConfig
        策略配置
    instrument : Instrument | None
        交易品种对象，在 on_start 中初始化
    bars_processed : int
        已处理的K线数量
    start_time : datetime | None
        策略启动时间
    end_time : datetime | None
        策略停止时间

    Examples
    --------
    >>> config = QuantCellNautilusConfig(
    ...     instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    ...     bar_type=BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"),
    ...     trade_size=Decimal("0.1"),
    ... )
    >>> strategy = MyStrategy(config)
    """

    def __init__(self, config: QuantCellNautilusConfig) -> None:
        """
        初始化策略

        Args:
            config: 策略配置对象
        """
        super().__init__(config)

        # 交易品种对象，在 on_start 中从缓存加载
        self.instrument: Instrument | None = None

        # 统计信息
        self.bars_processed: int = 0
        self.start_time: dt.datetime | None = None
        self.end_time: dt.datetime | None = None

    def on_start(self) -> None:
        """
        策略启动时调用

        执行以下操作:
        1. 记录策略启动时间
        2. 从缓存加载交易品种信息
        3. 订阅指定的K线数据
        4. 输出启动日志

        子类可以重写此方法，但需要调用 super().on_start()
        """
        # 记录策略启动时间
        self.start_time = dt.datetime.now()
        self.log.info(f"策略启动时间: {self.start_time}", color=LogColor.GREEN)

        # 从缓存加载交易品种信息
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            self.log.error(f"无法找到交易品种: {self.config.instrument_id}")
            self.stop()
            return

        self.log.info(f"成功加载交易品种: {self.instrument.id}", color=LogColor.GREEN)

        # 订阅K线数据
        self.subscribe_bars(self.config.bar_type)
        self.log.info(f"已订阅K线数据: {self.config.bar_type}", color=LogColor.YELLOW)

    def on_bar(self, bar: Bar) -> None:
        """
        收到K线数据时调用

        这是策略的核心方法，子类必须实现具体的交易逻辑
        基类只负责统计处理过的K线数量

        Args:
            bar: K线数据对象，包含开盘价、最高价、最低价、收盘价、成交量等信息

        Raises
        ------
        NotImplementedError
            如果子类没有实现此方法
        """
        self.bars_processed += 1

        # 子类应该重写此方法实现具体的交易逻辑
        self.log.debug(f"处理K线数据: {bar.ts_event}, 收盘价: {bar.close}")

        # 调用抽象方法执行子类的具体逻辑
        self._on_bar_impl(bar)

    @abstractmethod
    def _on_bar_impl(self, bar: Bar) -> None:
        """
        K线数据处理的具体实现（子类必须实现）

        Args:
            bar: K线数据对象
        """
        raise NotImplementedError("子类必须实现 _on_bar_impl 方法")

    def on_stop(self) -> None:
        """
        策略停止时调用

        执行以下操作:
        1. 记录策略停止时间
        2. 取消所有未成交订单
        3. 平掉所有持仓
        4. 取消数据订阅
        5. 输出统计日志

        子类可以重写此方法，但需要调用 super().on_stop()
        """
        # 记录策略停止时间
        self.end_time = dt.datetime.now()

        # 取消所有订单
        self.cancel_all_orders(self.config.instrument_id)
        self.log.info("已取消所有未成交订单", color=LogColor.YELLOW)

        # 平掉所有持仓
        self.close_all_positions(self.config.instrument_id)
        self.log.info("已平掉所有持仓", color=LogColor.YELLOW)

        # 取消数据订阅
        self.unsubscribe_bars(self.config.bar_type)
        self.log.info(f"已取消K线订阅: {self.config.bar_type}", color=LogColor.YELLOW)

        # 输出统计信息
        duration = self.end_time - self.start_time if self.start_time else None
        self.log.info("=" * 50, color=LogColor.CYAN)
        self.log.info("策略运行统计:", color=LogColor.CYAN)
        self.log.info(f"  启动时间: {self.start_time}", color=LogColor.CYAN)
        self.log.info(f"  停止时间: {self.end_time}", color=LogColor.CYAN)
        self.log.info(f"  运行时长: {duration}", color=LogColor.CYAN)
        self.log.info(f"  处理K线: {self.bars_processed} 条", color=LogColor.CYAN)
        self.log.info("=" * 50, color=LogColor.CYAN)

    def buy(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        买入下单封装

        根据指定的参数创建并提交买入订单

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，默认为 None（市价单不需要）
            order_type: 订单类型，默认为 MARKET（市价单）
            time_in_force: 订单有效时间，默认为 GTC（一直有效）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        if not self.instrument:
            self.log.error("交易品种未加载，无法下单")
            return

        # 使用默认数量
        qty = quantity if quantity else self.config.trade_size

        # 创建数量对象
        order_qty: Quantity = self.instrument.make_qty(qty)

        # 创建价格对象（市价单不需要价格）
        order_price: Price | None = None
        if price and order_type != OrderType.MARKET:
            order_price = self.instrument.make_price(price)

        # 创建订单
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=order_qty,
        ) if order_type == OrderType.MARKET else self.order_factory.limit(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.BUY,
            quantity=order_qty,
            price=order_price,
            time_in_force=time_in_force,
        )

        # 提交订单
        self.submit_order(order)
        self.log.info(
            f"买入下单: {self.config.instrument_id}, 数量: {qty}, 类型: {order_type.name}",
            color=LogColor.GREEN,
        )

    def sell(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        卖出下单封装

        根据指定的参数创建并提交卖出订单

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，默认为 None（市价单不需要）
            order_type: 订单类型，默认为 MARKET（市价单）
            time_in_force: 订单有效时间，默认为 GTC（一直有效）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        if not self.instrument:
            self.log.error("交易品种未加载，无法下单")
            return

        # 使用默认数量
        qty = quantity if quantity else self.config.trade_size

        # 创建数量对象
        order_qty: Quantity = self.instrument.make_qty(qty)

        # 创建价格对象（市价单不需要价格）
        order_price: Price | None = None
        if price and order_type != OrderType.MARKET:
            order_price = self.instrument.make_price(price)

        # 创建订单
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=order_qty,
        ) if order_type == OrderType.MARKET else self.order_factory.limit(
            instrument_id=self.config.instrument_id,
            order_side=OrderSide.SELL,
            quantity=order_qty,
            price=order_price,
            time_in_force=time_in_force,
        )

        # 提交订单
        self.submit_order(order)
        self.log.info(
            f"卖出下单: {self.config.instrument_id}, 数量: {qty}, 类型: {order_type.name}",
            color=LogColor.RED,
        )

    def close_position(self, position: Position | None = None) -> None:
        """
        平仓封装

        平掉指定的持仓或当前品种的所有持仓

        Args:
            position: 要平仓的持仓对象，默认为 None（平掉所有持仓）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        if not self.instrument:
            self.log.error("交易品种未加载，无法平仓")
            return

        if position:
            # 平掉指定持仓
            self.close_position_by_id(position.id)
            self.log.info(f"平掉持仓: {position.id}", color=LogColor.YELLOW)
        else:
            # 平掉所有持仓
            self.close_all_positions(self.config.instrument_id)
            self.log.info(f"平掉 {self.config.instrument_id} 的所有持仓", color=LogColor.YELLOW)

    def get_position(self, instrument_id: InstrumentId | None = None) -> Position | None:
        """
        获取持仓信息

        获取指定品种的持仓信息

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            Position | None: 持仓对象，如果没有持仓则返回 None
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id

        # 从缓存获取持仓
        positions = self.cache.positions_for_instrument(target_id)

        if positions:
            # 返回第一个持仓（通常一个品种只有一个持仓）
            return positions[0]

        return None

    def get_position_size(self, instrument_id: InstrumentId | None = None) -> Decimal:
        """
        获取持仓数量

        获取指定品种的持仓数量（正数表示多头，负数表示空头）

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            Decimal: 持仓数量，没有持仓返回 0
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id

        # 检查是否持有多头
        if self.portfolio.is_net_long(target_id):
            position = self.get_position(target_id)
            return position.quantity.as_decimal() if position else Decimal("0")

        # 检查是否持有空头
        if self.portfolio.is_net_short(target_id):
            position = self.get_position(target_id)
            return -position.quantity.as_decimal() if position else Decimal("0")

        return Decimal("0")

    def is_flat(self, instrument_id: InstrumentId | None = None) -> bool:
        """
        检查是否空仓

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果没有持仓返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        return self.portfolio.is_flat(target_id)

    def is_long(self, instrument_id: InstrumentId | None = None) -> bool:
        """
        检查是否持有多头

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果持有多头返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        return self.portfolio.is_net_long(target_id)

    def is_short(self, instrument_id: InstrumentId | None = None) -> bool:
        """
        检查是否持有空头

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果持有空头返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        return self.portfolio.is_net_short(target_id)

    def log_info(self, message: str, color: LogColor = LogColor.NORMAL) -> None:
        """
        输出信息日志

        Args:
            message: 日志消息
            color: 日志颜色
        """
        self.log.info(message, color=color)

    def log_debug(self, message: str, color: LogColor = LogColor.NORMAL) -> None:
        """
        输出调试日志

        Args:
            message: 日志消息
            color: 日志颜色
        """
        self.log.debug(message, color=color)

    def log_warning(self, message: str, color: LogColor = LogColor.YELLOW) -> None:
        """
        输出警告日志

        Args:
            message: 日志消息
            color: 日志颜色
        """
        self.log.warning(message, color=color)

    def log_error(self, message: str, color: LogColor = LogColor.RED) -> None:
        """
        输出错误日志

        Args:
            message: 日志消息
            color: 日志颜色
        """
        self.log.error(message, color=color)

    def calculate_indicators(self, bar: Bar) -> dict[str, Any]:
        """
        计算技术指标（子类可以重写）

        Args:
            bar: K线数据对象

        Returns:
            dict: 指标字典
        """
        return {}

    def generate_signals(self, indicators: dict[str, Any]) -> dict[str, bool]:
        """
        生成交易信号（子类可以重写）

        Args:
            indicators: 指标字典

        Returns:
            dict: 信号字典，包含 entry_long, exit_long, entry_short, exit_short 等键
        """
        return {
            "entry_long": False,
            "exit_long": False,
            "entry_short": False,
            "exit_short": False,
        }
