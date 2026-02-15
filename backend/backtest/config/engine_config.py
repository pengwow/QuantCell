"""
回测引擎配置加载逻辑

提供引擎配置的加载和管理功能。

包含:
    - get_engine_config: 获取引擎配置
    - load_engine_config: 从字典加载引擎配置
    - merge_config: 合并配置

作者: QuantCell Team
版本: 1.0.0
日期: 2026-02-15
"""

from typing import Any, Dict, Optional

from .settings import DEFAULT_ENGINE, EngineType, DEFAULT_CONFIG


def get_engine_config(
    engine_type: Optional[EngineType] = None,
    custom_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    获取引擎配置

    根据引擎类型返回对应的配置，支持自定义配置覆盖默认配置。

    Args:
        engine_type: 引擎类型，默认为 DEFAULT_ENGINE
        custom_config: 自定义配置，用于覆盖默认配置

    Returns:
        引擎配置字典

    Example:
        >>> config = get_engine_config(EngineType.DEFAULT, {"log_level": "DEBUG"})
        >>> print(config["log_level"])
        DEBUG
    """
    engine_type = engine_type or DEFAULT_ENGINE

    # 根据引擎类型选择基础配置
    if engine_type == EngineType.DEFAULT:
        base_config = DEFAULT_CONFIG.copy()
    elif engine_type == EngineType.LEGACY:
        # 传统引擎配置
        base_config = {
            "log_level": "INFO",
        }
    else:
        base_config = {}

    # 合并自定义配置
    if custom_config:
        base_config = merge_config(base_config, custom_config)

    return base_config


def load_engine_config(
    config_dict: Dict[str, Any],
    engine_type_key: str = "engine_type",
) -> Dict[str, Any]:
    """
    从字典加载引擎配置

    从配置字典中解析引擎类型并返回对应的完整配置。

    Args:
        config_dict: 包含引擎配置的字典
        engine_type_key: 引擎类型键名

    Returns:
        完整的引擎配置字典

    Raises:
        ValueError: 当引擎类型无效时

    Example:
        >>> config = load_engine_config({"engine_type": "default", "log_level": "DEBUG"})
        >>> print(config["log_level"])
        DEBUG
    """
    # 解析引擎类型
    engine_type_str = config_dict.get(engine_type_key, DEFAULT_ENGINE.value)
    try:
        engine_type = EngineType(engine_type_str)
    except ValueError as e:
        valid_types = [et.value for et in EngineType]
        raise ValueError(
            f"无效的引擎类型: {engine_type_str}. "
            f"有效的类型: {valid_types}"
        ) from e

    # 移除引擎类型键，剩余作为自定义配置
    custom_config = {
        k: v for k, v in config_dict.items() if k != engine_type_key
    }

    return get_engine_config(engine_type, custom_config)


def merge_config(
    base_config: Dict[str, Any],
    override_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    合并配置字典

    将覆盖配置合并到基础配置中，支持嵌套字典的递归合并。

    Args:
        base_config: 基础配置
        override_config: 覆盖配置

    Returns:
        合并后的配置字典

    Example:
        >>> base = {"cache": {"enabled": True, "size_mb": 512}}
        >>> override = {"cache": {"size_mb": 1024}}
        >>> result = merge_config(base, override)
        >>> print(result["cache"]["size_mb"])
        1024
        >>> print(result["cache"]["enabled"])
        True
    """
    result = base_config.copy()

    for key, value in override_config.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            # 递归合并嵌套字典
            result[key] = merge_config(result[key], value)
        else:
            # 直接覆盖或添加新值
            result[key] = value

    return result
