"""
事件引擎验证器
用于验证事件引擎的处理逻辑和输出结果
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from loguru import logger

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity, ValidationSuite
from ..core.registry import register_validator


class EventEngineValidator(BaseValidator):
    """
    事件引擎验证器
    验证事件引擎的事件处理、订单执行和状态管理
    """

    name = "EventEngineValidator"
    description = "验证事件引擎处理逻辑和输出结果"
    default_threshold = 0.01

    def __init__(self, threshold: Optional[float] = None, strict: bool = False):
        super().__init__(threshold, strict)
        self.sub_validators = self._create_sub_validators()

    def _create_sub_validators(self) -> List[BaseValidator]:
        """创建子验证器列表"""
        return [
            EventProcessingValidator(),
            OrderExecutionValidator(),
            StateConsistencyValidator(),
        ]

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证事件引擎结果

        Args:
            expected: 期望结果
            actual: 实际结果
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        results = []
        all_passed = True

        for validator in self.sub_validators:
            try:
                result = validator.validate(expected, actual, **kwargs)
                results.append(result)
                if not result.passed:
                    all_passed = False
            except Exception as e:
                logger.error(f"子验证器执行失败: {validator.name} - {e}")
                all_passed = False

        # 汇总结果
        passed_count = sum(1 for r in results if r.passed)
        total_count = len(results)

        passed = all_passed

        if passed:
            message = f"事件引擎验证通过 ({passed_count}/{total_count} 项子验证通过)"
            severity = ValidationSeverity.INFO
        else:
            message = f"事件引擎验证失败 ({passed_count}/{total_count} 项子验证通过)"
            severity = ValidationSeverity.ERROR

        return self.create_result(
            passed=passed,
            message=message,
            severity=severity,
            details={
                "sub_results": [r.to_dict() for r in results],
                "passed_count": passed_count,
                "total_count": total_count,
            },
        )


class EventProcessingValidator(BaseValidator):
    """
    事件处理验证器
    验证事件处理的正确性
    """

    name = "EventProcessingValidator"
    description = "验证事件处理逻辑"
    default_threshold = 0

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """验证事件处理"""
        expected_events = expected.get("processed_events", [])
        actual_events = actual.get("processed_events", [])

        if len(expected_events) != len(actual_events):
            return self.create_result(
                passed=False,
                message=f"处理事件数量不一致 (期望: {len(expected_events)}, 实际: {len(actual_events)})",
                severity=ValidationSeverity.ERROR,
            )

        # 检查事件类型匹配
        mismatches = 0
        for i, (exp, act) in enumerate(zip(expected_events, actual_events)):
            if exp.get("type") != act.get("type"):
                mismatches += 1

        passed = mismatches == 0

        return self.create_result(
            passed=passed,
            message=f"事件处理验证{'通过' if passed else '失败'} (不匹配: {mismatches})",
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
            details={
                "expected_count": len(expected_events),
                "actual_count": len(actual_events),
                "mismatches": mismatches,
            },
        )


class OrderExecutionValidator(BaseValidator):
    """
    订单执行验证器
    验证订单执行的正确性
    """

    name = "OrderExecutionValidator"
    description = "验证订单执行逻辑"
    default_threshold = 0.001

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """验证订单执行"""
        expected_orders = expected.get("executed_orders", [])
        actual_orders = actual.get("executed_orders", [])

        if len(expected_orders) != len(actual_orders):
            return self.create_result(
                passed=False,
                message=f"执行订单数量不一致 (期望: {len(expected_orders)}, 实际: {len(actual_orders)})",
                severity=ValidationSeverity.ERROR,
            )

        # 检查订单详情
        mismatches = 0
        for exp, act in zip(expected_orders, actual_orders):
            if (exp.get("price") != act.get("price") or
                exp.get("size") != act.get("size") or
                exp.get("side") != act.get("side")):
                mismatches += 1

        passed = mismatches == 0

        return self.create_result(
            passed=passed,
            message=f"订单执行验证{'通过' if passed else '失败'} (不匹配: {mismatches})",
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
            details={
                "expected_count": len(expected_orders),
                "actual_count": len(actual_orders),
                "mismatches": mismatches,
            },
        )


class StateConsistencyValidator(BaseValidator):
    """
    状态一致性验证器
    验证引擎状态的一致性
    """

    name = "StateConsistencyValidator"
    description = "验证引擎状态一致性"
    default_threshold = 0.01

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """验证状态一致性"""
        issues = []

        # 检查持仓
        exp_position = expected.get("final_position", 0)
        act_position = actual.get("final_position", 0)
        if exp_position != act_position:
            issues.append(f"持仓不一致: 期望={exp_position}, 实际={act_position}")

        # 检查现金
        exp_cash = expected.get("final_cash", 0)
        act_cash = actual.get("final_cash", 0)
        if abs(exp_cash - act_cash) > self.threshold:
            issues.append(f"现金不一致: 期望={exp_cash}, 实际={act_cash}")

        passed = len(issues) == 0

        return self.create_result(
            passed=passed,
            message=f"状态一致性验证{'通过' if passed else '失败'}",
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
            details={
                "issues": issues,
                "issue_count": len(issues),
            },
        )


# 注册验证器
register_validator("event_engine", EventEngineValidator)
