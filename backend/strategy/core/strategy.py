# -*- coding: utf-8 -*-
"""
策略接口定义

提供与交易框架无关的策略基类和配置类。
策略脚本应该继承这些基类，实现具体的交易逻辑。

作者: QuantCell Team
版本: 1.0.0
日期: 2026-03-02
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Callable

from loguru import logger

from .data_types import (
    Bar,
    InstrumentId,
    OrderSide,
    OrderType,
    TimeInForce,
    Position,
    PositionSide,
)


@dataclass
class StrategyConfig:
    """
    策略配置基类

    所有策略配置都需要继承此类。
    提供基础的配置参数，支持单品种和多品种模式。

    Parameters
    ----------
    instrument_ids : List[InstrumentId]
        策略交易的品种ID列表
    bar_types : List[str]
        策略订阅的K线类型列表，例如 ["1-HOUR", "1-MINUTE"]
    trade_size : Decimal
        每笔交易的数量，默认 1.0
    log_level : str
        日志级别，默认 "INFO"

    Attributes
    ----------
    instrument_id : InstrumentId
        第一个交易品种（便捷访问）
    bar_type : str
        第一个K线类型（便捷访问）
    is_multi_symbol : bool
        是否为多品种模式

    Examples
    --------
    >>> # 单品种模式
    >>> config = StrategyConfig(
    ...     instrument_ids=[InstrumentId("BTCUSDT", "BINANCE")],
    ...     bar_types=["1-HOUR"],
    ... )
    >>> # 多品种模式
    >>> config = StrategyConfig(
    ...     instrument_ids=[
    ...         InstrumentId("BTCUSDT", "BINANCE"),
    ...         InstrumentId("ETHUSDT", "BINANCE"),
    ...     ],
    ...     bar_types=["1-HOUR", "1-HOUR"],
    ... )
    """

    instrument_ids: List[InstrumentId]
    bar_types: List[str]
    trade_size: Decimal = field(default_factory=lambda: Decimal("1.0"))
    log_level: str = "INFO"

    def __post_init__(self):
        """验证配置"""
        if not self.instrument_ids or not self.bar_types:
            raise ValueError("instrument_ids 和 bar_types 不能为空列表")
        if len(self.instrument_ids) != len(self.bar_types):
            raise ValueError(
                f"instrument_ids ({len(self.instrument_ids)}) 和 "
                f"bar_types ({len(self.bar_types)}) 长度必须相同"
            )

    @property
    def instrument_id(self) -> InstrumentId:
        """获取第一个品种ID（便捷访问）"""
        return self.instrument_ids[0]

    @property
    def bar_type(self) -> str:
        """获取第一个K线类型（便捷访问）"""
        return self.bar_types[0]

    @property
    def is_multi_symbol(self) -> bool:
        """是否为多品种模式"""
        return len(self.instrument_ids) > 1

    def get_bar_type_for(self, instrument_id: InstrumentId) -> Optional[str]:
        """
        获取指定品种对应的K线类型

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        Optional[str]
            K线类型，未找到返回 None
        """
        for i, inst_id in enumerate(self.instrument_ids):
            if inst_id == instrument_id:
                return self.bar_types[i]
        return None

    def get_instrument_index(self, instrument_id: InstrumentId) -> int:
        """
        获取品种在列表中的索引

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        int
            品种索引，未找到返回 -1
        """
        for i, inst_id in enumerate(self.instrument_ids):
            if inst_id == instrument_id:
                return i
        return -1


class StrategyBase(ABC):
    """
    策略基类抽象接口

    所有策略都需要继承此类并实现抽象方法。
    这个基类定义了策略的生命周期和交易接口，与具体执行环境无关。

    Parameters
    ----------
    config : StrategyConfig
        策略配置对象

    Attributes
    ----------
    config : StrategyConfig
        策略配置
    is_running : bool
        策略是否正在运行
    bars_processed : int
        已处理的K线数量
    start_time : Optional[datetime]
        策略启动时间
    end_time : Optional[datetime]
        策略停止时间

    Examples
    --------
    >>> class MyStrategy(StrategyBase):
    ...     def on_bar(self, bar: Bar) -> None:
    ...         if self.should_buy(bar):
    ...             self.buy(bar.instrument_id, Decimal("0.1"))
    """

    def __init__(self, config: StrategyConfig) -> None:
        """
        初始化策略

        Parameters
        ----------
        config : StrategyConfig
            策略配置对象
        """
        self.config = config
        self.is_running: bool = False
        self.bars_processed: int = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

        # 内部状态（由子类使用）
        self._positions: Dict[InstrumentId, Position] = {}
        self._orders: Dict[str, Any] = {}

    # ==================== 生命周期方法 ====================

    @abstractmethod
    def on_start(self) -> None:
        """
        策略启动时调用

        子类应该在此方法中：
        1. 初始化策略状态
        2. 订阅数据（如果需要）
        3. 输出启动日志

        Examples
        --------
        >>> def on_start(self) -> None:
        ...     self.log_info("策略启动")
        ...     # 初始化指标计算
        ...     self.prices = {}
        """
        pass

    @abstractmethod
    def on_bar(self, bar: Bar) -> None:
        """
        收到K线数据时调用

        这是策略的核心方法，子类必须实现具体的交易逻辑。

        Parameters
        ----------
        bar : Bar
            K线数据对象

        Examples
        --------
        >>> def on_bar(self, bar: Bar) -> None:
        ...     # 计算指标
        ...     sma = self.calculate_sma(bar.close)
        ...     # 生成信号
        ...     if self.should_buy(sma, bar.close):
        ...         self.buy(bar.instrument_id, self.config.trade_size)
        """
        pass

    @abstractmethod
    def on_stop(self) -> None:
        """
        策略停止时调用

        子类应该在此方法中：
        1. 清理资源
        2. 平掉持仓（如果需要）
        3. 输出统计日志

        Examples
        --------
        >>> def on_stop(self) -> None:
        ...     self.log_info("策略停止")
        ...     # 平掉所有持仓
        ...     for inst_id in self.config.instrument_ids:
        ...         if not self.is_flat(inst_id):
        ...             self.close_position(inst_id)
        """
        pass

    # ==================== 交易接口 ====================
    # 注意：以下方法由执行环境（回测引擎或实盘交易引擎）提供实现
    # 策略开发者不需要实现这些方法，只需要调用它们

    def buy(
        self,
        instrument_id: InstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        买入下单

        此方法由执行环境提供实现。在回测环境中，由 StrategyAdapter 实现；
        在实盘环境中，由相应的交易引擎实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识
        quantity : Decimal
            交易数量
        price : Optional[Decimal]
            订单价格，市价单为 None
        order_type : OrderType
            订单类型，默认 MARKET
        time_in_force : TimeInForce
            订单有效期，默认 GTC

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "buy() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def sell(
        self,
        instrument_id: InstrumentId,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        卖出下单

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识
        quantity : Decimal
            交易数量
        price : Optional[Decimal]
            订单价格，市价单为 None
        order_type : OrderType
            订单类型，默认 MARKET
        time_in_force : TimeInForce
            订单有效期，默认 GTC

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "sell() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def close_position(self, instrument_id: InstrumentId) -> None:
        """
        平仓

        平掉指定品种的所有持仓。此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "close_position() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def cancel_order(self, order_id: str) -> None:
        """
        取消订单

        此方法由执行环境提供实现。

        Parameters
        ----------
        order_id : str
            订单ID

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "cancel_order() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def cancel_all_orders(self, instrument_id: Optional[InstrumentId] = None) -> None:
        """
        取消所有订单

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : Optional[InstrumentId]
            品种标识，None 表示取消所有品种的订单

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "cancel_all_orders() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    # ==================== 持仓查询接口 ====================
    # 注意：以下方法由执行环境提供实现

    def get_position(self, instrument_id: InstrumentId) -> Optional[Position]:
        """
        获取持仓信息

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        Optional[Position]
            持仓对象，如果没有持仓返回 None

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "get_position() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def get_position_size(self, instrument_id: InstrumentId) -> Decimal:
        """
        获取持仓数量

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        Decimal
            持仓数量，正数表示多头，负数表示空头，0 表示空仓

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "get_position_size() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def is_flat(self, instrument_id: InstrumentId) -> bool:
        """
        检查是否空仓

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        bool
            如果没有持仓返回 True

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "is_flat() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def is_long(self, instrument_id: InstrumentId) -> bool:
        """
        检查是否持有多头

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        bool
            如果持有多头返回 True

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "is_long() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    def is_short(self, instrument_id: InstrumentId) -> bool:
        """
        检查是否持有空头

        此方法由执行环境提供实现。

        Parameters
        ----------
        instrument_id : InstrumentId
            品种标识

        Returns
        -------
        bool
            如果持有空头返回 True

        Raises
        ------
        NotImplementedError
            如果执行环境没有提供实现
        """
        raise NotImplementedError(
            "is_short() 方法必须由执行环境提供实现。"
            "请确保策略在正确的执行环境中运行（如回测引擎或实盘交易引擎）。"
        )

    # ==================== 日志接口 ====================

    def log_info(self, message: str) -> None:
        """
        输出信息日志

        Parameters
        ----------
        message : str
            日志消息
        """
        logger.info(message)

    def log_debug(self, message: str) -> None:
        """
        输出调试日志

        Parameters
        ----------
        message : str
            日志消息
        """
        logger.debug(message)

    def log_warning(self, message: str) -> None:
        """
        输出警告日志

        Parameters
        ----------
        message : str
            日志消息
        """
        logger.warning(message)

    def log_error(self, message: str) -> None:
        """
        输出错误日志

        Parameters
        ----------
        message : str
            日志消息
        """
        logger.error(message)

    # ==================== 工具方法 ====================

    def get_bar_instrument(self, bar: Bar) -> InstrumentId:
        """
        获取K线对应的品种ID

        Parameters
        ----------
        bar : Bar
            K线数据

        Returns
        -------
        InstrumentId
            品种标识
        """
        return bar.instrument_id

    def format_price(self, price: float, decimals: int = 2) -> str:
        """
        格式化价格显示

        Parameters
        ----------
        price : float
            价格
        decimals : int
            小数位数

        Returns
        -------
        str
            格式化后的价格字符串
        """
        return f"{price:.{decimals}f}"


# 类型别名，用于向后兼容
Strategy = StrategyBase
