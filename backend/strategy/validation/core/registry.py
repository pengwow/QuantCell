"""
验证器注册表
管理所有可用的验证器
"""

from typing import Dict, List, Optional, Type, Callable
from loguru import logger

from .base import BaseValidator
from .exceptions import ValidatorNotFoundError


class ValidatorRegistry:
    """
    验证器注册表

    单例模式管理所有验证器的注册和获取
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._validators: Dict[str, Type[BaseValidator]] = {}
            cls._instance._factories: Dict[str, Callable] = {}
        return cls._instance

    def register(
        self,
        name: str,
        validator_class: Type[BaseValidator],
        factory: Optional[Callable] = None,
    ) -> None:
        """
        注册验证器

        Args:
            name: 验证器名称
            validator_class: 验证器类
            factory: 可选的工厂函数
        """
        self._validators[name] = validator_class
        if factory:
            self._factories[name] = factory

    def unregister(self, name: str) -> bool:
        """
        注销验证器

        Args:
            name: 验证器名称

        Returns:
            bool: 是否成功注销
        """
        if name in self._validators:
            del self._validators[name]
            if name in self._factories:
                del self._factories[name]
            logger.debug(f"验证器已注销: {name}")
            return True
        return False

    def get(self, name: str, *args, **kwargs) -> BaseValidator:
        """
        获取验证器实例

        Args:
            name: 验证器名称
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            BaseValidator: 验证器实例

        Raises:
            ValidatorNotFoundError: 验证器未找到
        """
        if name not in self._validators:
            raise ValidatorNotFoundError(f"验证器未找到: {name}")

        # 如果有工厂函数，使用工厂函数创建
        if name in self._factories:
            return self._factories[name](*args, **kwargs)

        # 否则直接实例化
        return self._validators[name](*args, **kwargs)

    def list_validators(self) -> List[str]:
        """
        获取所有已注册的验证器名称

        Returns:
            List[str]: 验证器名称列表
        """
        return list(self._validators.keys())

    def get_validator_info(self, name: str) -> Optional[Dict]:
        """
        获取验证器信息

        Args:
            name: 验证器名称

        Returns:
            Optional[Dict]: 验证器信息
        """
        if name not in self._validators:
            return None

        validator_class = self._validators[name]
        return {
            "name": getattr(validator_class, "name", name),
            "description": getattr(validator_class, "description", ""),
            "default_threshold": getattr(validator_class, "default_threshold", 0.01),
            "has_factory": name in self._factories,
        }

    def clear(self) -> None:
        """
        清空所有注册的验证器
        """
        self._validators.clear()
        self._factories.clear()
        logger.debug("验证器注册表已清空")

    def create_suite(self, names: List[str], suite_name: str = "CustomSuite"):
        """
        从注册的验证器创建验证套件

        Args:
            names: 验证器名称列表
            suite_name: 套件名称

        Returns:
            ValidationSuite: 验证套件
        """
        from .base import ValidationSuite

        suite = ValidationSuite(name=suite_name)
        for name in names:
            validator = self.get(name)
            suite.add_validator(validator)
        return suite


# 全局注册表实例
registry = ValidatorRegistry()


def register_validator(name: str, factory: Optional[Callable] = None):
    """
    装饰器：注册验证器

    Args:
        name: 验证器名称
        factory: 可选的工厂函数

    Returns:
        Callable: 装饰器函数
    """

    def decorator(validator_class: Type[BaseValidator]):
        registry.register(name, validator_class, factory)
        return validator_class

    return decorator


def get_validator(name: str, *args, **kwargs) -> BaseValidator:
    """
    便捷函数：获取验证器实例

    Args:
        name: 验证器名称
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        BaseValidator: 验证器实例
    """
    return registry.get(name, *args, **kwargs)
