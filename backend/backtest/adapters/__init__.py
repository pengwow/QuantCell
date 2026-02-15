# -*- coding: utf-8 -*-
"""
Backtest 适配器模块

提供策略适配、数据转换等功能
"""

from .strategy_adapter import (
    # 主要函数
    adapt_legacy_strategy,
    load_advanced_strategy,
    auto_adapt_strategy,
    
    # 参数转换
    convert_params_to_advanced_config,
    create_importable_strategy_config,
    
    # 验证函数
    validate_advanced_strategy,
    validate_legacy_strategy,
    detect_strategy_type,
    
    # 异常类
    StrategyAdapterError,
    LegacyStrategyWrapperError,
    StrategyLoadError,
    StrategyValidationError,
    ParameterConversionError,
    
    # 常量
    ADVANCED_REQUIRED_METHODS,
    ADVANCED_DATA_METHODS,
    
    # 便捷别名
    load_strategy,
    wrap_legacy_strategy,
)

__all__ = [
    # 主要函数
    "adapt_legacy_strategy",
    "load_advanced_strategy",
    "auto_adapt_strategy",
    
    # 参数转换
    "convert_params_to_advanced_config",
    "create_importable_strategy_config",
    
    # 验证函数
    "validate_advanced_strategy",
    "validate_legacy_strategy",
    "detect_strategy_type",
    
    # 异常类
    "StrategyAdapterError",
    "LegacyStrategyWrapperError",
    "StrategyLoadError",
    "StrategyValidationError",
    "ParameterConversionError",
    
    # 常量
    "ADVANCED_REQUIRED_METHODS",
    "ADVANCED_DATA_METHODS",
    
    # 便捷别名
    "load_strategy",
    "wrap_legacy_strategy",
]
