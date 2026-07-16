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
        """获取策略基类（统一用 on_bar 方法检测）"""
        return None

    @classmethod
    def _get_axon_strategy_config(cls) -> Type:
        """获取策略配置基类（不再需要）"""
        return None

    @classmethod
    def _get_event_strategy_base(cls) -> Type:
        """获取策略基类（不再需要）"""
        return None

    @staticmethod
    def _get_strategies_dir() -> Path:
        """获取策略目录路径（向后兼容：返回第一个存在的目录）

        优先查找 strategy/example/strategies（示例策略），
        然后查找 strategies（旧版兼容）。

        新代码请使用 _get_strategies_dirs() 获取所有目录列表。
        """
        dirs = StrategyLoaderService._get_strategies_dirs()
        if not dirs:
            raise StrategyLoadError("找不到任何策略目录")
        return dirs[0]

    @staticmethod
    def _get_strategies_dirs() -> list[Path]:
        """返回所有可能的策略目录（按优先级排序）

        这是路径查找的**单一真相源**：
        - list-strategies 用这个扫描所有目录
        - load_strategy 用这个逐个查找策略文件

        优先级顺序：
        1. backend/strategy/example/strategies  （示例策略，axond 风格）
        2. backend/strategies                  （旧版兼容，事件驱动风格）
        """
        backend_path = Path(__file__).resolve().parent.parent
        candidates = [
            backend_path / "strategy" / "example" / "strategies",
            backend_path / "strategies",
        ]
        return [d for d in candidates if d.exists()]

    @staticmethod
    def _find_strategy_file(strategy_name: str) -> Optional[Path]:
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
                if f.name.startswith("_") or f.stem in ("__init__",):
                    continue
                if f not in seen:
                    seen.add(f)
                    result.append(f)
        return result

    @staticmethod
    def load_strategy(
        strategy_name: str,
        strategy_params: dict,
        instrument_ids: Optional[list] = None,
        bar_types: Optional[list] = None,
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
                raise StrategyLoadError(
                    f"策略文件不存在: {strategy_name}.py。已搜索: {[str(d) for d in dirs]}"
                )

            strategies_dir = strategy_file.parent
            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))

            if strategy_name in sys.modules:
                del sys.modules[strategy_name]

            module = importlib.import_module(strategy_name)

            # 查找策略类
            strategy_class = StrategyLoaderService._find_strategy_class(module)

            if strategy_class is None:
                raise StrategyLoadError(
                    f"在模块 {strategy_name} 中找不到策略类"
                )

            # 实例化策略
            # instrument_ids/bar_types 传 None 时 _instantiate_strategy 会用空列表
            # （axond.StrategyConfig 的这两个字段是必填但允许空列表；
            #  真实品种信息在 default 引擎走 data_dict，event 引擎走 load_event_strategy_multi）
            instance = StrategyLoaderService._instantiate_strategy(
                strategy_class, strategy_params, instrument_ids, bar_types,
                config_class=StrategyLoaderService._find_strategy_config_class(module, strategy_class),
            )

            logger.info(
                f"成功加载策略: {strategy_class.__name__} (from {strategy_file})"
            )
            return instance

        except StrategyLoadError:
            raise
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
            strategy_file = StrategyLoaderService._find_strategy_file(strategy_name)
            if strategy_file is None:
                logger.info(
                    f"策略文件不存在: {strategy_name}.py"
                )
                return None

            strategies_dir = strategy_file.parent
            if str(strategies_dir) not in sys.path:
                sys.path.insert(0, str(strategies_dir))

            if strategy_name in sys.modules:
                del sys.modules[strategy_name]

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
                f"（支持 {len(instruments)} 个品种, from {strategy_file})"
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

        found_class: Optional[Type] = None

        for name in dir(module):
            obj = getattr(module, name)
            if not isinstance(obj, type):
                continue
            if name.startswith("_"):
                continue

            # 检查是否有 on_bar 方法（axon_quant 策略统一接口）
            if hasattr(obj, "on_bar") and callable(getattr(obj, "on_bar", None)):
                found_class = obj
                logger.info(f"找到策略类: {name}")
                break

        return found_class

    @staticmethod
    def _find_strategy_config_class(module, strategy_class: Type) -> Type:
        """查找策略对应的 Config 类（向后兼容）

        Args:
            module: 策略模块
            strategy_class: 策略类

        Returns:
            Config 类或 None
        """
        strategy_name = strategy_class.__name__
        candidate_name = strategy_name + "Config"

        if hasattr(module, candidate_name):
            candidate = getattr(module, candidate_name)
            if isinstance(candidate, type):
                return candidate

        return None
        candidate = getattr(module, candidate_name, None)
        if (
            candidate is not None
            and isinstance(candidate, type)
            and issubclass(candidate, axon_config_base)
            and candidate is not axon_config_base
        ):
            logger.debug(f"找到策略 Config 类: {candidate_name}")
            return candidate

        # 2. 模糊匹配：模块内任何以 Config 结尾的 axond.StrategyConfig 子类
        for name in dir(module):
            obj = getattr(module, name)
            if (
                isinstance(obj, type)
                and obj is not axon_config_base
                and issubclass(obj, axon_config_base)
                and name.endswith("Config")
                and not name.startswith("_")
            ):
                logger.debug(f"模糊匹配到 Config 类: {name}")
                return obj

        # 3. 回退：基类
        logger.debug(f"未找到 {strategy_name} 的 Config 子类，使用基类")
        return axon_config_base

    @staticmethod
    def _instantiate_strategy(
        strategy_class: Type,
        strategy_params: dict,
        instrument_ids_list: Optional[list],
        bar_types_list: Optional[list],
        config_class: Optional[Type] = None,
    ):
        """实例化策略类

        根据策略类的构造函数签名决定如何传递参数：
        1. 接受 config 参数：创建配置对象后传入
        2. 直接接受参数：直接传入

        Args:
            strategy_class: 策略类
            strategy_params: 策略参数
            instrument_ids_list: 品种 ID 列表（axond.StrategyConfig 必填且非空，
                                None 时会抛错告知调用方传入）
            bar_types_list: bar_type 列表（同上）
            config_class: 可选，策略专属的 Config 子类（来自 _find_strategy_config_class）；
                         None 时回退到 axond.StrategyConfig 基类

        Returns:
            策略实例

        Raises:
            StrategyLoadError: 必填参数缺失时
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
            # 使用传入的 config_class；缺省回退到 axond.StrategyConfig 基类
            if config_class is None:
                config_class = StrategyLoaderService._get_axon_strategy_config()

            config_params = dict(strategy_params)

            # 添加品种和 bar_type
            # axond.StrategyConfig 必填且非空；调用方应该传入
            if instrument_ids_list is None or bar_types_list is None:
                raise StrategyLoadError(
                    f"策略 {strategy_class.__name__} 是 axond 风格，"
                    f"需要传入 instrument_ids 和 bar_types。"
                    f"请使用 load_strategy(name, params, instrument_ids, bar_types) "
                    f"或 load_event_strategy_multi(...) 加载。"
                )
            if not instrument_ids_list or not bar_types_list:
                raise StrategyLoadError(
                    f"策略 {strategy_class.__name__} 要求 instrument_ids 和 bar_types 非空。"
                )
            config_params["instrument_ids"] = instrument_ids_list
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
            # 直接传递参数（只传策略接受的参数）
            params = dict(strategy_params)
            # 过滤：只传策略构造函数实际接受的参数
            valid_params = {k for k in param_names if k != "self"}
            filtered = {k: v for k, v in params.items() if k in valid_params}
            return strategy_class(**filtered)
