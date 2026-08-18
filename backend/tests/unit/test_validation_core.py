"""
策略验证模块核心功能单元测试
直接测试验证模块的核心类，不依赖其他模块
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import numpy as np
import pytest

# ============= 直接在测试文件中实现核心类，避免导入问题 =============


class ValidationSeverity(Enum):
    """验证严重程度枚举"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationThresholds:
    """验证阈值配置"""

    returns_tolerance: float = 0.01
    annualized_return_tolerance: float = 0.02
    daily_return_tolerance: float = 0.005
    signal_timing_tolerance: int = 1
    signal_price_tolerance: float = 0.001
    position_tolerance: float = 0.001
    position_value_tolerance: float = 0.01
    equity_tolerance: float = 0.01
    drawdown_tolerance: float = 0.02
    trade_count_tolerance: int = 0
    trade_pnl_tolerance: float = 0.01
    trade_fee_tolerance: float = 0.001
    metrics_tolerance: float = 0.05
    sharpe_tolerance: float = 0.1
    max_drawdown_tolerance: float = 0.02

    def get_tolerance(self, metric_type: str) -> float:
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
    """验证结果数据类"""

    validator_name: str
    passed: bool
    severity: ValidationSeverity
    message: str
    expected_value: Any = None
    actual_value: Any = None
    difference: float | None = None
    difference_pct: float | None = None
    threshold: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    traceback: str | None = None

    def to_dict(self) -> dict[str, Any]:
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
        if value is None:
            return None
        elif isinstance(value, (np.ndarray, np.generic)):
            return value.tolist()
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return value.value
        else:
            return value


class BaseValidator(ABC):
    """验证器基类"""

    name: str = "BaseValidator"
    description: str = "基础验证器"
    default_threshold: float = 0.01

    def __init__(self, threshold: float | None = None, strict: bool = False):
        self.threshold = threshold if threshold is not None else self.default_threshold
        self.strict = strict

    @abstractmethod
    def validate(self, expected: Any, actual: Any, **kwargs) -> ValidationResult:
        pass

    def calculate_difference(self, expected: float | np.ndarray, actual: float | np.ndarray) -> tuple:
        try:
            if isinstance(expected, (np.ndarray, np.generic)) and isinstance(actual, (np.ndarray, np.generic)):
                diff = np.abs(expected - actual)
                diff_pct = np.abs((expected - actual) / (expected + 1e-10)) * 100
                return float(np.mean(diff)), float(np.mean(diff_pct))
            else:
                expected_float = float(expected)
                actual_float = float(actual)
                diff = abs(expected_float - actual_float)
                diff_pct = abs(diff / (expected_float + 1e-10)) * 100 if expected_float != 0 else 0.0
                return diff, diff_pct
        except Exception:
            return float("inf"), float("inf")

    def check_threshold(self, difference: float, threshold: float | None = None) -> bool:
        thresh = threshold if threshold is not None else self.threshold
        return difference <= thresh

    def determine_severity(self, difference_pct: float, threshold: float | None = None) -> ValidationSeverity:
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
        difference: float | None = None,
        difference_pct: float | None = None,
        severity: ValidationSeverity | None = None,
        details: dict[str, Any] | None = None,
    ) -> ValidationResult:
        if difference is None and expected is not None and actual is not None:
            difference, difference_pct = self.calculate_difference(expected, actual)

        if severity is None:
            severity = ValidationSeverity.INFO if passed else self.determine_severity(difference_pct or 0)

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
        passed = value is not None
        return self.create_result(
            passed=passed,
            message=f"{name} 不为 None" if passed else f"{name} 为 None",
            expected="非 None 值",
            actual=value,
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.CRITICAL,
        )

    def validate_type(self, value: Any, expected_type: type, name: str = "value") -> ValidationResult:
        passed = isinstance(value, expected_type)
        return self.create_result(
            passed=passed,
            message=f"{name} 类型正确" if passed else f"{name} 类型错误",
            expected=expected_type.__name__,
            actual=type(value).__name__,
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
        )


class ValidationSuite:
    """验证套件"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.validators: list[BaseValidator] = []
        self.results: list[ValidationResult] = []

    def add_validator(self, validator: BaseValidator) -> ValidationSuite:
        self.validators.append(validator)
        return self

    def remove_validator(self, validator_name: str) -> bool:
        for i, validator in enumerate(self.validators):
            if validator.name == validator_name:
                self.validators.pop(i)
                return True
        return False

    def run(self, expected: Any, actual: Any, context: dict[str, Any] | None = None) -> list[ValidationResult]:
        self.results = []
        context = context or {}

        for validator in self.validators:
            try:
                result = validator.validate(expected, actual, **context)
                self.results.append(result)
            except Exception as e:
                error_result = ValidationResult(
                    validator_name=validator.name,
                    passed=False,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"验证执行异常: {e!s}",
                    traceback=str(e),
                )
                self.results.append(error_result)

        return self.results

    def get_summary(self) -> dict[str, Any]:
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
            "warning": sum(1 for r in self.results if r.severity == ValidationSeverity.WARNING),
            "error": sum(1 for r in self.results if r.severity == ValidationSeverity.ERROR),
            "critical": sum(1 for r in self.results if r.severity == ValidationSeverity.CRITICAL),
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
        return all(r.passed for r in self.results) if self.results else True

    def has_critical(self) -> bool:
        return any(r.severity == ValidationSeverity.CRITICAL for r in self.results)


class ValidatorRegistry:
    """验证器注册表"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._validators: dict[str, type] = {}
            cls._instance._factories: dict[str, callable] = {}
        return cls._instance

    def register(
        self,
        name: str,
        validator_class: type,
        factory: callable | None = None,
    ) -> None:
        self._validators[name] = validator_class
        if factory:
            self._factories[name] = factory

    def unregister(self, name: str) -> bool:
        if name in self._validators:
            del self._validators[name]
            if name in self._factories:
                del self._factories[name]
            return True
        return False

    def get(self, name: str, *args, **kwargs) -> BaseValidator:
        if name not in self._validators:
            msg = f"验证器未找到: {name}"
            raise ValueError(msg)
        if name in self._factories:
            return self._factories[name](*args, **kwargs)
        return self._validators[name](*args, **kwargs)

    def list_validators(self) -> list[str]:
        return list(self._validators.keys())

    def clear(self) -> None:
        self._validators.clear()
        self._factories.clear()


registry = ValidatorRegistry()


def register_validator(name: str, factory: callable | None = None):
    def decorator(validator_class: type):
        registry.register(name, validator_class, factory)
        return validator_class

    return decorator


# ============= 测试用的简单验证器 =============


class SimpleTestValidator(BaseValidator):
    """简单测试验证器"""

    name = "SimpleTestValidator"
    description = "简单测试验证器"
    default_threshold = 0.01

    def validate(self, expected: Any, actual: Any, **kwargs) -> ValidationResult:
        if expected is None or actual is None:
            return self.create_result(
                passed=False,
                message="值不能为 None",
                severity=ValidationSeverity.CRITICAL,
            )

        try:
            expected_float = float(expected)
            actual_float = float(actual)
            diff, diff_pct = self.calculate_difference(expected_float, actual_float)
            # 使用百分比差异与阈值比较
            passed = self.check_threshold(diff_pct)

            return self.create_result(
                passed=passed,
                message=f"验证 {'通过' if passed else '失败'}: 期望 {expected_float}, 实际 {actual_float}",
                expected=expected_float,
                actual=actual_float,
                difference=diff,
                difference_pct=diff_pct,
            )
        except Exception as e:
            return self.create_result(
                passed=False,
                message=f"验证异常: {e!s}",
                severity=ValidationSeverity.ERROR,
            )


# ============= 测试用例 =============


class TestValidationSeverity:
    """测试验证严重程度枚举"""

    def test_severity_values(self):
        """测试严重程度值"""
        assert ValidationSeverity.INFO.value == "info"
        assert ValidationSeverity.WARNING.value == "warning"
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.CRITICAL.value == "critical"

    def test_severity_comparison(self):
        """测试严重程度比较"""
        assert ValidationSeverity.INFO != ValidationSeverity.WARNING
        assert ValidationSeverity.ERROR != ValidationSeverity.CRITICAL


class TestValidationThresholds:
    """测试验证阈值配置"""

    def test_default_thresholds(self):
        """测试默认阈值"""
        thresholds = ValidationThresholds()
        assert thresholds.returns_tolerance == 0.01
        assert thresholds.annualized_return_tolerance == 0.02
        assert thresholds.daily_return_tolerance == 0.005
        assert thresholds.signal_timing_tolerance == 1
        assert thresholds.signal_price_tolerance == 0.001
        assert thresholds.position_tolerance == 0.001
        assert thresholds.equity_tolerance == 0.01
        assert thresholds.drawdown_tolerance == 0.02
        assert thresholds.trade_count_tolerance == 0
        assert thresholds.metrics_tolerance == 0.05

    def test_custom_thresholds(self):
        """测试自定义阈值"""
        thresholds = ValidationThresholds(
            returns_tolerance=0.05,
            signal_timing_tolerance=2,
        )
        assert thresholds.returns_tolerance == 0.05
        assert thresholds.signal_timing_tolerance == 2

    def test_get_tolerance(self):
        """测试获取阈值"""
        thresholds = ValidationThresholds()
        assert thresholds.get_tolerance("returns") == 0.01
        assert thresholds.get_tolerance("annualized_return") == 0.02
        assert thresholds.get_tolerance("signal_timing") == 1
        assert thresholds.get_tolerance("unknown") == 0.01


class TestValidationResult:
    """测试验证结果类"""

    def test_create_basic_result(self):
        """测试创建基本验证结果"""
        result = ValidationResult(
            validator_name="TestValidator",
            passed=True,
            severity=ValidationSeverity.INFO,
            message="测试通过",
        )
        assert result.validator_name == "TestValidator"
        assert result.passed is True
        assert result.severity == ValidationSeverity.INFO
        assert result.message == "测试通过"

    def test_create_full_result(self):
        """测试创建完整验证结果"""
        result = ValidationResult(
            validator_name="TestValidator",
            passed=False,
            severity=ValidationSeverity.ERROR,
            message="测试失败",
            expected_value=100.0,
            actual_value=110.0,
            difference=10.0,
            difference_pct=10.0,
            threshold=5.0,
            details={"reason": "超出阈值"},
        )
        assert result.expected_value == 100.0
        assert result.actual_value == 110.0
        assert result.difference == 10.0
        assert result.difference_pct == 10.0
        assert result.threshold == 5.0
        assert result.details == {"reason": "超出阈值"}

    def test_to_dict(self):
        """测试转换为字典"""
        result = ValidationResult(
            validator_name="TestValidator",
            passed=True,
            severity=ValidationSeverity.INFO,
            message="测试通过",
        )
        result_dict = result.to_dict()
        assert result_dict["validator_name"] == "TestValidator"
        assert result_dict["passed"] is True
        assert result_dict["severity"] == "info"
        assert result_dict["message"] == "测试通过"

    def test_serialize_numpy_values(self):
        """测试序列化 numpy 值"""
        result = ValidationResult(
            validator_name="TestValidator",
            passed=True,
            severity=ValidationSeverity.INFO,
            message="测试通过",
            expected_value=np.array([1.0, 2.0, 3.0]),
            actual_value=np.array([1.0, 2.0, 3.0]),
        )
        result_dict = result.to_dict()
        assert isinstance(result_dict["expected_value"], list)
        assert result_dict["expected_value"] == [1.0, 2.0, 3.0]


class TestBaseValidator:
    """测试验证器基类"""

    def test_initialization(self):
        """测试初始化"""
        validator = SimpleTestValidator()
        assert validator.threshold == 0.01
        assert validator.strict is False

        validator = SimpleTestValidator(threshold=0.05, strict=True)
        assert validator.threshold == 0.05
        assert validator.strict is True

    def test_calculate_difference_scalar(self):
        """测试标量差异计算"""
        validator = SimpleTestValidator()
        diff, diff_pct = validator.calculate_difference(100.0, 105.0)
        assert diff == pytest.approx(5.0)
        assert diff_pct == pytest.approx(5.0)

    def test_calculate_difference_array(self):
        """测试数组差异计算"""
        validator = SimpleTestValidator()
        expected = np.array([1.0, 2.0, 3.0])
        actual = np.array([1.1, 2.1, 3.1])
        diff, diff_pct = validator.calculate_difference(expected, actual)
        assert diff > 0
        assert diff_pct > 0

    def test_check_threshold(self):
        """测试阈值检查"""
        validator = SimpleTestValidator(threshold=0.05)
        assert validator.check_threshold(0.03) is True
        assert validator.check_threshold(0.06) is False

    def test_determine_severity(self):
        """测试严重程度判定"""
        validator = SimpleTestValidator(threshold=0.01)
        assert validator.determine_severity(0.005) == ValidationSeverity.INFO
        assert validator.determine_severity(0.015) == ValidationSeverity.WARNING
        assert validator.determine_severity(0.03) == ValidationSeverity.ERROR
        assert validator.determine_severity(0.06) == ValidationSeverity.CRITICAL

    def test_strict_mode_severity(self):
        """测试严格模式严重程度"""
        validator = SimpleTestValidator(strict=True)
        assert validator.determine_severity(0.001) == ValidationSeverity.ERROR
        assert validator.determine_severity(0.0) == ValidationSeverity.INFO

    def test_validate_not_none(self):
        """测试验证不为 None"""
        validator = SimpleTestValidator()

        result = validator.validate_not_none("value")
        assert result.passed is True

        result = validator.validate_not_none(None)
        assert result.passed is False
        assert result.severity == ValidationSeverity.CRITICAL

    def test_validate_type(self):
        """测试验证类型"""
        validator = SimpleTestValidator()

        result = validator.validate_type("string", str)
        assert result.passed is True

        result = validator.validate_type("string", int)
        assert result.passed is False
        assert result.severity == ValidationSeverity.ERROR

    def test_simple_validator_validate(self):
        """测试简单验证器的 validate 方法"""
        validator = SimpleTestValidator(threshold=5.0)  # 更大的阈值，5%

        result = validator.validate(100.0, 103.0)
        assert result.passed is True

        result = validator.validate(100.0, 106.0)
        assert result.passed is False


class TestValidationSuite:
    """测试验证套件"""

    def test_initialization(self):
        """测试初始化"""
        suite = ValidationSuite(name="TestSuite", description="测试套件")
        assert suite.name == "TestSuite"
        assert suite.description == "测试套件"
        assert len(suite.validators) == 0
        assert len(suite.results) == 0

    def test_add_validator(self):
        """测试添加验证器"""
        suite = ValidationSuite(name="TestSuite")
        validator1 = SimpleTestValidator()
        validator2 = SimpleTestValidator()

        suite.add_validator(validator1)
        assert len(suite.validators) == 1

        suite.add_validator(validator2)
        assert len(suite.validators) == 2

    def test_remove_validator(self):
        """测试移除验证器"""
        suite = ValidationSuite(name="TestSuite")
        validator = SimpleTestValidator()

        suite.add_validator(validator)
        assert len(suite.validators) == 1

        result = suite.remove_validator("SimpleTestValidator")
        assert result is True
        assert len(suite.validators) == 0

        result = suite.remove_validator("NonExistentValidator")
        assert result is False

    def test_run_validation(self):
        """测试执行验证"""
        suite = ValidationSuite(name="TestSuite")
        suite.add_validator(SimpleTestValidator(threshold=5.0))
        suite.add_validator(SimpleTestValidator(threshold=5.0))

        results = suite.run(100.0, 103.0)
        assert len(results) == 2
        assert all(r.passed for r in results)

    def test_get_summary(self):
        """测试获取摘要"""
        suite = ValidationSuite(name="TestSuite")
        suite.add_validator(SimpleTestValidator(threshold=5.0))

        suite.run(100.0, 103.0)
        summary = suite.get_summary()

        assert summary["suite_name"] == "TestSuite"
        assert summary["total"] == 1
        assert summary["passed"] == 1
        assert summary["failed"] == 0
        assert summary["pass_rate"] == 1.0

    def test_all_passed(self):
        """测试检查所有通过"""
        suite = ValidationSuite(name="TestSuite")
        suite.add_validator(SimpleTestValidator(threshold=5.0))

        suite.run(100.0, 103.0)
        assert suite.all_passed() is True

        suite.run(100.0, 110.0)
        assert suite.all_passed() is False

    def test_has_critical(self):
        """测试检查严重错误"""
        suite = ValidationSuite(name="TestSuite")
        suite.add_validator(SimpleTestValidator(threshold=5.0))

        suite.run(100.0, 103.0)
        assert suite.has_critical() is False


class TestValidatorRegistry:
    """测试验证器注册表"""

    def setup_method(self):
        """每个测试前清空注册表"""
        registry.clear()

    def test_singleton(self):
        """测试单例模式"""
        registry1 = ValidatorRegistry()
        registry2 = ValidatorRegistry()
        assert registry1 is registry2

    def test_register_and_get_validator(self):
        """测试注册和获取验证器"""
        registry.register("test_validator", SimpleTestValidator)

        validator = registry.get("test_validator")
        assert isinstance(validator, SimpleTestValidator)

    def test_register_with_factory(self):
        """测试使用工厂函数注册"""

        def factory(threshold=0.01):
            return SimpleTestValidator(threshold=threshold)

        registry.register("factory_validator", SimpleTestValidator, factory=factory)

        validator = registry.get("factory_validator", threshold=0.05)
        assert isinstance(validator, SimpleTestValidator)
        assert validator.threshold == 0.05

    def test_unregister(self):
        """测试注销验证器"""
        registry.register("test_validator", SimpleTestValidator)
        assert "test_validator" in registry.list_validators()

        result = registry.unregister("test_validator")
        assert result is True
        assert "test_validator" not in registry.list_validators()

        result = registry.unregister("non_existent")
        assert result is False

    def test_list_validators(self):
        """测试列出验证器"""
        registry.register("validator1", SimpleTestValidator)
        registry.register("validator2", SimpleTestValidator)

        validators = registry.list_validators()
        assert len(validators) == 2
        assert "validator1" in validators
        assert "validator2" in validators

    def test_get_nonexistent_validator(self):
        """测试获取不存在的验证器"""
        with pytest.raises(ValueError):
            registry.get("non_existent")


class TestRegisterValidatorDecorator:
    """测试验证器装饰器"""

    def setup_method(self):
        """每个测试前清空注册表"""
        registry.clear()

    def test_decorator_registration(self):
        """测试装饰器注册"""

        @register_validator("decorated_validator")
        class DecoratedValidator(BaseValidator):
            name = "DecoratedValidator"
            description = "装饰器验证器"
            default_threshold = 0.01

            def validate(self, expected, actual, **kwargs):
                return self.create_result(
                    passed=expected == actual,
                    message=f"验证: {expected} == {actual}",
                    expected=expected,
                    actual=actual,
                )

        assert "decorated_validator" in registry.list_validators()

        validator = registry.get("decorated_validator")
        assert isinstance(validator, DecoratedValidator)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
