"""
策略加载服务模块

从策略文件加载和实例化事件驱动策略类。
支持 EventDrivenStrategy 类型的策略加载。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

import importlib
import sys
from typing import Any, Dict, Optional
from pathlib import Path
from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class StrategyLoadError(Exception):
    """策略加载异常"""
    pass


class StrategyLoaderService:
    """
    策略加载服务

    负责从策略文件中查找、加载和实例化事件驱动策略类。
    支持单品种和多品种场景。

    使用示例：
        # 加载事件驱动策略（多品种）
        strategy = StrategyLoaderService.load_event_strategy_multi(
            "sma_crossover",
            params={"fast_period": 10, "slow_period": 30},
            bar_types={"BTCUSDT": bar_type},
            instruments={"BTCUSDT": instrument}
        )
    """

    @staticmethod
    def load_event_strategy_multi(
        strategy_name: str,
        strategy_params: dict,
        bar_types: dict,
        instruments: dict
    ):
        """
        加载支持多品种的事件驱动策略

        Args:
            strategy_name: 策略名称
            strategy_params: 策略参数
            bar_types: 品种到BarType的映射字典
            instruments: 品种到Instrument的映射字典

        Returns:
            EventDrivenStrategy: 策略实例或None
        """
        try:
            backend_path = Path(__file__).resolve().parent.parent
            strategies_dir = backend_path / 'strategies'

            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))

            if strategy_name in sys.modules:
                del sys.modules[strategy_name]

            strategy_file = strategies_dir / f"{strategy_name}.py"
            if not strategy_file.exists():
                logger.info(f"策略文件不存在: {strategy_file}")
                return None

            module = importlib.import_module(strategy_name)

            # 查找策略类和配置类
            strategy_class = None
            config_class = None

            try:
                from backtest.strategies.event_strategy import (
                    EventDrivenStrategy,
                    EventDrivenStrategyConfig
                )
            except ImportError as e:
                logger.error(f"导入 EventDrivenStrategy 失败: {e}")
                return None

            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type):
                    if issubclass(obj, EventDrivenStrategy) and obj != EventDrivenStrategy:
                        strategy_class = obj
                        logger.info(f"找到策略类: {name}")

                    if issubclass(obj, EventDrivenStrategyConfig) and obj != EventDrivenStrategyConfig:
                        config_class = obj
                        logger.info(f"找到配置类: {name}")

            if strategy_class is None:
                logger.info(f"在模块 {strategy_name} 中找不到事件驱动策略类")
                return None

            # 准备参数
            instrument_ids_list = list(instruments.keys())
            bar_types_list = list(bar_types.values())

            config = None
            if config_class:
                config_params = strategy_params.copy()

                config_param_names = StrategyLoaderService._get_class_param_names(config_class)

                if 'instrument_ids' in config_param_names:
                    config_params['instrument_ids'] = instrument_ids_list
                elif 'instrument_id' in config_param_names:
                    config_params['instrument_id'] = instrument_ids_list[0] if instrument_ids_list else None

                if 'bar_types' in config_param_names:
                    config_params['bar_types'] = bar_types_list
                elif 'bar_type' in config_param_names:
                    config_params['bar_type'] = bar_types_list[0] if bar_types_list else None

                # 移除不相关的参数
                config_params = {k: v for k, v in config_params.items()
                                if k in config_param_names}

                config = config_class(**config_params)
                user_strategy = strategy_class(config)
            else:
                strategy_params_copy = strategy_params.copy()

                strategy_param_names = StrategyLoaderService._get_class_param_names(strategy_class)

                if 'instrument_ids' in strategy_param_names:
                    strategy_params_copy['instrument_ids'] = instrument_ids_list
                elif 'instrument_id' in strategy_param_names:
                    strategy_params_copy['instrument_id'] = instrument_ids_list[0] if instrument_ids_list else None

                if 'bar_types' in strategy_param_names:
                    strategy_params_copy['bar_types'] = bar_types_list
                elif 'bar_type' in strategy_param_names:
                    strategy_params_copy['bar_type'] = bar_types_list[0] if bar_types_list else None

                # 移除不相关的参数
                strategy_params_copy = {k: v for k, v in strategy_params_copy.items()
                                       if k in strategy_param_names}

                user_strategy = strategy_class(**strategy_params_copy)

            strategy = user_strategy
            logger.info(
                f"成功加载事件驱动策略: {strategy_class.__name__}"
                f"（支持 {len(instruments)} 个品种）"
            )

            return strategy

        except Exception as e:
            logger.error(f"加载事件驱动策略失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    @staticmethod
    def _get_class_param_names(cls) -> list:
        """获取类的构造函数参数名列表

        优先使用 inspect.signature（能正确解析显式 __init__ 声明的参数），
        其次才回退到 Pydantic/dataclass 的字段声明。
        """
        import inspect

        param_names = []

        try:
            sig = inspect.signature(cls.__init__)
            param_names = [p for p in sig.parameters.keys() if p != 'self']
        except (ValueError, TypeError):
            # 当 __init__ 来自 C 扩展或不可内省时，回退到 Pydantic/dataclass 字段
            pass

        if not param_names:
            if hasattr(cls, 'model_fields'):
                param_names = list(cls.model_fields.keys())
            elif hasattr(cls, '__fields__'):
                param_names = list(cls.__fields__.keys())
            elif hasattr(cls, '__annotations__'):
                param_names = list(cls.__annotations__.keys())

        return param_names