# -*- coding: utf-8 -*-
"""
策略基类

提供统一的事件驱动策略封装，支持高性能回测和实盘交易。
基于 NautilusTrader 原生 Strategy 类进行封装，同时保留扩展性以支持其他策略引擎。

包含:
    - StrategyConfig: 策略配置基类
    - Strategy: 策略基类（继承自 nautilus_trader.trading.strategy.Strategy）

作者: QuantCell Team
版本: 2.0.0
日期: 2026-03-02
"""

from __future__ import annotations

import datetime as dt
import warnings
from abc import abstractmethod
from decimal import Decimal
from typing import Any, Optional

from loguru import logger

# 导入 NautilusTrader 原生 Strategy
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy
from nautilus_trader.trading.config import StrategyConfig as NautilusStrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.enums import OrderSide, TimeInForce


class StrategyConfig:
    """
    策略配置基类

    所有策略都需要继承此配置类
    提供基础的配置参数，子类可以扩展更多特定参数

    统一使用列表形式支持单品种和多品种回测，通过列表长度自动判断模式。

    Parameters
    ----------
    instrument_ids : list[Any]
        策略交易的品种ID列表，单品种时传 [instrument_id]
    bar_types : list[Any]
        策略订阅的K线类型列表，单品种时传 [bar_type]
    trade_size : Decimal
        每笔交易的数量
    log_level : str, default "INFO"
        日志级别，可选值: DEBUG, INFO, WARNING, ERROR

    Attributes
    ----------
    instrument_ids : list[Any]
        交易品种唯一标识符列表
    bar_types : list[Any]
        K线数据类型列表
    instrument_id : Any
        第一个交易品种ID（便捷访问，等同于 instrument_ids[0]）
    bar_type : Any
        第一个K线类型（便捷访问，等同于 bar_types[0]）
    trade_size : Decimal
        标准交易数量
    log_level : str
        日志输出级别

    Examples
    --------
    >>> # 单品种模式
    >>> config = StrategyConfig(
    ...     instrument_ids=[btc_instrument_id],
    ...     bar_types=[btc_bar_type],
    ... )
    >>> # 多品种模式
    >>> config = StrategyConfig(
    ...     instrument_ids=[btc_id, eth_id],
    ...     bar_types=[btc_bar_type, eth_bar_type],
    ... )
    """

    def __init__(
        self,
        instrument_ids: list[Any],
        bar_types: list[Any],
        trade_size: Decimal = Decimal("1.0"),
        log_level: str = "INFO",
    ):
        # 验证输入
        if not instrument_ids or not bar_types:
            raise ValueError("instrument_ids 和 bar_types 不能为空列表")
        if len(instrument_ids) != len(bar_types):
            raise ValueError(f"instrument_ids ({len(instrument_ids)}) 和 bar_types ({len(bar_types)}) 长度必须相同")

        # 统一使用列表存储
        self.instrument_ids = list(instrument_ids)
        self.bar_types = list(bar_types)

        # 便捷访问：第一个品种（向后兼容）
        self.instrument_id = instrument_ids[0]
        self.bar_type = bar_types[0]

        self.trade_size = trade_size
        self.log_level = log_level

    @property
    def is_multi_symbol(self) -> bool:
        """是否为多品种模式"""
        return len(self.instrument_ids) > 1

    def get_instrument_index(self, instrument_id: Any) -> int:
        """
        获取品种在列表中的索引

        Parameters
        ----------
        instrument_id : Any
            品种ID

        Returns
        -------
        int
            品种索引，未找到返回 -1
        """
        for i, inst_id in enumerate(self.instrument_ids):
            if inst_id == instrument_id:
                return i
        return -1

    def get_bar_type_for(self, instrument_id: Any) -> Any:
        """
        获取指定品种对应的K线类型

        Parameters
        ----------
        instrument_id : Any
            品种ID

        Returns
        -------
        Any
            K线类型，未找到返回 None
        """
        idx = self.get_instrument_index(instrument_id)
        return self.bar_types[idx] if idx >= 0 else None


class Strategy(NautilusStrategy):
    """
    策略基类

    为 QuantCell 项目提供统一的策略封装，继承自 NautilusTrader 原生 Strategy 类
    封装了常用的交易操作和生命周期管理，同时保留 NautilusTrader 的全部功能

    子类需要实现以下方法:
    - `on_bar`: 处理K线数据的核心交易逻辑
    - `calculate_indicators`: 计算技术指标
    - `generate_signals`: 生成交易信号

    Parameters
    ----------
    config : StrategyConfig
        策略配置对象

    Attributes
    ----------
    config : StrategyConfig
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
    >>> config = StrategyConfig(
    ...     instrument_ids=[instrument_id],
    ...     bar_types=[bar_type],
    ...     trade_size=Decimal("0.1"),
    ... )
    >>> strategy = MyStrategy(config)
    """

    def __init__(self, config: StrategyConfig) -> None:
        """
        初始化策略

        Args:
            config: 策略配置对象
        """
        # 创建 NautilusTrader 原生配置
        nautilus_config = NautilusStrategyConfig(
            strategy_id=config.__class__.__name__,
            order_id_tag="001",
            oms_type="NETTING",
        )

        # 调用父类初始化
        super().__init__(nautilus_config)

        # 使用 _strategy_config 避免与父类的 config 属性冲突
        self._strategy_config = config

        # 交易品种对象，在 on_start 中从缓存加载
        self.instrument: Any | None = None

        # 统计信息
        self.bars_processed: int = 0
        self.start_time: dt.datetime | None = None
        self.end_time: dt.datetime | None = None

    @property
    def config(self) -> StrategyConfig:
        """获取策略配置"""
        return self._strategy_config

    def on_start(self) -> None:
        """
        策略启动时调用

        执行以下操作:
        1. 记录策略启动时间
        2. 从缓存加载交易品种信息
        3. 订阅指定的K线数据（支持多品种）
        4. 输出启动日志

        子类可以重写此方法，但需要调用 super().on_start()
        """
        # 记录策略启动时间
        self.start_time = dt.datetime.now()
        logger.info(f"策略启动时间: {self.start_time}")

        # 从缓存加载交易品种信息（第一个品种作为主品种）
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument is None:
            logger.error(f"无法找到交易品种: {self.config.instrument_id}")
            self.stop()
            return

        logger.info(f"成功加载交易品种: {self.instrument.id}")

        # 订阅所有品种的K线数据（支持多品种）
        for i, bar_type in enumerate(self.config.bar_types):
            instrument_id = self.config.instrument_ids[i]
            self.subscribe_bars(bar_type)
            logger.info(f"已订阅K线数据: {instrument_id} -> {bar_type}")

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
            如果子类没有实现 _on_bar_impl 方法
        """
        self.bars_processed += 1

        # 子类应该重写 _on_bar_impl 方法实现具体的交易逻辑
        logger.debug(f"处理K线数据: {bar.ts_event}, 收盘价: {bar.close}")

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
        logger.info("已取消所有未成交订单")

        # 平掉所有持仓
        self.close_all_positions(self.config.instrument_id)
        logger.info("已平掉所有持仓")

        # 取消数据订阅
        self.unsubscribe_bars(self.config.bar_type)
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
        instrument_id: Any | None = None,
    ) -> None:
        """
        买入下单封装

        根据指定的参数创建并提交买入订单

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，默认为 None（市价单不需要）
            order_type: 订单类型，默认为 "MARKET"（市价单）
            time_in_force: 订单有效时间，默认为 "GTC"（一直有效）
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        # 获取目标品种ID
        target_id = instrument_id if instrument_id else self.config.instrument_id

        # 从缓存获取品种信息
        instrument = self.cache.instrument(target_id)
        if instrument is None:
            logger.error(f"无法找到交易品种: {target_id}")
            return

        # 使用默认数量
        qty = quantity if quantity else self.config.trade_size

        # 创建数量对象
        order_qty = instrument.make_qty(qty)

        # 创建订单
        if order_type == "MARKET":
            order = self.order_factory.market(
                instrument_id=target_id,
                order_side=OrderSide.BUY,
                quantity=order_qty,
            )
        else:
            order_price = instrument.make_price(price) if price else None
            order = self.order_factory.limit(
                instrument_id=target_id,
                order_side=OrderSide.BUY,
                quantity=order_qty,
                price=order_price,
                time_in_force=TimeInForce.GTC,
            )

        # 提交订单
        self.submit_order(order)
        logger.info(f"买入下单: {target_id}, 数量: {qty}, 类型: {order_type}")

    def sell(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: str = "MARKET",
        time_in_force: str = "GTC",
        instrument_id: Any | None = None,
    ) -> None:
        """
        卖出下单封装

        根据指定的参数创建并提交卖出订单

        Args:
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 订单价格，默认为 None（市价单不需要）
            order_type: 订单类型，默认为 "MARKET"（市价单）
            time_in_force: 订单有效时间，默认为 "GTC"（一直有效）
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        # 获取目标品种ID
        target_id = instrument_id if instrument_id else self.config.instrument_id

        # 从缓存获取品种信息
        instrument = self.cache.instrument(target_id)
        if instrument is None:
            logger.error(f"无法找到交易品种: {target_id}")
            return

        # 使用默认数量
        qty = quantity if quantity else self.config.trade_size

        # 创建数量对象
        order_qty = instrument.make_qty(qty)

        # 创建订单
        if order_type == "MARKET":
            order = self.order_factory.market(
                instrument_id=target_id,
                order_side=OrderSide.SELL,
                quantity=order_qty,
            )
        else:
            order_price = instrument.make_price(price) if price else None
            order = self.order_factory.limit(
                instrument_id=target_id,
                order_side=OrderSide.SELL,
                quantity=order_qty,
                price=order_price,
                time_in_force=TimeInForce.GTC,
            )

        # 提交订单
        self.submit_order(order)
        logger.info(f"卖出下单: {target_id}, 数量: {qty}, 类型: {order_type}")

    def close_position_by_instrument(self, position: Any | None = None, instrument_id: Any | None = None) -> None:
        """
        平仓封装

        平掉指定的持仓或指定品种的所有持仓

        Args:
            position: 要平仓的持仓对象，默认为 None（平掉所有持仓）
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Raises
        ------
        RuntimeError
            如果交易品种未加载
        """
        # 获取目标品种ID
        target_id = instrument_id if instrument_id else self.config.instrument_id

        if position:
            # 平掉指定持仓
            self.close_position_by_id(position.id)
            logger.info(f"平掉持仓: {position.id}")
        else:
            # 平掉指定品种的所有持仓
            self.close_all_positions(target_id)
            logger.info(f"平掉 {target_id} 的所有持仓")

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

        # 从缓存获取持仓
        positions = self.cache.positions_for_instrument(target_id)

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

        # 检查是否持有多头
        if self.portfolio.is_net_long(target_id):
            position = self.get_position(target_id)
            return position.quantity.as_decimal() if position else Decimal("0")

        # 检查是否持有空头
        if self.portfolio.is_net_short(target_id):
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
        return self.portfolio.is_flat(target_id)

    def is_long(self, instrument_id: Any | None = None) -> bool:
        """
        检查是否持有多头

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果持有多头返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        return self.portfolio.is_net_long(target_id)

    def is_short(self, instrument_id: Any | None = None) -> bool:
        """
        检查是否持有空头

        Args:
            instrument_id: 品种ID，默认为 None（使用配置中的 instrument_id）

        Returns:
            bool: 如果持有空头返回 True，否则返回 False
        """
        target_id = instrument_id if instrument_id else self.config.instrument_id
        return self.portfolio.is_net_short(target_id)

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


# 向后兼容别名（带弃用警告）
def _deprecated_alias(old_name: str, new_class: type) -> type:
    """创建带弃用警告的别名"""
    class _DeprecatedClass(new_class):
        def __init__(self, *args, **kwargs):
            warnings.warn(
                f"{old_name} 已弃用，请使用 {new_class.__name__} 代替",
                DeprecationWarning,
                stacklevel=2
            )
            super().__init__(*args, **kwargs)

    _DeprecatedClass.__name__ = old_name
    _DeprecatedClass.__qualname__ = old_name
    return _DeprecatedClass


# 向后兼容别名
EventDrivenStrategy = _deprecated_alias("EventDrivenStrategy", Strategy)
EventDrivenStrategyConfig = _deprecated_alias("EventDrivenStrategyConfig", StrategyConfig)
