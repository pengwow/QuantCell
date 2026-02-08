"""
向量引擎验证器
用于验证向量引擎的处理逻辑和输出结果
"""

from typing import Any, Dict, List, Optional
import numpy as np
from loguru import logger

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class VectorEngineValidator(BaseValidator):
    """
    向量引擎验证器
    验证向量引擎的向量化计算、信号处理和结果输出
    """

    name = "VectorEngineValidator"
    description = "验证向量引擎处理逻辑和输出结果"
    default_threshold = 0.01

    def __init__(self, threshold: Optional[float] = None, strict: bool = False):
        super().__init__(threshold, strict)
        self.sub_validators = self._create_sub_validators()

    def _create_sub_validators(self) -> List[BaseValidator]:
        """创建子验证器列表"""
        return [
            VectorizedCalculationValidator(),
            SignalProcessingValidator(),
            NumbaConsistencyValidator(),
        ]

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证向量引擎结果

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
            message = f"向量引擎验证通过 ({passed_count}/{total_count} 项子验证通过)"
            severity = ValidationSeverity.INFO
        else:
            message = f"向量引擎验证失败 ({passed_count}/{total_count} 项子验证通过)"
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


class VectorizedCalculationValidator(BaseValidator):
    """
    向量化计算验证器
    验证向量化计算的正确性
    """

    name = "VectorizedCalculationValidator"
    description = "验证向量化计算逻辑"
    default_threshold = 0.001

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """验证向量化计算"""
        expected_cash = expected.get("cash", [])
        actual_cash = actual.get("cash", [])

        if len(expected_cash) != len(actual_cash):
            return self.create_result(
                passed=False,
                message=f"现金序列长度不一致 (期望: {len(expected_cash)}, 实际: {len(actual_cash)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异
        if len(expected_cash) > 0:
            expected_arr = np.array(expected_cash, dtype=float)
            actual_arr = np.array(actual_cash, dtype=float)

            diff = np.abs(expected_arr - actual_arr)
            max_diff = np.max(diff)
            mean_diff = np.mean(diff)

            # 相对差异
            non_zero_mask = expected_arr != 0
            if np.any(non_zero_mask):
                rel_diff = diff[non_zero_mask] / expected_arr[non_zero_mask]
                max_rel_diff = np.max(rel_diff)
            else:
                max_rel_diff = 0.0
        else:
            max_diff = 0.0
            mean_diff = 0.0
            max_rel_diff = 0.0

        passed = max_rel_diff <= self.threshold

        return self.create_result(
            passed=passed,
            message=f"向量化计算验证{'通过' if passed else '失败'} (最大相对差异: {max_rel_diff*100:.4f}%)",
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
            details={
                "sequence_length": len(expected_cash),
                "max_absolute_diff": float(max_diff),
                "mean_absolute_diff": float(mean_diff),
                "max_relative_diff": float(max_rel_diff),
            },
        )


class SignalProcessingValidator(BaseValidator):
    """
    信号处理验证器
    验证信号处理的正确性
    """

    name = "SignalProcessingValidator"
    description = "验证信号处理逻辑"
    default_threshold = 0

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """验证信号处理"""
        expected_signals = expected.get("signals", [])
        actual_signals = actual.get("signals", [])

        if isinstance(expected_signals, np.ndarray):
            expected_signals = expected_signals.tolist()
        if isinstance(actual_signals, np.ndarray):
            actual_signals = actual_signals.tolist()

        if len(expected_signals) != len(actual_signals):
            return self.create_result(
                passed=False,
                message=f"信号序列长度不一致 (期望: {len(expected_signals)}, 实际: {len(actual_signals)})",
                severity=ValidationSeverity.ERROR,
            )

        # 统计信号差异
        mismatches = sum(1 for e, a in zip(expected_signals, actual_signals) if e != a)
        mismatch_rate = mismatches / len(expected_signals) if expected_signals else 0

        passed = mismatches == 0

        return self.create_result(
            passed=passed,
            message=f"信号处理验证{'通过' if passed else '失败'} (不匹配: {mismatches}, 不匹配率: {mismatch_rate*100:.2f}%)",
            severity=ValidationSeverity.INFO if passed else ValidationSeverity.ERROR,
            details={
                "signal_count": len(expected_signals),
                "mismatches": mismatches,
                "mismatch_rate": mismatch_rate,
            },
        )


class NumbaConsistencyValidator(BaseValidator):
    """
    Numba一致性验证器
    验证Numba编译版本和Python版本的一致性
    """

    name = "NumbaConsistencyValidator"
    description = "验证Numba编译一致性"
    default_threshold = 0.001

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """验证Numba一致性"""
        # 检查是否使用了Numba
        expected_numba = expected.get("used_numba", False)
        actual_numba = actual.get("used_numba", False)

        if expected_numba != actual_numba:
            return self.create_result(
                passed=False,
                message=f"Numba使用状态不一致 (期望: {expected_numba}, 实际: {actual_numba})",
                severity=ValidationSeverity.WARNING,
            )

        # 如果都使用了Numba，验证结果一致性
        if expected_numba and actual_numba:
            expected_metrics = expected.get("metrics", {})
            actual_metrics = actual.get("metrics", {})

            issues = []
            for key in ["total_pnl", "total_fees", "win_rate", "sharpe_ratio"]:
                exp_val = expected_metrics.get(key)
                act_val = actual_metrics.get(key)
                if exp_val is not None and act_val is not None:
                    if exp_val != 0:
                        diff_pct = abs(exp_val - act_val) / abs(exp_val)
                        if diff_pct > self.threshold:
                            issues.append(f"{key}: 期望={exp_val:.6f}, 实际={act_val:.6f}, 差异={diff_pct*100:.4f}%")

            passed = len(issues) == 0

            return self.create_result(
                passed=passed,
                message=f"Numba一致性验证{'通过' if passed else '失败'}",
                severity=ValidationSeverity.INFO if passed else ValidationSeverity.WARNING,
                details={
                    "used_numba": actual_numba,
                    "issues": issues,
                    "issue_count": len(issues),
                },
            )

        return self.create_result(
            passed=True,
            message="Numba未使用，跳过一致性验证",
            severity=ValidationSeverity.INFO,
            details={"used_numba": actual_numba},
        )


# 注册验证器
register_validator("vector_engine", VectorEngineValidator)
