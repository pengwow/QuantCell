"""策略加载器 — 按 name → class 全局注册表。

ponytail: @register(name) 装饰器,模板 import 时自动注册
         加载器: StrategyLoader.get(name) -> class
         列出: StrategyLoader.list_all() -> [name, ...]
"""
from __future__ import annotations

import importlib
import pkgutil

from strategy.base import BaseStrategy


_REGISTRY: dict[str, type[BaseStrategy]] = {}


def register(name: str):
    """装饰器：注册策略到全局表。"""
    def deco(cls: type[BaseStrategy]) -> type[BaseStrategy]:
        if name in _REGISTRY:
            raise ValueError(f"策略名重复: {name}")
        _REGISTRY[name] = cls
        cls._registered_name = name  # type: ignore[attr-defined]
        return cls
    return deco


class StrategyLoader:
    @staticmethod
    def get(name: str) -> type[BaseStrategy]:
        if name not in _REGISTRY:
            raise ValueError(f"未知策略: {name}，可用: {list(_REGISTRY.keys())}")
        return _REGISTRY[name]

    @staticmethod
    def list_all() -> list[str]:
        return sorted(_REGISTRY.keys())

    @staticmethod
    def has(name: str) -> bool:
        return name in _REGISTRY


# 自动导入 strategy.templates 触发 @register 装饰器
def _auto_register():
    import strategy.templates  # noqa: F401
    for _, mod_name, _ in pkgutil.iter_modules(strategy.templates.__path__):
        importlib.import_module(f"strategy.templates.{mod_name}")


_auto_register()
