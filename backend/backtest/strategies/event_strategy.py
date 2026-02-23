# -*- coding: utf-8 -*-
"""
事件驱动策略基类

提供事件驱动架构的策略基类，支持高性能回测和实盘交易。

包含:
    - EventDrivenStrategyConfig: 事件驱动策略配置基类
    - EventDrivenStrategy: 事件驱动策略基类

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-23
"""

from __future__ import annotations

import datetime as dt
from abc import abstractmethod
from decimal import Decimal
from typing import Any

from loguru import logger


class EventDrivenStrategyConfig:
    """
    事件驱动策略配置基类

    所有事件驱动策略都需要继承此配置类
    提供基础的配置参数，子类可以扩展更多特定参数

    Parameters
    ----------
    instrument_id : Any
        策略交易的品种ID
    bar_type : Any
        策略订阅的K线类型
    trade_size : Decimal
        每笔交易的数量
    log_level : str, default "INFO"
        日志级别，可选值: DEBUG, INFO, WARNING, ERROR

    Attributes
    ----------
    instrument_id : Any
        交易品种唯一标识符
    bar_type : Any
        K线数据类型（时间周期、价格类型等）
    trade_size : Decimal
        标准交易数量
    log_level : str
        日志输出级别
    """

    def __init__(
        self,
        instrument_id: Any,
        bar_type: Any,
        trade_size: Decimal = Decimal("1.0"),
        log_level: str = "INFO",
    ):
        self.instrument_id = instrument_id
        self.bar_type = bar_type
        self.trade_size = trade_size
        self.log_level = log_level


class EventDrivenStrategy:
    """
    事件驱动策略基类

    为 QuantCell 项目提供统一的事件驱动策略封装
    封装了常用的交易操作和生命周期管理

    子类需要实现以下方法:
    - `on_bar`: 处理K线数据的核心交易逻辑
    - `calculate_indicators`: 计算技术指标
    - `generate_signals`: 生成交易信号

    Parameters
    ----------
    config : EventDrivenStrategyConfig
        策略配置对象

    Attributes
    ----------
    config : EventDrivenStrategyConfig
        策略配置
    instrument : Any | None
        交易品种对象，在 on_start 中初始化
    bars_processed : int
        已处理的K线数量
    start_time : datetime | None
        策略启动时间
    end_time : datetime | None
        策略停止时间

    Examples
    --------
    >>> config = EventDrivenStrategyConfig(
    ...     instrument_id=instrument_id,
    ...     bar_type=bar_type,
    ...     trade_size=Decimal("0.1"),
    ... )
    >>> strategy = MyStrategy(config)
    """

    def __init__(self, config: EventDrivenStrategyConfig) -> None:
        """
        初始化策略

        Args:
            config: 策略配置对象
        """
        self.config = config

        # 交易品种对象，在 on_start 中从缓存加载
        self.instrument: Any | None = None

        # 统计信息
        self.bars_processed: int = 0
        self.start_time: dt.datetime | None = None
        self.end_time: dt.datetime | None = None

        # 延迟导入底层实现
        self._strategy_impl: Any = None
        self._log_color: Any = None

    def _get_strategy_impl(self) -> Any:
        """获取底层策略实现（延迟加载）"""
        if self._strategy_impl is None:
            from nautilus_trader.trading.strategy import Strategy
            from nautilus_trader.trading.config import StrategyConfig

            # 创建NautilusTrader兼容的配置
            nautilus_config = StrategyConfig(
                strategy_id=self.config.__class__.__name__,
                order_id_tag="001",
                oms_type="NETTING",
            )

            # 创建底层策略实现
            class _StrategyImpl(Strategy):
                def __init__(inner_self, config, outer_self):
                    super().__init__(config)
                    self._outer = outer_self
                    outer_self._strategy_impl = inner_self

                def on_start(inner_self) -> None:
                    self.on_start()

                def on_bar(inner_self, bar: Any) -> None:
                    self.on_bar(bar)

                def on_stop(inner_self) -> None:
                    self.on_stop()

            self._strategy_impl = _StrategyImpl(nautilus_config, self)
        return self._strategy_impl

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
        # 延迟导入底层实现
        from nautilus_trader.common.enums import LogColor

        # 记录策略启动时间
        self.start_time = dt.datetime.now()
        logger.info(f"策略启动时间: {self.start_time}")

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        # 从缓存加载交易品种信息
        self.instrument = impl.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            logger.error(f"无法找到交易品种: {self.config.instrument_id}")
            impl.stop()
            return

        logger.info(f"成功加载交易品种: {self.instrument.id}")

        # 订阅K线数据
        impl.subscribe_bars(self.config.bar_type)
        logger.info(f"已订阅K线数据: {self.config.bar_type}")

    def on_bar(self, bar: Any) -> None:
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
        logger.debug(f"处理K线数据: {bar.ts_event}, 收盘价: {bar.close}")

        # 调用抽象方法执行子类的具体逻辑
        self._on_bar_impl(bar)

    @abstractmethod
    def _on_bar_impl(self, bar: Any) -> None:
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

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        # 取消所有订单
        impl.cancel_all_orders(self.config.instrument_id)
        logger.info("已取消所有未成交订单")

        # 平掉所有持仓
        impl.close_all_positions(self.config.instrument_id)
        logger.info("已平掉所有持仓")

        # 取消数据订阅
        impl.unsubscribe_bars(self.config.bar_type)
        logger.info(f"已取消K线订阅: {self.config.bar_type}")

        # 输出统计信息
        duration = self.end_time - self.start_time if self.start_time else None
        logger.info("=" * 50)
        logger.info("策略运行统计:")
        logger.info(f"  启动时间: {self.start_time}")
        logger.info(f"  停止时间: {self.end_time}")
        logger.info(f"  运行时长: {duration}")
        logger.info(f"  处理K线: {self.bars_processed} 条")
        logger.info("=" * 50)

    def buy(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: str = "MARKET",
        time_in_force: str = "GTC",
    ) -> None:
        """
        买入下单封装

        根据指定的参数创建并提交买入订单

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，默认为 None（市价单不需要）
            order_type: 订单类型，默认为 "MARKET"（市价单）
            time_in_force: 订单有效时间，默认为 "GTC"（一直有效）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        if not self.instrument:
            logger.error("交易品种未加载，无法下单")
            return

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        # 使用默认数量
        qty = quantity if quantity else self.config.trade_size

        # 创建数量对象
        order_qty = self.instrument.make_qty(qty)

        # 创建订单
        if order_type == "MARKET":
            from nautilus_trader.model.enums import OrderSide

            order = impl.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=order_qty,
            )
        else:
            from nautilus_trader.model.enums import OrderSide, TimeInForce

            order_price = self.instrument.make_price(price) if price else None
            order = impl.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=order_qty,
                price=order_price,
                time_in_force=TimeInForce.GTC,
            )

        # 提交订单
        impl.submit_order(order)
        logger.info(f"买入下单: {self.config.instrument_id}, 数量: {qty}, 类型: {order_type}")

    def sell(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: str = "MARKET",
        time_in_force: str = "GTC",
    ) -> None:
        """
        卖出下单封装

        根据指定的参数创建并提交卖出订单

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，默认为 None（市价单不需要）
            order_type: 订单类型，默认为 "MARKET"（市价单）
            time_in_force: 订单有效时间，默认为 "GTC"（一直有效）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        if not self.instrument:
            logger.error("交易品种未加载，无法下单")
            return

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        # 使用默认数量
        qty = quantity if quantity else self.config.trade_size

        # 创建数量对象
        order_qty = self.instrument.make_qty(qty)

        # 创建订单
        if order_type == "MARKET":
            from nautilus_trader.model.enums import OrderSide

            order = impl.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=order_qty,
            )
        else:
            from nautilus_trader.model.enums import OrderSide, TimeInForce

            order_price = self.instrument.make_price(price) if price else None
            order = impl.order_factory.limit(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.SELL,
                quantity=order_qty,
                price=order_price,
                time_in_force=TimeInForce.GTC,
            )

        # 提交订单
        impl.submit_order(order)
        logger.info(f"卖出下单: {self.config.instrument_id}, 数量: {qty}, 类型: {order_type}")

    def close_position(self, position: Any | None = None) -> None:
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
            logger.error("交易品种未加载，无法平仓")
            return

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        if position:
            # 平掉指定持仓
            impl.close_position_by_id(position.id)
            logger.info(f"平掉持仓: {position.id}")
        else:
            # 平掉所有持仓
            impl.close_all_positions(self.config.instrument_id)
            logger.info(f"平掉 {self.config.instrument_id} 的所有持仓")

    def get_position(self, instrument_id: Any | None = None) -> Any | None:
        """
        获取持仓信息

        获取指定品种的持仓信息

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            Any | None: 持仓对象，如果没有持仓则返回 None
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        # 从缓存获取持仓
        positions = impl.cache.positions_for_instrument(target_id)

        if positions:
            # 返回第一个持仓（通常一个品种只有一个持仓）
            return positions[0]

        return None

    def get_position_size(self, instrument_id: Any | None = None) -> Decimal:
        """
        获取持仓数量

        获取指定品种的持仓数量（正数表示多头，负数表示空头）

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            Decimal: 持仓数量，没有持仓返回 0
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id

        # 获取底层策略实例
        impl = self._get_strategy_impl()

        # 检查是否持有多头
        if impl.portfolio.is_net_long(target_id):
            position = self.get_position(target_id)
            return position.quantity.as_decimal() if position else Decimal("0")

        # 检查是否持有空头
        if impl.portfolio.is_net_short(target_id):
            position = self.get_position(target_id)
            return -position.quantity.as_decimal() if position else Decimal("0")

        return Decimal("0")

    def is_flat(self, instrument_id: Any | None = None) -> bool:
        """
        检查是否空仓

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果没有持仓返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        impl = self._get_strategy_impl()
        return impl.portfolio.is_flat(target_id)

    def is_long(self, instrument_id: Any | None = None) -> bool:
        """
        检查是否持有多头

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果持有多头返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        impl = self._get_strategy_impl()
        return impl.portfolio.is_net_long(target_id)

    def is_short(self, instrument_id: Any | None = None) -> bool:
        """
        检查是否持有空头

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果持有空头返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        impl = self._get_strategy_impl()
        return impl.portfolio.is_net_short(target_id)

    def log_info(self, message: str) -> None:
        """
        输出信息日志

        Args:
            message: 日志消息
        """
        logger.info(message)

    def log_debug(self, message: str) -> None:
        """
        输出调试日志

        Args:
            message: 日志消息
        """
        logger.debug(message)

    def log_warning(self, message: str) -> None:
        """
        输出警告日志

        Args:
            message: 日志消息
        """
        logger.warning(message)

    def log_error(self, message: str) -> None:
        """
        输出错误日志

        Args:
            message: 日志消息
        """
        logger.error(message)

    def calculate_indicators(self, bar: Any) -> dict[str, Any]:
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
