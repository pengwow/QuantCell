# -*- coding: utf-8 -*-
"""
实盘交易适配器模块

提供 QuantCell 策略与 axon_quant 交易引擎之间的适配功能。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-24
"""

from __future__ import annotations

import importlib
import inspect
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from utils.logger import get_logger, LogType

logger = get_logger(__name__, LogType.STRATEGY)

from strategy.core.data_types import (
    Bar as QCBar,
    InstrumentId as QCInstrumentId,
    OrderSide,
    OrderType,
    TimeInForce,
    PositionSide,
)
from strategy.core.strategy import StrategyConfig as QCStrategyConfig
from strategy.core.strategy import StrategyBase as QCStrategyBase


class TradingAdapterError(Exception):
    """交易适配器异常基类"""
    pass


class StrategyAdapterConfigError(TradingAdapterError):
    """配置错误"""
    pass


class TradingStrategyAdapter:
    """
    实盘交易策略适配器类

    将 QuantCell 策略包装为 axon_quant 交易引擎可执行的策略。

    Attributes
    ----------
    qc_strategy : QCStrategyBase
        QuantCell 策略实例
    config : dict
        交易配置
    is_paused : bool
        策略是否暂停
    bars_processed : int
        已处理的 K 线数量
    """

    def __init__(
        self,
        qc_strategy: QCStrategyBase,
        config: Any,
    ) -> None:
        """
        初始化适配器

        Parameters
        ----------
        qc_strategy : QCStrategyBase
            QuantCell 策略实例
        config : dict
            交易配置
        """
        if not isinstance(qc_strategy, QCStrategyBase):
            raise StrategyAdapterConfigError(
                f"qc_strategy 必须是 QCStrategyBase 的子类，"
                f"实际类型: {type(qc_strategy).__name__}"
            )

        self.qc_strategy = qc_strategy
        self.config = config
        self._is_paused = False
        self._bars_processed = 0
        self._ticks_processed = 0
        self._start_time: Optional[datetime] = None

        logger.info(f"交易策略适配器已初始化: {qc_strategy.__class__.__name__}")

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def bars_processed(self) -> int:
        return self._bars_processed

    def on_bar(self, bar: QCBar) -> None:
        """处理 K 线数据"""
        if self._is_paused:
            return

        self._bars_processed += 1
        self.qc_strategy.on_bar(bar)

    def on_start(self) -> None:
        """策略启动"""
        self._start_time = datetime.now()
        self.qc_strategy.on_start()
        logger.info("策略已启动")

    def on_stop(self) -> None:
        """策略停止"""
        self.qc_strategy.on_stop()
        logger.info("策略已停止")

    def pause(self) -> None:
        """暂停策略"""
        self._is_paused = True
        logger.info("策略已暂停")

    def resume(self) -> None:
        """恢复策略"""
        self._is_paused = False
        logger.info("策略已恢复")


def create_adapter(
    strategy_name: str,
    strategy_params: Dict[str, Any],
    trading_config: Dict[str, Any],
) -> TradingStrategyAdapter:
    """
    创建交易适配器实例

    Parameters
    ----------
    strategy_name : str
        策略名称
    strategy_params : dict
        策略参数
    trading_config : dict
        交易配置

    Returns
    -------
    TradingStrategyAdapter
        适配器实例
    """
    # 动态加载策略模块
    module_path = f"strategies.{strategy_name}"
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise StrategyAdapterConfigError(f"无法加载策略模块 {module_path}: {e}")

    # 查找策略类
    strategy_class = None
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if issubclass(obj, QCStrategyBase) and obj is not QCStrategyBase:
            strategy_class = obj
            break

    if strategy_class is None:
        raise StrategyAdapterConfigError(f"在 {module_path} 中未找到策略类")

    # 创建策略实例
    qc_config = QCStrategyConfig(**strategy_params)
    qc_strategy = strategy_class(qc_config)

    # 创建适配器
    adapter = TradingStrategyAdapter(qc_strategy, trading_config)

    return adapter


__all__ = [
    "TradingStrategyAdapter",
    "TradingAdapterError",
    "StrategyAdapterConfigError",
    "create_adapter",
]
