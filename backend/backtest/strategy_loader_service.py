# -*- coding: utf-8 -*-
"""
策略加载服务模块（基于 axond 体系）

从策略文件加载和实例化策略类，支持：
- axond.AxonStrategy 子类
- backtest.strategies.EventDrivenStrategy 子类
- backtest.strategies.StrategyAdapter 子类

提供统一的策略加载接口，支持单品种和多品种场景。
完全基于 axond 体系，不依赖任何外部量化框架。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
"""

import importlib
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Type

from utils.logger import get_logger, LogType

# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class StrategyLoadError(Exception):
    """策略加载异常"""
    pass


class StrategyLoaderService:
    """
    策略加载服务（基于 axond 体系）

    负责从策略文件中查找、加载和实例化策略类。
    支持多种策略基类和配置模式。

    使用示例：
        # 加载事件驱动策略（多品种）
        strategy = StrategyLoaderService.load_event_strategy_multi(
            "simple_dual_ma",
            params={"fast_period": 10, "slow_period": 30},
            bar_types={"BTCUSDT": "1h"},
            instruments={"BTCUSDT": InstrumentId("BTCUSDT", "binance")},
        )

        # 加载默认引擎策略
        strategy = StrategyLoaderService.load_strategy("simple_dual_ma", params={})
    """

    # axond 策略基类
    _axon_strategy_base: Optional[Type] = None
    _axon_strategy_config: Optional[Type] = None
    # 事件驱动策略基类
    _event_strategy_base: Optional[Type] = None

    @classmethod
    def _get_axon_strategy_base(cls) -> Type:
        """获取 axond.AxonStrategy 基类（延迟导入）"""
        if cls._axon_strategy_base is None:
            from axond.axon_strategy import AxonStrategy
            cls._axon_strategy_base = AxonStrategy
        return cls._axon_strategy_base

    @classmethod
    def _get_axon_strategy_config(cls) -> Type:
        """获取 axond.StrategyConfig 基类（延迟导入）"""
        if cls._axon_strategy_config is None:
            from axond.strategy_config import StrategyConfig
            cls._axon_strategy_config = StrategyConfig
        return cls._axon_strategy_config

    @classmethod
    def _get_event_strategy_base(cls) -> Type:
        """获取 EventDrivenStrategy 基类（延迟导入）"""
        if cls._event_strategy_base is None:
            from backtest.strategies.event_strategy import EventDrivenStrategy
            cls._event_strategy_base = EventDrivenStrategy
        return cls._event_strategy_base

    @staticmethod
    def _get_strategies_dir() -> Path:
        """获取策略目录路径

        优先查找 strategy/example/strategies（示例策略），
        然后查找 strategies（旧版兼容）。
        """
        backend_path = Path(__file__).resolve().parent.parent

        # 优先查找示例策略目录
        example_dir = backend_path / "strategy" / "example" / "strategies"
        if example_dir.exists():
            return example_dir

        # 兼容旧版 strategies 目录
        legacy_dir = backend_path / "strategies"
        if legacy_dir.exists():
            return legacy_dir

        raise StrategyLoadError(f"找不到策略目录: {example_dir} 或 {legacy_dir}")

    @staticmethod
    def load_strategy(strategy_name: str, strategy_params: dict):
        """
        加载策略（通用入口）

        Args:
            strategy_name: 策略名称（文件名，不含 .py 后缀）
            strategy_params: 策略参数字典

        Returns:
            策略实例

        Raises:
            StrategyLoadError: 当策略加载失败时
        """
        try:
            strategies_dir = StrategyLoaderService._get_strategies_dir()

            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))

            if strategy_name in sys.modules:
                del sys.modules[strategy_name]

            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                raise StrategyLoadError(f"策略文件不存在: {strategy_file}")

            module = importlib.import_module(strategy_name)

            # 查找策略类
            strategy_class = StrategyLoaderService._find_strategy_class(module)

            if strategy_class is None:
                raise StrategyLoadError(
                    f"在模块 {strategy_name} 中找不到策略类"
                )

            # 实例化策略
            instance = StrategyLoaderService._instantiate_strategy(
                strategy_class, strategy_params, None, None
            )

            logger.info(f"成功加载策略: {strategy_class.__name__}")
            return instance

        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            raise StrategyLoadError(f"加载策略失败: {e}") from e

    @staticmethod
    def load_event_strategy(
        strategy_name: str,
        strategy_params: dict,
        bar_type: str,
        instrument_id,
    ):
        """
        加载事件驱动策略（单品种版本）

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            bar_type: K 线类型字符串
            instrument_id: InstrumentId 对象

        Returns:
            策略实例或 None
        """
        return StrategyLoaderService.load_event_strategy_multi(
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            bar_types={"_default": bar_type},
            instruments={"_default": instrument_id},
        )

    @staticmethod
    def load_event_strategy_multi(
        strategy_name: str,
        strategy_params: dict,
        bar_types: dict,
        instruments: dict,
    ):
        """
        加载支持多品种的事件驱动策略

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            bar_types: 品种到 bar_type 字符串的映射字典
            instruments: 品种到 InstrumentId 的映射字典

        Returns:
            策略实例或 None
        """
        try:
            strategies_dir = StrategyLoaderService._get_strategies_dir()

            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))

            if strategy_name in sys.modules:
                del sys.modules[strategy_name]

            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.info(f"策略文件不存在: {strategy_file}")
                return None

            module = importlib.import_module(strategy_name)

            # 查找策略类
            strategy_class = StrategyLoaderService._find_strategy_class(module)

            if strategy_class is None:
                logger.info(f"在模块 {strategy_name} 中找不到策略类")
                return None

            # 提取 instrument_ids 和 bar_types 列表
            instrument_ids_list = list(instruments.values())
            bar_types_list = list(bar_types.values())

            # 实例化策略
            instance = StrategyLoaderService._instantiate_strategy(
                strategy_class,
                strategy_params,
                instrument_ids_list,
                bar_types_list,
            )

            logger.info(
                f"成功加载多品种事件驱动策略: {strategy_class.__name__}"
                f"（支持 {len(instruments)} 个品种）"
            )
            return instance

        except Exception as e:
            logger.error(f"加载多品种事件驱动策略失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _find_strategy_class(module) -> Optional[Type]:
        """在模块中查找策略类

        优先级：
        1. axond.AxonStrategy 子类
        2. backtest.strategies.event_strategy.EventDrivenStrategy 子类
        3. strategy.core.StrategyBase 子类

        Args:
            module: 策略模块

        Returns:
            策略类或 None
        """
        axon_base = StrategyLoaderService._get_axon_strategy_base()
        event_base = StrategyLoaderService._get_event_strategy_base()

        # 策略核心基类（可选）
        core_base = None
        try:
            from strategy.core.strategy_core import StrategyCore

            core_base = StrategyCore
        except ImportError:
            pass

        found_class: Optional[Type] = None
        found_priority = -1

        for name in dir(module):
            obj = getattr(module, name)
            if not isinstance(obj, type):
                continue

            # 跳过基类本身
            if obj is axon_base or obj is event_base or obj is core_base:
                continue

            # 检查是否是 AxonStrategy 子类（优先级 3）
            if axon_base and issubclass(obj, axon_base):
                if found_priority < 3:
                    found_class = obj
                    found_priority = 3
                    logger.info(f"找到 axond 策略类: {name}")
                continue

            # 检查是否是 EventDrivenStrategy 子类（优先级 2）
            if event_base and issubclass(obj, event_base):
                if found_priority < 2:
                    found_class = obj
                    found_priority = 2
                    logger.info(f"找到事件驱动策略类: {name}")
                continue

            # 检查是否是 StrategyCore 子类（优先级 1）
            if core_base and issubclass(obj, core_base):
                if found_priority < 1:
                    found_class = obj
                    found_priority = 1
                    logger.info(f"找到策略核心类: {name}")
                continue

        return found_class

    @staticmethod
    def _instantiate_strategy(
        strategy_class: Type,
        strategy_params: dict,
        instrument_ids_list: Optional[list],
        bar_types_list: Optional[list],
    ):
        """实例化策略类

        根据策略类的构造函数签名决定如何传递参数：
        1. 接受 config 参数：创建配置对象后传入
        2. 直接接受参数：直接传入

        Args:
            strategy_class: 策略类
            strategy_params: 策略参数
            instrument_ids_list: 品种 ID 列表（可选）
            bar_types_list: bar_type 列表（可选）

        Returns:
            策略实例
        """
        import inspect

        # 获取构造函数签名
        try:
            sig = inspect.signature(strategy_class.__init__)
            param_names = list(sig.parameters.keys())
        except (TypeError, ValueError):
            param_names = []

        # 检查是否需要 config 对象
        if "config" in param_names:
            # 使用 axond.StrategyConfig
            config_class = StrategyLoaderService._get_axon_strategy_config()

            config_params = dict(strategy_params)

            # 添加品种和 bar_type
            if instrument_ids_list is not None:
                config_params["instrument_ids"] = instrument_ids_list
            if bar_types_list is not None:
                config_params["bar_types"] = bar_types_list

            # 过滤 config 接受的参数
            config_field_names = []
            try:
                import dataclasses
                if dataclasses.is_dataclass(config_class):
                    config_field_names = [
                        f.name for f in dataclasses.fields(config_class)
                    ]
            except Exception:
                pass

            if config_field_names:
                filtered = {
                    k: v for k, v in config_params.items()
                    if k in config_field_names
                }
            else:
                filtered = config_params

            config = config_class(**filtered)
            return strategy_class(config)
        else:
            # 直接传递参数
            params = dict(strategy_params)
            if instrument_ids_list is not None:
                params["instrument_ids"] = instrument_ids_list
            if bar_types_list is not None:
                params["bar_types"] = bar_types_list
            return strategy_class(**params)
