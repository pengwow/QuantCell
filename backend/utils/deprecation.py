"""
弃用警告工具库
==============

提供标准化的弃用警告机制，用于标记兼容性代码。
支持函数、类、属性和模块级的弃用标记。

Usage:
    from utils.deprecation import deprecated, deprecated_property, deprecated_module

    @deprecated("2.0", "3.0", "new_function()")
    def old_function():
        pass

    @deprecated("2.1", "3.0", "NewClass")
    class OldClass:
        pass

    class MyClass:
        @property
        @deprecated_property("2.0", ".new_attr")
        def old_attr(self):
            return self._new_attr

    # 模块级弃用（在模块顶部调用）
    deprecated_module(__name__, "2.0", "new.module.path")
"""

import functools
import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def deprecated(
    version: str,
    remove_version: str | None = None,
    replacement: str | None = None,
    category: type = DeprecationWarning,
    stacklevel: int = 2,
):
    """
    通用的弃用装饰器，适用于函数和类

    Args:
        version: 弃用版本号（如 "2.0"）
        remove_version: 计划移除版本号（如 "3.0"）
        replacement: 替代方案描述
        category: 警告类别（默认 DeprecationWarning）
        stacklevel: 堆栈层级（用于定位警告源）

    Returns:
        装饰器函数

    Example:
        >>> @deprecated("2.1", "3.0", "worker_state_manager.get_status()")
        ... def get_worker_status(self, worker_id):
        ...     return self.worker_state_manager.get_state(worker_id)
    """

    def decorator(func_or_class):
        if isinstance(func_or_class, type):
            return _deprecate_class(
                func_or_class,
                version,
                remove_version,
                replacement,
                category,
                stacklevel,
            )
        else:
            return _deprecate_function(
                func_or_class,
                version,
                remove_version,
                replacement,
                category,
                stacklevel,
            )

    return decorator


def _deprecate_function(
    func: Callable,
    version: str,
    remove_version: str,
    replacement: str,
    category: type,
    stacklevel: int,
) -> Callable:
    """为函数添加弃用包装"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        msg = _build_message(func.__qualname__, version, remove_version, replacement)
        warnings.warn(msg, category, stacklevel=stacklevel)
        _log_deprecation(msg)
        return func(*args, **kwargs)

    wrapper.__doc__ = _update_docstring(func.__doc__, version, remove_version, replacement)
    return wrapper


def _deprecate_class(
    cls: type,
    version: str,
    remove_version: str,
    replacement: str,
    category: type,
    stacklevel: int,
) -> type:
    """为类添加弃用包装"""

    original_init = cls.__init__

    @functools.wraps(original_init)
    def new_init(self, *args, **kwargs):
        msg = _build_message(cls.__qualname__, version, remove_version, replacement)
        warnings.warn(msg, category, stacklevel=stacklevel)
        _log_deprecation(msg)
        original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    cls.__doc__ = _update_docstring(cls.__doc__, version, remove_version, replacement)
    return cls


def deprecated_property(getter_func: Callable, version: str, replacement: str | None = None) -> property:
    """
    创建带弃用警告的属性装饰器

    Args:
        getter_func: 原始的 property getter 函数
        version: 弃用版本号
        replacement: 替代属性名（如 ".new_attr"）

    Returns:
        带 warning 的 property 对象

    Example:
        >>> class WorkerModel:
        ...     @property
        ...     @deprecated_property("2.1", ".trading_config")
        ...     def exchange(self):
        ...         return self.trading_config.exchange
    """

    @property
    @functools.wraps(getter_func)
    def wrapper(self):
        name = getter_func.__name__
        msg = f"{name} 属性已弃用 (v{version})"
        if replacement:
            msg += f"，请使用 {replacement}"
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        _log_deprecation(msg)
        return getter_func(self)

    wrapper.__doc__ = _update_docstring(getter_func.__doc__, version, None, replacement)
    return wrapper


def deprecated_module(module_name: str, version: str, replacement: str):
    """
    发出模块级弃用警告（在模块顶部调用）

    Args:
        module_name: 当前模块名（使用 __name__）
        version: 弃用版本号
        replacement: 替代模块路径或说明

    Example:
        >>> # 在模块文件顶部
        >>> from utils.deprecation import deprecated_module
        >>> deprecated_module(__name__, "2.0", "from exchange import test_exchange_connection")
    """
    msg = f"{module_name} 模块已弃用 (v{version})，请使用 {replacement}"
    warnings.warn(msg, DeprecationWarning, stacklevel=3)
    _log_deprecation(msg)


def deprecated_compat(new_api: str | None = None, version: str = "2.1"):
    """
    兼容性方法专用装饰器：标记为向后兼容接口并发出警告

    与 deprecated() 的区别：
    - 专门用于"兼容旧代码"场景
    - 默认消息格式为"向后兼容接口"
    - 不要求指定移除版本

    Args:
        new_api: 推荐的新 API 路径
        version: 兼容层引入版本

    Example:
        >>> @deprecated_compat(new_api="worker_state_manager.start_worker()")
        ... def start_strategy_worker(self, config):
        ...     # 旧的命令式接口
        ...     pass
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            qualname = func.__qualname__
            msg = f"{qualname} 是向后兼容接口 (v{version})"
            if new_api:
                msg += f"，建议使用 {new_api}"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            _log_deprecation(msg)
            return func(*args, **kwargs)

        wrapper.__doc__ = _update_docstring(func.__doc__, version, None, new_api or "新的事件驱动 API")
        return wrapper

    return decorator


def _build_message(name: str, version: str, remove_version: str, replacement: str) -> str:
    """构建标准化的弃用消息"""
    parts = [f"{name} 已弃用 (v{version})"]
    if remove_version:
        parts.append(f"将在 v{remove_version} 中移除")
    if replacement:
        parts.append(f"请使用 {replacement}")
    return "。".join(parts)


def _update_docstring(doc: str | None, version: str, remove_version: str | None, replacement: str | None) -> str:
    """更新文档字符串，添加标准的弃用标记"""
    if doc is None:
        doc = ""

    deprecation_note = f"\n\n    .. deprecated:: {version}"
    if remove_version:
        deprecation_note += f"\n        将在版本 {remove_version} 中完全移除"
    if replacement:
        deprecation_note += f"\n        请使用 ``{replacement}`` 替代"
    deprecation_note += "\n"

    return doc + deprecation_note


def _log_deprecation(message: str):
    """将弃用信息记录到项目日志系统"""
    try:
        from utils.logger import get_logger

        logger = get_logger(__name__)
        logger.warning(f"[DEPRECATION] {message}")
    except Exception:
        pass
