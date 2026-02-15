# -*- coding: utf-8 -*-
"""
回测引擎抽象基类模块

定义所有回测引擎必须实现的接口，确保引擎之间的一致性
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from enum import Enum
from loguru import logger


class EngineType(Enum):
    """
    回测引擎类型枚举
    """
    EVENT_DRIVEN = "event_driven"      # 事件驱动引擎
    VECTORIZED = "vectorized"          # 向量化引擎
    CONCURRENT = "concurrent"          # 并发引擎
    ASYNC_EVENT = "async_event"        # 异步事件引擎
    DEFAULT = "default"                # 默认回测引擎
    LEGACY = "legacy"                  # 传统回测引擎


class BacktestEngineBase(ABC):
    """
    回测引擎抽象基类

    所有回测引擎必须继承此类并实现其抽象方法。
    提供统一的接口规范，确保不同引擎实现之间的一致性。

    Attributes:
        engine_type: 引擎类型标识
        config: 引擎配置字典
        is_initialized: 引擎是否已初始化
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化回测引擎基类

        Args:
            config: 引擎配置字典，包含回测参数、初始资金等
        """
        self._config = config or {}
        self._is_initialized = False
        self._results = {}

    @property
    @abstractmethod
    def engine_type(self) -> EngineType:
        """
        引擎类型属性

        Returns:
            EngineType: 返回当前引擎的类型标识
        """
        pass

    @property
    def config(self) -> Dict[str, Any]:
        """
        引擎配置属性

        Returns:
            Dict[str, Any]: 引擎配置字典
        """
        return self._config

    @config.setter
    def config(self, value: Dict[str, Any]):
        """
        设置引擎配置

        Args:
            value: 新的配置字典
        """
        self._config = value

    @property
    def is_initialized(self) -> bool:
        """
        引擎初始化状态属性

        Returns:
            bool: 引擎是否已完成初始化
        """
        return self._is_initialized

    @abstractmethod
    def initialize(self) -> None:
        """
        初始化回测引擎

        执行引擎启动前的准备工作，包括：
        - 加载历史数据
        - 初始化账户状态
        - 设置交易环境
        - 注册事件处理器

        Raises:
            RuntimeError: 初始化失败时抛出
        """
        pass

    @abstractmethod
    def run_backtest(self) -> Dict[str, Any]:
        """
        执行回测

        运行完整的回测流程，处理所有历史数据并生成交易记录。

        Returns:
            Dict[str, Any]: 回测结果字典，包含：
                - trades: 交易记录列表
                - equity_curve: 权益曲线
                - metrics: 绩效指标
                - positions: 持仓记录

        Raises:
            RuntimeError: 回测执行失败时抛出
        """
        pass

    @abstractmethod
    def get_results(self) -> Dict[str, Any]:
        """
        获取回测结果

        返回最近一次回测的完整结果。

        Returns:
            Dict[str, Any]: 回测结果字典，包含：
                - total_return: 总收益率
                - sharpe_ratio: 夏普比率
                - max_drawdown: 最大回撤
                - win_rate: 胜率
                - profit_factor: 盈亏比
                - trades: 完整交易记录

        Raises:
            RuntimeError: 尚未执行回测时抛出
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """
        清理资源

        释放引擎占用的所有资源，包括：
        - 关闭数据连接
        - 释放内存缓存
        - 停止后台线程
        - 重置内部状态

        此方法应在回测完成后调用，确保资源正确释放。
        """
        pass

    def _validate_config(self) -> bool:
        """
        验证配置有效性（内部方法）

        检查配置字典是否包含必需的参数。

        Returns:
            bool: 配置是否有效
        """
        required_keys = ['initial_capital', 'start_date', 'end_date']
        for key in required_keys:
            if key not in self._config:
                logger.error(f"配置缺少必需参数: {key}")
                return False
        return True

    def _reset_state(self) -> None:
        """
        重置引擎状态（内部方法）

        将引擎状态重置为初始状态，便于重新运行回测。
        """
        self._is_initialized = False
        self._results = {}
        logger.debug("引擎状态已重置")
