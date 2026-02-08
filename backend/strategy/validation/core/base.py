"""
验证模块基础类定义
包含验证器基类、验证结果类和严重程度枚举
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd
from loguru import logger


class ValidationSeverity(Enum):
    """
    验证严重程度枚举
    """

    INFO = "info"  # 信息提示，不影响验证通过
    WARNING = "warning"  # 警告，轻微偏差
    ERROR = "error"  # 错误，显著偏差
    CRITICAL = "critical"  # 严重错误，验证失败


@dataclass
class ValidationThresholds:
    """
    验证阈值配置
    """

    # 收益率相关阈值
    returns_tolerance: float = 0.01  # 收益率容差 1%
    annualized_return_tolerance: float = 0.02  # 年化收益率容差 2%
    daily_return_tolerance: float = 0.005  # 日收益率容差 0.5%

    # 信号相关阈值
    signal_timing_tolerance: int = 1  # 信号时间容差 1个周期
    signal_price_tolerance: float = 0.001  # 信号价格容差 0.1%

    # 持仓相关阈值
    position_tolerance: float = 0.001  # 持仓容差 0.1%
    position_value_tolerance: float = 0.01  # 持仓价值容差 1%

    # 资金相关阈值
    equity_tolerance: float = 0.01  # 资金容差 1%
    drawdown_tolerance: float = 0.02  # 回撤容差 2%

    # 交易相关阈值
    trade_count_tolerance: int = 0  # 交易数量容差 0笔
    trade_pnl_tolerance: float = 0.01  # 交易盈亏容差 1%
    trade_fee_tolerance: float = 0.001  # 交易费用容差 0.1%

    # 指标相关阈值
    metrics_tolerance: float = 0.05  # 指标容差 5%
    sharpe_tolerance: float = 0.1  # 夏普比率容差
    max_drawdown_tolerance: float = 0.02  # 最大回撤容差

    def get_tolerance(self, metric_type: str) -> float:
        """
        获取指定指标类型的容差

        Args:
            metric_type: 指标类型名称

        Returns:
            float: 容差值
        """
        tolerance_map = {
            "returns": self.returns_tolerance,
            "annualized_return": self.annualized_return_tolerance,
            "daily_return": self.daily_return_tolerance,
            "signal_timing": self.signal_timing_tolerance,
            "signal_price": self.signal_price_tolerance,
            "position": self.position_tolerance,
            "position_value": self.position_value_tolerance,
            "equity": self.equity_tolerance,
            "drawdown": self.drawdown_tolerance,
            "trade_count": self.trade_count_tolerance,
            "trade_pnl": self.trade_pnl_tolerance,
            "trade_fee": self.trade_fee_tolerance,
            "metrics": self.metrics_tolerance,
            "sharpe": self.sharpe_tolerance,
            "max_drawdown": self.max_drawdown_tolerance,
        }
        return tolerance_map.get(metric_type, 0.01)


@dataclass
class ValidationResult:
    """
    验证结果数据类

    存储单个验证项的详细结果信息
    """

    validator_name: str  # 验证器名称
    passed: bool  # 是否通过验证
    severity: ValidationSeverity  # 严重程度
    message: str  # 验证消息
    expected_value: Any = None  # 期望值
    actual_value: Any = None  # 实际值
    difference: Optional[float] = None  # 差异值
    difference_pct: Optional[float] = None  # 差异百分比
    threshold: Optional[float] = None  # 阈值
    details: Dict[str, Any] = field(default_factory=dict)  # 详细信息
    timestamp: datetime = field(default_factory=datetime.now)  # 时间戳
    traceback: Optional[str] = None  # 异常堆栈（如果有）

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典格式

        Returns:
            Dict[str, Any]: 字典表示
        """
        return {
            "validator_name": self.validator_name,
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "expected_value": self._serialize_value(self.expected_value),
            "actual_value": self._serialize_value(self.actual_value),
            "difference": self.difference,
            "difference_pct": self.difference_pct,
            "threshold": self.threshold,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback,
        }

    def _serialize_value(self, value: Any) -> Any:
        """
        序列化值，处理特殊类型

        Args:
            value: 任意值

        Returns:
            Any: 可序列化的值
        """
        if value is None:
            return None
        elif isinstance(value, (np.ndarray, pd.Series)):
            return value.tolist()
        elif isinstance(value, pd.DataFrame):
            return value.to_dict(orient="records")
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return value.value
        else:
            return value


class BaseValidator(ABC):
    """
    验证器基类

    所有具体验证器都需要继承此类并实现 validate 方法
    """

    name: str = "BaseValidator"
    description: str = "基础验证器"
    default_threshold: float = 0.01

    def __init__(self, threshold: Optional[float] = None, strict: bool = False):
        """
        初始化验证器

        Args:
            threshold: 验证阈值，如果为None则使用默认值
            strict: 是否严格模式（严格模式下任何偏差都视为错误）
        """
        self.threshold = threshold if threshold is not None else self.default_threshold
        self.strict = strict
        self.logger = logger.bind(validator=self.name)

    @abstractmethod
    def validate(self, expected: Any, actual: Any, **kwargs) -> ValidationResult:
        """
        执行验证

        Args:
            expected: 期望值/基准值
            actual: 实际值/待验证值
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        pass

    def calculate_difference(
        self, expected: Union[float, np.ndarray], actual: Union[float, np.ndarray]
    ) -> tuple:
        """
        计算差异值和差异百分比

        Args:
            expected: 期望值
            actual: 实际值

        Returns:
            tuple: (差异值, 差异百分比)
        """
        try:
            if isinstance(expected, (np.ndarray, pd.Series)) and isinstance(
                actual, (np.ndarray, pd.Series)
            ):
                # 数组类型差异计算
                diff = np.abs(expected - actual)
                diff_pct = np.abs((expected - actual) / (expected + 1e-10)) * 100
                return float(np.mean(diff)), float(np.mean(diff_pct))
            else:
                # 标量类型差异计算
                expected_float = float(expected)
                actual_float = float(actual)
                diff = abs(expected_float - actual_float)
                diff_pct = (
                    abs(diff / (expected_float + 1e-10)) * 100
                    if expected_float != 0
                    else 0.0
                )
                return diff, diff_pct
        except Exception as e:
            self.logger.warning(f"差异计算失败: {e}")
            return float("inf"), float("inf")

    def check_threshold(self, difference: float, threshold: Optional[float] = None) -> bool:
        """
        检查差异是否在阈值范围内

        Args:
            difference: 差异值
            threshold: 阈值（可选，默认使用实例阈值）

        Returns:
            bool: 是否在阈值内
        """
        thresh = threshold if threshold is not None else self.threshold
        return difference <= thresh

    def determine_severity(
        self, difference_pct: float, threshold: Optional[float] = None
    ) -> ValidationSeverity:
        """
        根据差异百分比确定严重程度

        Args:
            difference_pct: 差异百分比
            threshold: 基础阈值

        Returns:
            ValidationSeverity: 严重程度
        """
        if self.strict:
            return ValidationSeverity.ERROR if difference_pct > 0 else ValidationSeverity.INFO

        thresh = threshold if threshold is not None else self.threshold

        if difference_pct <= thresh:
            return ValidationSeverity.INFO
        elif difference_pct <= thresh * 2:
            return ValidationSeverity.WARNING
        elif difference_pct <= thresh * 5:
            return ValidationSeverity.ERROR
        else:
            return ValidationSeverity.CRITICAL

    def create_result(
        self,
        passed: bool,
        message: str,
        expected: Any = None,
        actual: Any = None,
        difference: Optional[float] = None,
        difference_pct: Optional[float] = None,
        severity: Optional[ValidationSeverity] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        """
        创建验证结果对象

        Args:
            passed: 是否通过
            message: 验证消息
            expected: 期望值
            actual: 实际值
            difference: 差异值
            difference_pct: 差异百分比
            severity: 严重程度
            details: 详细信息

        Returns:
            ValidationResult: 验证结果
        """
        if difference is None and expected is not None and actual is not None:
            difference, difference_pct = self.calculate_difference(expected, actual)

        if severity is None:
            severity = (
                ValidationSeverity.INFO
                if passed
                else self.determine_severity(difference_pct or 0)
            )

        return ValidationResult(
            validator_name=self.name,
            passed=passed,
            severity=severity,
            message=message,
            expected_value=expected,
            actual_value=actual,
            difference=difference,
            difference_pct=difference_pct,
            threshold=self.threshold,
            details=details or {},
        )

    def validate_not_none(self, value: Any, name: str = "value") -> ValidationResult:
        """
        验证值不为None

        Args:
            value: 待验证值
            name: 值名称

        Returns:
            ValidationResult: 验证结果
        """
        passed = value is not None
        return self.create_result(
            passed=passed,
            message=f"{name} 不为 None" if passed else f"{name} 为 None",
            expected="非 None 值",
            actual=value,
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.CRITICAL,
        )

    def validate_type(
        self, value: Any, expected_type: type, name: str = "value"
    ) -> ValidationResult:
        """
        验证值类型

        Args:
            value: 待验证值
            expected_type: 期望类型
            name: 值名称

        Returns:
            ValidationResult: 验证结果
        """
        passed = isinstance(value, expected_type)
        return self.create_result(
            passed=passed,
            message=f"{name} 类型正确" if passed else f"{name} 类型错误",
            expected=expected_type.__name__,
            actual=type(value).__name__,
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
        )


class ValidationSuite:
    """
    验证套件

    将多个验证器组合在一起执行
    """

    def __init__(self, name: str, description: str = ""):
        """
        初始化验证套件

        Args:
            name: 套件名称
            description: 套件描述
        """
        self.name = name
        self.description = description
        self.validators: List[BaseValidator] = []
        self.results: List[ValidationResult] = []

    def add_validator(self, validator: BaseValidator) -> "ValidationSuite":
        """
        添加验证器

        Args:
            validator: 验证器实例

        Returns:
            ValidationSuite: 自身，支持链式调用
        """
        self.validators.append(validator)
        return self

    def remove_validator(self, validator_name: str) -> bool:
        """
        移除验证器

        Args:
            validator_name: 验证器名称

        Returns:
            bool: 是否成功移除
        """
        for i, validator in enumerate(self.validators):
            if validator.name == validator_name:
                self.validators.pop(i)
                return True
        return False

    def run(
        self, expected: Any, actual: Any, context: Optional[Dict[str, Any]] = None
    ) -> List[ValidationResult]:
        """
        执行所有验证器

        Args:
            expected: 期望值
            actual: 实际值
            context: 上下文信息

        Returns:
            List[ValidationResult]: 验证结果列表
        """
        self.results = []
        context = context or {}

        logger.info(f"开始执行验证套件: {self.name}")
        logger.info(f"验证器数量: {len(self.validators)}")

        for validator in self.validators:
            try:
                result = validator.validate(expected, actual, **context)
                self.results.append(result)

                if not result.passed:
                    diff_str = f"{result.difference_pct:.2f}%" if result.difference_pct is not None else "N/A"
                    logger.warning(
                        f"验证失败: {validator.name} - {result.message} "
                        f"(差异: {diff_str})"
                    )
                else:
                    logger.debug(f"验证通过: {validator.name}")

            except Exception as e:
                logger.error(f"验证器执行异常: {validator.name} - {e}")
                error_result = ValidationResult(
                    validator_name=validator.name,
                    passed=False,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"验证执行异常: {str(e)}",
                    traceback=str(e),
                )
                self.results.append(error_result)

        logger.info(f"验证套件执行完成: {self.name}")
        return self.results

    def get_summary(self) -> Dict[str, Any]:
        """
        获取验证摘要

        Returns:
            Dict[str, Any]: 验证摘要信息
        """
        if not self.results:
            return {
                "suite_name": self.name,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0.0,
                "severity_counts": {},
            }

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        severity_counts = {
            "info": sum(1 for r in self.results if r.severity == ValidationSeverity.INFO),
            "warning": sum(
                1 for r in self.results if r.severity == ValidationSeverity.WARNING
            ),
            "error": sum(1 for r in self.results if r.severity == ValidationSeverity.ERROR),
            "critical": sum(
                1 for r in self.results if r.severity == ValidationSeverity.CRITICAL
            ),
        }

        return {
            "suite_name": self.name,
            "description": self.description,
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0.0,
            "severity_counts": severity_counts,
        }

    def all_passed(self) -> bool:
        """
        检查是否所有验证都通过

        Returns:
            bool: 是否全部通过
        """
        return all(r.passed for r in self.results) if self.results else True

    def has_critical(self) -> bool:
        """
        检查是否有严重错误

        Returns:
            bool: 是否有严重错误
        """
        return any(r.severity == ValidationSeverity.CRITICAL for r in self.results)
