# -*- coding: utf-8 -*-
"""
策略适配器模块

提供策略适配功能，支持：
- 包装 legacy 策略（基于 StrategyBase）
- 加载原生交易引擎策略
- 策略参数转换
- 策略验证
"""

import importlib
import inspect
import sys
from abc import ABC
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, Union

from loguru import logger

# 交易引擎导入
from nautilus_trader.trading.strategy import Strategy, StrategyConfig
from nautilus_trader.config import ImportableStrategyConfig

# QuantCell 内部导入
from strategy.core.strategy_base import StrategyBase


class StrategyAdapterError(Exception):
    """策略适配器异常基类"""
    pass


class LegacyStrategyWrapperError(StrategyAdapterError):
    """Legacy 策略包装异常"""
    pass


class StrategyLoadError(StrategyAdapterError):
    """高级策略加载异常"""
    pass


class StrategyValidationError(StrategyAdapterError):
    """策略验证异常"""
    pass


class ParameterConversionError(StrategyAdapterError):
    """参数转换异常"""
    pass


# 交易引擎策略必需的方法列表
ADVANCED_REQUIRED_METHODS = [
    "on_start",
    "on_stop",
]

# 交易引擎策略可选的数据处理方法
ADVANCED_DATA_METHODS = [
    "on_quote_tick",
    "on_trade_tick",
    "on_bar",
    "on_data",
]


def adapt_legacy_strategy(legacy_strategy_class: Type[StrategyBase]) -> Type[Strategy]:
    """
    包装 legacy 策略（基于 StrategyBase）为交易引擎 Strategy

    参数：
        legacy_strategy_class: 继承自 StrategyBase 的 legacy 策略类

    返回：
        Type[Strategy]: 包装后的交易引擎 Strategy 类

    异常：
        LegacyStrategyWrapperError: 如果包装失败
    """
    # 验证输入类是否继承自 StrategyBase
    if not issubclass(legacy_strategy_class, StrategyBase):
        raise LegacyStrategyWrapperError(
            f"策略类 {legacy_strategy_class.__name__} 必须继承自 StrategyBase"
        )

    class LegacyStrategyAdapter(Strategy):
        """
        Legacy 策略适配器类

        将基于 StrategyBase 的 legacy 策略包装为交易引擎 Strategy
        """

        def __init__(self, config: StrategyConfig):
            """
            初始化适配器

            参数：
                config: 交易引擎策略配置
            """
            super().__init__(config)

            # 提取 legacy 策略参数
            legacy_params = getattr(config, "legacy_params", {})
            if not legacy_params:
                # 从 config 的其他属性中提取参数
                legacy_params = {
                    k: v for k, v in vars(config).items()
                    if not k.startswith("_") and k not in ["strategy_id", "order_id_tag", "oms_type"]
                }

            # 创建 legacy 策略实例
            self._legacy_strategy = legacy_strategy_class(legacy_params)

            # 初始化状态
            self._bars_cache: List[Dict[str, Any]] = []
            self._current_bar: Optional[Dict[str, Any]] = None

            logger.info(f"Legacy 策略适配器已初始化: {legacy_strategy_class.__name__}")

        def on_start(self):
            """策略启动回调"""
            logger.info(f"Legacy 策略启动: {legacy_strategy_class.__name__}")

            # 调用 legacy 策略的 on_init
            if hasattr(self._legacy_strategy, "on_init"):
                self._legacy_strategy.on_init()

        def on_stop(self):
            """策略停止回调"""
            logger.info(f"Legacy 策略停止: {legacy_strategy_class.__name__}")

            # 调用 legacy 策略的 on_stop
            if self._current_bar and hasattr(self._legacy_strategy, "on_stop"):
                self._legacy_strategy.on_stop(self._current_bar)

        def on_bar(self, bar):
            """
            K线数据回调

            参数：
                bar: 交易引擎 Bar 对象
            """
            # 转换为 legacy 策略期望的字典格式
            bar_dict = self._convert_bar_to_dict(bar)
            self._current_bar = bar_dict
            self._bars_cache.append(bar_dict)

            # 调用 legacy 策略的 on_bar
            if hasattr(self._legacy_strategy, "on_bar"):
                self._legacy_strategy.on_bar(bar_dict)

        def on_quote_tick(self, tick):
            """
            Quote Tick 数据回调

            参数：
                tick: 交易引擎 QuoteTick 对象
            """
            # 转换为 legacy 策略期望的字典格式
            tick_dict = self._convert_quote_tick_to_dict(tick)

            # 调用 legacy 策略的 on_tick
            if hasattr(self._legacy_strategy, "on_tick"):
                self._legacy_strategy.on_tick(tick_dict)

        def _convert_bar_to_dict(self, bar) -> Dict[str, Any]:
            """
            将交易引擎 Bar 对象转换为字典

            参数：
                bar: 交易引擎 Bar 对象

            返回：
                Dict[str, Any]: K线数据字典
            """
            return {
                "timestamp": bar.ts_event,
                "Open": float(bar.open),
                "High": float(bar.high),
                "Low": float(bar.low),
                "Close": float(bar.close),
                "Volume": float(bar.volume) if hasattr(bar, "volume") else 0.0,
                "symbol": str(bar.bar_type.instrument_id) if hasattr(bar, "bar_type") else "",
                "timeframe": str(bar.bar_type.spec) if hasattr(bar, "bar_type") else "",
            }

        def _convert_quote_tick_to_dict(self, tick) -> Dict[str, Any]:
            """
            将交易引擎 QuoteTick 对象转换为字典

            参数：
                tick: 交易引擎 QuoteTick 对象

            返回：
                Dict[str, Any]: Tick 数据字典
            """
            return {
                "timestamp": tick.ts_event,
                "symbol": str(tick.instrument_id),
                "bid_price": float(tick.bid_price),
                "ask_price": float(tick.ask_price),
                "bid_size": float(tick.bid_size),
                "ask_size": float(tick.ask_size),
            }

        # 暴露 legacy 策略的公共方法
        def buy(self, symbol: str, price: float, volume: float) -> str:
            """买入"""
            return self._legacy_strategy.buy(symbol, price, volume)

        def sell(self, symbol: str, price: float, volume: float) -> str:
            """卖出"""
            return self._legacy_strategy.sell(symbol, price, volume)

        def long(self, symbol: str, price: float, volume: float) -> str:
            """开多"""
            return self._legacy_strategy.long(symbol, price, volume)

        def short(self, symbol: str, price: float, volume: float) -> str:
            """开空"""
            return self._legacy_strategy.short(symbol, price, volume)

        def get_position(self, symbol: str) -> Dict[str, Any]:
            """获取持仓"""
            return self._legacy_strategy.get_position(symbol)

        @property
        def legacy_strategy(self) -> StrategyBase:
            """获取底层 legacy 策略实例"""
            return self._legacy_strategy

    # 设置适配器类的名称
    LegacyStrategyAdapter.__name__ = f"{legacy_strategy_class.__name__}Adapter"
    LegacyStrategyAdapter.__qualname__ = f"{legacy_strategy_class.__qualname__}Adapter"

    logger.info(f"Legacy 策略包装完成: {legacy_strategy_class.__name__} -> {LegacyStrategyAdapter.__name__}")

    return LegacyStrategyAdapter


def load_advanced_strategy(
    strategy_path: Union[str, Path],
    strategy_name: Optional[str] = None
) -> Type[Strategy]:
    """
    加载原生交易引擎策略

    参数：
        strategy_path: 策略文件路径或模块路径
        strategy_name: 策略类名称（可选，如果为 None 则自动查找）

    返回：
        Type[Strategy]: 交易引擎 Strategy 类

    异常：
        StrategyLoadError: 如果加载失败
    """
    strategy_path = Path(strategy_path)

    # 检查文件是否存在
    if not strategy_path.exists():
        raise StrategyLoadError(f"策略文件不存在: {strategy_path}")

    # 添加策略目录到 Python 路径
    strategy_dir = strategy_path.parent
    if str(strategy_dir) not in sys.path:
        sys.path.insert(0, str(strategy_dir))

    # 获取模块名称
    module_name = strategy_path.stem

    try:
        # 清除模块缓存（如果存在）
        if module_name in sys.modules:
            del sys.modules[module_name]

        # 导入策略模块
        module = importlib.import_module(module_name)

        # 查找策略类
        if strategy_name:
            # 使用指定的策略类名称
            if not hasattr(module, strategy_name):
                raise StrategyLoadError(
                    f"模块 {module_name} 中不存在策略类: {strategy_name}"
                )
            strategy_class = getattr(module, strategy_name)
        else:
            # 自动查找继承自 Strategy 的类
            strategy_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Strategy)
                    and obj is not Strategy
                ):
                    strategy_class = obj
                    strategy_name = name
                    logger.info(f"找到交易引擎策略类: {name}")
                    break

        if strategy_class is None:
            raise StrategyLoadError(
                f"在模块 {module_name} 中找不到交易引擎策略类"
            )

        # 验证策略类
        validate_advanced_strategy(strategy_class)

        logger.info(f"成功加载交易引擎策略: {strategy_class.__name__}")

        return strategy_class

    except Exception as e:
        raise StrategyLoadError(f"加载交易引擎策略失败: {e}")


def convert_params_to_advanced_config(
    params: Dict[str, Any],
    strategy_class: Optional[Type[Strategy]] = None,
    config_class: Optional[Type[StrategyConfig]] = None
) -> StrategyConfig:
    """
    将内部参数格式转换为交易引擎 StrategyConfig

    参数：
        params: 内部参数字典
        strategy_class: 交易引擎策略类（用于推断配置类）
        config_class: 指定的配置类（优先使用）

    返回：
        StrategyConfig: 交易引擎策略配置

    异常：
        ParameterConversionError: 如果转换失败
    """
    # 确定配置类
    if config_class is None and strategy_class is not None:
        # 从策略类获取默认配置类
        config_class = getattr(strategy_class, "default_config", None)
        if config_class is None:
            # 尝试查找策略模块中的配置类
            module = inspect.getmodule(strategy_class)
            if module:
                for name in dir(module):
                    obj = getattr(module, name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, StrategyConfig)
                        and obj is not StrategyConfig
                    ):
                        config_class = obj
                        break

    # 如果没有找到配置类，使用通用的 StrategyConfig
    if config_class is None:
        config_class = StrategyConfig

    try:
        # 过滤掉 None 值和内部参数
        filtered_params = {
            k: v for k, v in params.items()
            if v is not None and not k.startswith("_")
        }

        # 处理特殊参数名称映射
        param_mapping = {
            "strategy_id": "strategy_id",
            "order_id_tag": "order_id_tag",
            "oms_type": "oms_type",
        }

        # 构建配置参数
        config_params = {}
        for key, value in filtered_params.items():
            mapped_key = param_mapping.get(key, key)
            config_params[mapped_key] = value

        # 创建配置实例
        config = config_class(**config_params)

        logger.info(f"参数转换完成: {len(config_params)} 个参数")

        return config

    except Exception as e:
        raise ParameterConversionError(f"参数转换失败: {e}")


def create_importable_strategy_config(
    strategy_path: Union[str, Path],
    strategy_name: str,
    params: Dict[str, Any]
) -> ImportableStrategyConfig:
    """
    创建 ImportableStrategyConfig 用于动态加载策略

    参数：
        strategy_path: 策略文件路径
        strategy_name: 策略类名称
        params: 策略参数字典

    返回：
        ImportableStrategyConfig: 可导入的策略配置
    """
    strategy_path = Path(strategy_path)

    # 构建模块路径
    module_path = f"{strategy_path.parent.name}.{strategy_path.stem}"

    # 过滤参数
    filtered_params = {
        k: v for k, v in params.items()
        if v is not None and not k.startswith("_")
    }

    config = ImportableStrategyConfig(
        strategy_path=module_path,
        strategy_name=strategy_name,
        config_path="",  # 使用内联配置
        config=filtered_params,
    )

    logger.info(f"创建 ImportableStrategyConfig: {module_path}.{strategy_name}")

    return config


def validate_advanced_strategy(strategy_class: Type[Strategy]) -> bool:
    """
    验证策略是否继承自交易引擎的 Strategy 类

    参数：
        strategy_class: 要验证的策略类

    返回：
        bool: 验证是否通过

    异常：
        StrategyValidationError: 如果验证失败
    """
    # 检查是否继承自 Strategy
    if not issubclass(strategy_class, Strategy):
        raise StrategyValidationError(
            f"策略类 {strategy_class.__name__} 必须继承自交易引擎的 Strategy 类"
        )

    # 检查必需方法
    missing_methods = []
    for method_name in ADVANCED_REQUIRED_METHODS:
        if not hasattr(strategy_class, method_name):
            missing_methods.append(method_name)

    if missing_methods:
        raise StrategyValidationError(
            f"策略类 {strategy_class.__name__} 缺少必需方法: {', '.join(missing_methods)}"
        )

    # 检查至少有一个数据处理方法
    has_data_method = any(
        hasattr(strategy_class, method_name)
        for method_name in ADVANCED_DATA_METHODS
    )

    if not has_data_method:
        logger.warning(
            f"策略类 {strategy_class.__name__} 没有实现任何数据处理方法 "
            f"({', '.join(ADVANCED_DATA_METHODS)})"
        )

    logger.info(f"策略验证通过: {strategy_class.__name__}")

    return True


def validate_legacy_strategy(strategy_class: Type[StrategyBase]) -> bool:
    """
    验证策略是否继承自 StrategyBase

    参数：
        strategy_class: 要验证的策略类

    返回：
        bool: 验证是否通过

    异常：
        StrategyValidationError: 如果验证失败
    """
    # 检查是否继承自 StrategyBase
    if not issubclass(strategy_class, StrategyBase):
        raise StrategyValidationError(
            f"策略类 {strategy_class.__name__} 必须继承自 StrategyBase"
        )

    # 检查必需方法
    required_methods = ["on_init", "on_bar"]
    missing_methods = []

    for method_name in required_methods:
        if not hasattr(strategy_class, method_name):
            missing_methods.append(method_name)

    if missing_methods:
        raise StrategyValidationError(
            f"策略类 {strategy_class.__name__} 缺少必需方法: {', '.join(missing_methods)}"
        )

    logger.info(f"Legacy 策略验证通过: {strategy_class.__name__}")

    return True


def detect_strategy_type(strategy_class: Type) -> str:
    """
    检测策略类型

    参数：
        strategy_class: 策略类

    返回：
        str: 策略类型 ('default', 'legacy', 'unknown')
    """
    if issubclass(strategy_class, Strategy):
        return "default"
    elif issubclass(strategy_class, StrategyBase):
        return "legacy"
    else:
        return "unknown"


def auto_adapt_strategy(
    strategy_class: Type,
    params: Optional[Dict[str, Any]] = None
) -> Union[Type[Strategy], Strategy]:
    """
    自动适配策略

    根据策略类型自动选择适配方式：
    - 交易引擎 Strategy: 直接返回
    - Legacy StrategyBase: 包装为交易引擎 Strategy

    参数：
        strategy_class: 策略类
        params: 策略参数（可选）

    返回：
        Union[Type[Strategy], Strategy]: 适配后的策略类或实例
    """
    strategy_type = detect_strategy_type(strategy_class)

    if strategy_type == "default":
        logger.info(f"检测到交易引擎策略: {strategy_class.__name__}")
        return strategy_class
    elif strategy_type == "legacy":
        logger.info(f"检测到 Legacy 策略: {strategy_class.__name__}")
        return adapt_legacy_strategy(strategy_class)
    else:
        raise StrategyAdapterError(
            f"无法识别的策略类型: {strategy_class.__name__}"
        )


# 便捷函数
load_strategy = load_advanced_strategy
wrap_legacy_strategy = adapt_legacy_strategy
