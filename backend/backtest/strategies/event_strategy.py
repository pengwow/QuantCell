# -*- coding: utf-8 -*-
"""
事件驱动策略基类（基于 axond 体系）

提供事件驱动架构的策略基类，支持高性能回测和实盘交易。
不依赖任何外部量化框架，纯 axond 实现。

包含:
    - EventDrivenStrategyConfig: 事件驱动策略配置基类
    - EventDrivenStrategy: 事件驱动策略基类

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

from __future__ import annotations

import datetime as dt
from abc import abstractmethod
from decimal import Decimal
from typing import Any, Optional, List

from axond.types import InstrumentId, Bar
from axond.axon_strategy import AxonStrategy
from axond.strategy_config import StrategyConfig
from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class EventDrivenStrategyConfig:
    """
    事件驱动策略配置基类

    所有事件驱动策略都需要继承此配置类
    提供基础的配置参数，子类可以扩展更多特定参数

    统一使用列表形式支持单品种和多品种回测，通过列表长度自动判断模式。

    Parameters
    ----------
    instrument_ids : list[InstrumentId]
        策略交易的品种ID列表，单品种时传 [instrument_id]
    bar_types : list[str]
        策略订阅的K线类型列表，单品种时传 [bar_type]
    trade_size : Decimal
        每笔交易的数量
    log_level : str, default "INFO"
        日志级别，可选值: DEBUG, INFO, WARNING, ERROR

    Examples
    --------
    >>> # 单品种模式
    >>> config = EventDrivenStrategyConfig(
    ...     instrument_ids=[btc_instrument_id],
    ...     bar_types=["1h"],
    ... )
    >>> # 多品种模式
    >>> config = EventDrivenStrategyConfig(
    ...     instrument_ids=[btc_id, eth_id],
    ...     bar_types=["1h", "1h"],
    ... )
    """

    def __init__(
        self,
        instrument_ids: List[InstrumentId],
        bar_types: List[str],
        trade_size: Decimal = Decimal("1.0"),
        log_level: str = "INFO",
    ):
        # 验证输入
        if not instrument_ids or not bar_types:
            raise ValueError("instrument_ids 和 bar_types 不能为空列表")
        if len(instrument_ids) != len(bar_types):
            raise ValueError(
                f"instrument_ids ({len(instrument_ids)}) 和 "
                f"bar_types ({len(bar_types)}) 长度必须相同"
            )

        # 统一使用列表存储
        self.instrument_ids: List[InstrumentId] = list(instrument_ids)
        self.bar_types: List[str] = list(bar_types)

        # 便捷访问：第一个品种
        self.instrument_id: InstrumentId = instrument_ids[0]
        self.bar_type: str = bar_types[0]

        self.trade_size = trade_size
        self.log_level = log_level

    @property
    def is_multi_symbol(self) -> bool:
        """是否为多品种模式"""
        return len(self.instrument_ids) > 1

    def get_instrument_index(self, instrument_id: InstrumentId) -> int:
        """获取品种在列表中的索引，未找到返回 -1"""
        for i, inst_id in enumerate(self.instrument_ids):
            if inst_id == instrument_id:
                return i
        return -1

    def get_bar_type_for(self, instrument_id: InstrumentId) -> Optional[str]:
        """获取指定品种对应的K线类型，未找到返回 None"""
        idx = self.get_instrument_index(instrument_id)
        return self.bar_types[idx] if idx >= 0 else None

    def to_strategy_config(self) -> StrategyConfig:
        """转换为 axond StrategyConfig"""
        return StrategyConfig(
            instrument_ids=self.instrument_ids,
            bar_types=self.bar_types,
            trade_size=self.trade_size,
            log_level=self.log_level,
        )


class EventDrivenStrategy(AxonStrategy):
    """
    事件驱动策略基类（基于 axond 体系）

    为 QuantCell 项目提供统一的事件驱动策略封装
    封装了常用的交易操作和生命周期管理

    子类需要实现以下方法:
    - `_on_bar_impl`: 处理K线数据的核心交易逻辑

    Parameters
    ----------
    config : EventDrivenStrategyConfig
        策略配置对象

    Examples
    --------
    >>> config = EventDrivenStrategyConfig(
    ...     instrument_ids=[InstrumentId("BTCUSDT", "binance")],
    ...     bar_types=["1h"],
    ...     trade_size=Decimal("0.1"),
    ... )
    >>> strategy = MyStrategy(config)
    """

    def __init__(self, config: EventDrivenStrategyConfig) -> None:
        """初始化策略

        Args:
            config: 策略配置对象
        """
        # 转换配置为 axond StrategyConfig
        axon_config = config.to_strategy_config()
        super().__init__(axon_config)

        # 保存原始配置（包含额外方法）
        self.event_config = config

        # 统计信息
        self.bars_processed: int = 0
        self.start_time: Optional[dt.datetime] = None
        self.end_time: Optional[dt.datetime] = None

    def on_start(self) -> None:
        """
        策略启动时调用

        执行以下操作:
        1. 记录策略启动时间
        2. 初始化状态

        子类可以重写此方法，但需要调用 super().on_start()
        """
        self.start_time = dt.datetime.now()
        logger.info(f"策略启动时间: {self.start_time}")

    def on_bar(self, bar: Bar) -> None:
        """
        收到K线数据时调用

        这是策略的核心方法，子类必须实现具体的交易逻辑
        基类只负责统计处理过的K线数量

        Args:
            bar: K线数据对象
        """
        self.bars_processed += 1
        logger.debug(f"处理K线数据: {bar.timestamp}, 收盘价: {bar.close}")
        # 调用子类实现
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
        2. 输出统计日志

        子类可以重写此方法，但需要调用 super().on_stop()
        """
        self.end_time = dt.datetime.now()

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
        symbol: Optional[str] = None,
        quantity: Optional[Decimal] = None,
        price: Optional[float] = None,
    ) -> dict:
        """
        买入下单封装

        Args:
            symbol: 交易对符号，默认为 None（使用配置中的第一个品种）
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 限价价格，默认为 None（市价单）

        Returns:
            订单字典
        """
        target_symbol = symbol or self.event_config.instrument_id.symbol
        qty = quantity if quantity is not None else self.event_config.trade_size
        return super().buy(target_symbol, float(qty), price)

    def sell(
        self,
        symbol: Optional[str] = None,
        quantity: Optional[Decimal] = None,
        price: Optional[float] = None,
    ) -> dict:
        """
        卖出下单封装

        Args:
            symbol: 交易对符号，默认为 None（使用配置中的第一个品种）
            quantity: 交易数量，默认为 None（使用配置中的 trade_size）
            price: 限价价格，默认为 None（市价单）

        Returns:
            订单字典
        """
        target_symbol = symbol or self.event_config.instrument_id.symbol
        qty = quantity if quantity is not None else self.event_config.trade_size
        return super().sell(target_symbol, float(qty), price)

    def close_position(self, symbol: Optional[str] = None) -> dict:
        """
        平仓封装

        Args:
            symbol: 交易对符号，默认为 None（使用配置中的第一个品种）

        Returns:
            订单字典
        """
        target_symbol = symbol or self.event_config.instrument_id.symbol
        return super().close_position(target_symbol)

    def get_position_size(self, symbol: Optional[str] = None) -> float:
        """
        获取持仓数量

        Args:
            symbol: 交易对符号

        Returns:
            持仓数量
        """
        target_symbol = symbol or self.event_config.instrument_id.symbol
        return super().get_position_size(target_symbol)

    def is_flat(self, symbol: Optional[str] = None) -> bool:
        """检查是否空仓"""
        return self.get_position_size(symbol) == 0.0

    def is_long(self, symbol: Optional[str] = None) -> bool:
        """检查是否持有多头"""
        return self.get_position_size(symbol) > 0.0

    def is_short(self, symbol: Optional[str] = None) -> bool:
        """检查是否持有空头"""
        return self.get_position_size(symbol) < 0.0

    def log_info(self, message: str) -> None:
        """输出信息日志"""
        logger.info(message)

    def log_debug(self, message: str) -> None:
        """输出调试日志"""
        logger.debug(message)

    def log_warning(self, message: str) -> None:
        """输出警告日志"""
        logger.warning(message)

    def log_error(self, message: str) -> None:
        """输出错误日志"""
        logger.error(message)
