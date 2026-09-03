"""策略适配器模块

提供策略适配功能，支持：
- 加载 axon_quant 策略（实现 on_bar → Action）
- 策略参数转换
- 策略验证
"""

import importlib
from pathlib import Path

from utils.logger import LogType, get_logger

logger = get_logger(__name__, LogType.APPLICATION)

from backtest.backtest_loop import RuleStrategy


class StrategyAdapterError(Exception):
    """策略适配器异常基类"""

    pass


class StrategyLoadError(StrategyAdapterError):
    """策略加载异常"""

    pass


class StrategyConfigError(StrategyAdapterError):
    """策略配置异常"""

    pass


def load_strategy_from_file(
    file_path: str,
    strategy_name: str | None = None,
) -> type:
    """从文件加载策略类

    Args:
        file_path: 策略文件路径
        strategy_name: 策略类名（可选，自动检测）

    Returns:
        策略类

    Raises:
        StrategyLoadError: 加载失败
    """
    path = Path(file_path)
    if not path.exists():
        msg = f"策略文件不存在: {file_path}"
        raise StrategyLoadError(msg)

    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        msg = f"无法加载策略模块: {file_path}"
        raise StrategyLoadError(msg)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return _find_strategy_class(module, strategy_name)


def load_strategy_from_code(
    code: str,
    strategy_name: str | None = None,
) -> type:
    """从代码字符串加载策略类

    Args:
        code: 策略代码
        strategy_name: 策略类名（可选）

    Returns:
        策略类
    """
    module_name = "dynamic_strategy"
    import types

    module = types.ModuleType(module_name)
    exec(compile(code, "<string>", "exec"), module.__dict__)

    return _find_strategy_class(module, strategy_name)


def _find_strategy_class(module, strategy_name: str | None = None) -> type:
    """从模块中查找策略类"""
    if strategy_name:
        if hasattr(module, strategy_name):
            cls = getattr(module, strategy_name)
            if isinstance(cls, type) and hasattr(cls, "on_bar"):
                return cls
        msg = f"未找到策略类: {strategy_name}"
        raise StrategyLoadError(msg)

    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and hasattr(obj, "on_bar") and not name.startswith("_") and obj is not RuleStrategy:
            return obj

    msg = "未找到策略类（需要实现 on_bar 方法）"
    raise StrategyLoadError(msg)


def validate_strategy(strategy_class: type) -> bool:
    """验证策略类是否有效"""
    if not isinstance(strategy_class, type):
        return False
    return hasattr(strategy_class, "on_bar") and callable(getattr(strategy_class, "on_bar", None))
