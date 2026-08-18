"""
策略加载服务模块（基于 axond 体系）

从策略文件加载和实例化事件驱动策略类。
支持 EventDrivenStrategy 类型的策略加载。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-08-14
"""

import importlib
import sys
from pathlib import Path

from utils.logger import LogType, get_logger

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
            bar_types={"BTCUSDT": "1h"},
            instruments={"BTCUSDT": InstrumentId("BTCUSDT", "binance")},
        )
    """

    @staticmethod
    def _get_strategies_dir() -> Path:
        """获取策略目录路径（向后兼容：返回第一个存在的目录）

        优先查找 strategy/example/strategies（示例策略），
        然后查找 strategies（旧版兼容）。

        新代码请使用 _get_strategies_dirs() 获取所有目录列表。
        """
        dirs = StrategyLoaderService._get_strategies_dirs()
        if not dirs:
            msg = "找不到任何策略目录"
            raise StrategyLoadError(msg)
        return dirs[0]

    @staticmethod
    def _get_strategies_dirs() -> list[Path]:
        """返回所有可能的策略目录（按优先级排序）

        这是路径查找的**单一真相源**：
        - list-strategies 用这个扫描所有目录
        - load_strategy 用这个逐个查找策略文件

        优先级顺序：
        1. backend/strategy/templates         （P1-Sprint 2 新位置，8 模板）
        2. backend/strategy/example/strategies（示例策略，axond 风格）
        3. backend/strategies                 （旧版兼容，事件驱动风格）
        """
        backend_path = Path(__file__).resolve().parent.parent
        candidates = [
            backend_path / "strategy" / "templates",
            backend_path / "strategy" / "example" / "strategies",
            backend_path / "strategies",
        ]
        return [d for d in candidates if d.exists()]

    @staticmethod
    def _find_strategy_file(strategy_name: str) -> Path | None:
        """在所有候选目录里查找策略文件

        Args:
            strategy_name: 策略名称（不含 .py 后缀）

        Returns:
            找到的策略文件路径，未找到返回 None
        """
        for d in StrategyLoaderService._get_strategies_dirs():
            f = d / f"{strategy_name}.py"
            if f.exists():
                return f
        return None

    @staticmethod
    def get_all_strategy_files() -> list[Path]:
        """列出所有策略目录中的策略文件

        用于 list-strategies 命令，确保不会漏掉任何目录的策略。

        Returns:
            策略文件路径列表（去重后按文件名排序）
        """
        seen: set[Path] = set()
        result: list[Path] = []
        for d in StrategyLoaderService._get_strategies_dirs():
            for f in sorted(d.glob("*.py")):
                if f.name.startswith("_") or f.stem == "__init__":
                    continue
                if f not in seen:
                    seen.add(f)
                    result.append(f)
        return result

    @staticmethod
    def load_strategy(
        strategy_name: str,
        strategy_params: dict,
        instrument_ids: list | None = None,
        bar_types: list | None = None,
    ):
        """
        加载策略（通用入口）

        Args:
            strategy_name: 策略名称（文件名，不含 .py 后缀）
            strategy_params: 策略参数字典
            instrument_ids: 可选品种 ID 列表（axond.StrategyConfig 必填；
                           不传时使用空列表，CLI 单品种场景会后续传入）
            bar_types: 可选 bar_type 列表（同上）

        Returns:
            策略实例

        Raises:
            StrategyLoadError: 当策略加载失败时
        """
        try:
            strategy_file = StrategyLoaderService._find_strategy_file(strategy_name)
            if strategy_file is None:
                dirs = StrategyLoaderService._get_strategies_dirs()
                msg = f"策略文件不存在: {strategy_name}.py。已搜索: {[str(d) for d in dirs]}"
                raise StrategyLoadError(msg)

            strategies_dir = strategy_file.parent
            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))

            if strategy_name in sys.modules:
                del sys.modules[strategy_name]

            module = importlib.import_module(strategy_name)

            # 查找策略类
            strategy_class = StrategyLoaderService._find_strategy_class(module)

            if strategy_class is None:
                msg = f"在模块 {strategy_name} 中找不到策略类"
                raise StrategyLoadError(msg)

            # 实例化策略
            # instrument_ids/bar_types 传 None 时 _instantiate_strategy 会用空列表
            # （axond.StrategyConfig 的这两个字段是必填但允许空列表；
            #  真实品种信息在 default 引擎走 data_dict，event 引擎走 load_event_strategy_multi）
            instance = StrategyLoaderService._instantiate_strategy(
                strategy_class,
                strategy_params,
                instrument_ids,
                bar_types,
                config_class=StrategyLoaderService._find_strategy_config_class(module, strategy_class),
            )

            logger.info(f"成功加载策略: {strategy_class.__name__} (from {strategy_file})")
            return instance

        except StrategyLoadError:
            raise
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            msg = f"加载策略失败: {e}"
            raise StrategyLoadError(msg) from e

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
            bar_types: 品种到BarType的映射字典
            instruments: 品种到Instrument的映射字典

        Returns:
            EventDrivenStrategy: 策略实例或None
        """
        try:
            backend_path = Path(__file__).resolve().parent.parent
            strategies_dir = backend_path / "strategies"

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
                    EventDrivenStrategyConfig,
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

                if "instrument_ids" in config_param_names:
                    config_params["instrument_ids"] = instrument_ids_list
                elif "instrument_id" in config_param_names:
                    config_params["instrument_id"] = instrument_ids_list[0] if instrument_ids_list else None

                if "bar_types" in config_param_names:
                    config_params["bar_types"] = bar_types_list
                elif "bar_type" in config_param_names:
                    config_params["bar_type"] = bar_types_list[0] if bar_types_list else None

                # 移除不相关的参数
                config_params = {k: v for k, v in config_params.items() if k in config_param_names}

                config = config_class(**config_params)
                user_strategy = strategy_class(config)
            else:
                strategy_params_copy = strategy_params.copy()

                strategy_param_names = StrategyLoaderService._get_class_param_names(strategy_class)

                if "instrument_ids" in strategy_param_names:
                    strategy_params_copy["instrument_ids"] = instrument_ids_list
                elif "instrument_id" in strategy_param_names:
                    strategy_params_copy["instrument_id"] = instrument_ids_list[0] if instrument_ids_list else None

                if "bar_types" in strategy_param_names:
                    strategy_params_copy["bar_types"] = bar_types_list
                elif "bar_type" in strategy_param_names:
                    strategy_params_copy["bar_type"] = bar_types_list[0] if bar_types_list else None

                # 移除不相关的参数
                strategy_params_copy = {k: v for k, v in strategy_params_copy.items() if k in strategy_param_names}

                user_strategy = strategy_class(**strategy_params_copy)

            strategy = user_strategy
            logger.info(f"成功加载事件驱动策略: {strategy_class.__name__}（支持 {len(instruments)} 个品种）")

            return strategy

        except Exception as e:
            logger.error(f"加载多品种事件驱动策略失败: {e}")
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
            param_names = [p for p in sig.parameters if p != "self"]
        except ValueError, TypeError:
            # 当 __init__ 来自 C 扩展或不可内省时，回退到 Pydantic/dataclass 字段
            pass

        if not param_names:
            if hasattr(cls, "model_fields"):
                param_names = list(cls.model_fields.keys())
            elif hasattr(cls, "__fields__"):
                param_names = list(cls.__fields__.keys())
            elif hasattr(cls, "__annotations__"):
                param_names = list(cls.__annotations__.keys())

        return param_names
