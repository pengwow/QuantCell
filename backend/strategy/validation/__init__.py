"""
回测引擎验证模块

用于系统性验证回测引擎计算结果的准确性和可靠性。
提供多层次的验证指标体系和完整的验证报告功能。
"""

# 导入核心组件
from .core.base import BaseValidator, ValidationResult, ValidationSeverity, ValidationSuite
from .core.registry import ValidatorRegistry, registry, register_validator, get_validator
from .core.exceptions import ValidationError, ThresholdExceededError

# 导入验证器（自动注册）
from .validators import (
    # 收益率验证器
    TotalReturnValidator,
    AnnualizedReturnValidator,
    DailyReturnsValidator,
    CumulativeReturnsValidator,
    # 信号验证器
    SignalCountValidator,
    SignalTimingValidator,
    SignalTypeValidator,
    SignalPriceValidator,
    # 持仓验证器
    PositionQuantityValidator,
    PositionValueValidator,
    PositionChangeTimingValidator,
    # 资金验证器
    EquityCurveValidator,
    DrawdownValidator,
    CashBalanceValidator,
    # 交易验证器
    TradeCountValidator,
    TradePnLValidator,
    TradeFeeValidator,
    TradeTimingValidator,
    # 指标验证器
    SharpeRatioValidator,
    MaxDrawdownValidator,
    WinRateValidator,
    ProfitFactorValidator,
)

# 导入引擎验证器
from .engines import EventEngineValidator, VectorEngineValidator

# 导入运行器和报告
from .runner import ValidationRunner, BacktestValidator, quick_validate
from .reports.report_generator import ReportGenerator, ValidationReporter

__version__ = "1.0.0"

__all__ = [
    # 核心类
    "BaseValidator",
    "ValidationResult",
    "ValidationSeverity",
    "ValidationSuite",
    "ValidatorRegistry",
    "registry",
    "register_validator",
    "get_validator",
    "ValidationError",
    "ThresholdExceededError",
    # 收益率验证器
    "TotalReturnValidator",
    "AnnualizedReturnValidator",
    "DailyReturnsValidator",
    "CumulativeReturnsValidator",
    # 信号验证器
    "SignalCountValidator",
    "SignalTimingValidator",
    "SignalTypeValidator",
    "SignalPriceValidator",
    # 持仓验证器
    "PositionQuantityValidator",
    "PositionValueValidator",
    "PositionChangeTimingValidator",
    # 资金验证器
    "EquityCurveValidator",
    "DrawdownValidator",
    "CashBalanceValidator",
    # 交易验证器
    "TradeCountValidator",
    "TradePnLValidator",
    "TradeFeeValidator",
    "TradeTimingValidator",
    # 指标验证器
    "SharpeRatioValidator",
    "MaxDrawdownValidator",
    "WinRateValidator",
    "ProfitFactorValidator",
    # 引擎验证器
    "EventEngineValidator",
    "VectorEngineValidator",
    # 运行器
    "ValidationRunner",
    "BacktestValidator",
    "quick_validate",
    # 报告
    "ReportGenerator",
    "ValidationReporter",
]
