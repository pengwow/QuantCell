"""
绩效指标验证器
用于验证回测结果中的绩效指标计算准确性
"""

from typing import Any, Dict, Optional
import numpy as np

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class SharpeRatioValidator(BaseValidator):
    """
    夏普比率验证器
    验证夏普比率计算的一致性
    """

    name = "SharpeRatioValidator"
    description = "验证夏普比率计算一致性"
    default_threshold = 0.1  # 夏普比率容差

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证夏普比率

        Args:
            expected: 期望结果
            actual: 实际结果
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_sharpe = self._extract_sharpe(expected)
        actual_sharpe = self._extract_sharpe(actual)

        if expected_sharpe is None or actual_sharpe is None:
            return self.create_result(
                passed=False,
                message="夏普比率数据缺失",
                severity=ValidationSeverity.CRITICAL,
            )

        difference = abs(expected_sharpe - actual_sharpe)
        passed = difference <= self.threshold

        severity = self.determine_severity(difference / max(abs(expected_sharpe), 1))

        if passed:
            message = (
                f"夏普比率验证通过 (期望: {expected_sharpe:.4f}, 实际: {actual_sharpe:.4f})"
            )
        else:
            message = (
                f"夏普比率存在差异 (期望: {expected_sharpe:.4f}, "
                f"实际: {actual_sharpe:.4f}, 差异: {difference:.4f})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=float(expected_sharpe),
            actual=float(actual_sharpe),
            difference=float(difference),
            severity=severity,
            details={
                "expected_sharpe": float(expected_sharpe),
                "actual_sharpe": float(actual_sharpe),
                "difference": float(difference),
            },
        )

    def _extract_sharpe(self, data: Dict[str, Any]) -> Optional[float]:
        """提取夏普比率"""
        if not isinstance(data, dict):
            return None

        for key in ["sharpe_ratio", "Sharpe Ratio", "sharpe", "Sharpe"]:
            if key in data:
                value = data[key]
                if isinstance(value, (int, float)):
                    return float(value)
        return None


class MaxDrawdownValidator(BaseValidator):
    """
    最大回撤验证器
    验证最大回撤计算的一致性
    """

    name = "MaxDrawdownValidator"
    description = "验证最大回撤计算一致性"
    default_threshold = 0.02  # 2% 容差

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证最大回撤

        Args:
            expected: 期望结果
            actual: 实际结果
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_dd = self._extract_max_drawdown(expected)
        actual_dd = self._extract_max_drawdown(actual)

        if expected_dd is None or actual_dd is None:
            return self.create_result(
                passed=False,
                message="最大回撤数据缺失",
                severity=ValidationSeverity.CRITICAL,
            )

        difference = abs(expected_dd - actual_dd)
        difference_pct = abs(difference / expected_dd) if expected_dd != 0 else 0

        passed = difference_pct <= self.threshold

        severity = self.determine_severity(difference_pct)

        if passed:
            message = (
                f"最大回撤验证通过 (期望: {expected_dd:.4f}%, 实际: {actual_dd:.4f}%)"
            )
        else:
            message = (
                f"最大回撤存在差异 (期望: {expected_dd:.4f}%, "
                f"实际: {actual_dd:.4f}%, 差异: {difference_pct*100:.2f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=float(expected_dd),
            actual=float(actual_dd),
            difference=float(difference),
            severity=severity,
            details={
                "expected_max_drawdown": float(expected_dd),
                "actual_max_drawdown": float(actual_dd),
                "difference": float(difference),
                "difference_pct": float(difference_pct),
            },
        )

    def _extract_max_drawdown(self, data: Dict[str, Any]) -> Optional[float]:
        """提取最大回撤"""
        if not isinstance(data, dict):
            return None

        for key in ["max_drawdown", "Max Drawdown [%]", "max_drawdown_pct", "Max. Drawdown [%]"]:
            if key in data:
                value = data[key]
                if isinstance(value, (int, float)):
                    return float(value)
        return None


class WinRateValidator(BaseValidator):
    """
    胜率验证器
    验证胜率计算的一致性
    """

    name = "WinRateValidator"
    description = "验证胜率计算一致性"
    default_threshold = 0.05  # 5% 容差

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证胜率

        Args:
            expected: 期望结果
            actual: 实际结果
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_wr = self._extract_win_rate(expected)
        actual_wr = self._extract_win_rate(actual)

        if expected_wr is None or actual_wr is None:
            return self.create_result(
                passed=False,
                message="胜率数据缺失",
                severity=ValidationSeverity.CRITICAL,
            )

        difference = abs(expected_wr - actual_wr)
        passed = difference <= self.threshold * 100  # 转换为百分比

        severity = self.determine_severity(difference / 100)

        if passed:
            message = (
                f"胜率验证通过 (期望: {expected_wr:.2f}%, 实际: {actual_wr:.2f}%)"
            )
        else:
            message = (
                f"胜率存在差异 (期望: {expected_wr:.2f}%, "
                f"实际: {actual_wr:.2f}%, 差异: {difference:.2f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=float(expected_wr),
            actual=float(actual_wr),
            difference=float(difference),
            severity=severity,
            details={
                "expected_win_rate": float(expected_wr),
                "actual_win_rate": float(actual_wr),
                "difference": float(difference),
            },
        )

    def _extract_win_rate(self, data: Dict[str, Any]) -> Optional[float]:
        """提取胜率"""
        if not isinstance(data, dict):
            return None

        for key in ["win_rate", "Win Rate [%]", "win_rate_pct"]:
            if key in data:
                value = data[key]
                if isinstance(value, (int, float)):
                    return float(value)

        # 尝试从胜负次数计算
        win_trades = data.get("win_trades") or data.get("# Wins")
        total_trades = data.get("total_trades") or data.get("# Trades")

        if win_trades is not None and total_trades is not None:
            try:
                return (float(win_trades) / float(total_trades)) * 100
            except (ValueError, ZeroDivisionError):
                pass

        return None


class ProfitFactorValidator(BaseValidator):
    """
    盈利因子验证器
    验证盈利因子计算的一致性
    """

    name = "ProfitFactorValidator"
    description = "验证盈利因子计算一致性"
    default_threshold = 0.1  # 10% 容差

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证盈利因子

        Args:
            expected: 期望结果
            actual: 实际结果
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_pf = self._extract_profit_factor(expected)
        actual_pf = self._extract_profit_factor(actual)

        if expected_pf is None or actual_pf is None:
            return self.create_result(
                passed=False,
                message="盈利因子数据缺失",
                severity=ValidationSeverity.CRITICAL,
            )

        difference = abs(expected_pf - actual_pf)
        difference_pct = abs(difference / expected_pf) if expected_pf != 0 else 0

        passed = difference_pct <= self.threshold

        severity = self.determine_severity(difference_pct)

        if passed:
            message = (
                f"盈利因子验证通过 (期望: {expected_pf:.4f}, 实际: {actual_pf:.4f})"
            )
        else:
            message = (
                f"盈利因子存在差异 (期望: {expected_pf:.4f}, "
                f"实际: {actual_pf:.4f}, 差异: {difference_pct*100:.2f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=float(expected_pf),
            actual=float(actual_pf),
            difference=float(difference),
            severity=severity,
            details={
                "expected_profit_factor": float(expected_pf),
                "actual_profit_factor": float(actual_pf),
                "difference": float(difference),
                "difference_pct": float(difference_pct),
            },
        )

    def _extract_profit_factor(self, data: Dict[str, Any]) -> Optional[float]:
        """提取盈利因子"""
        if not isinstance(data, dict):
            return None

        for key in ["profit_factor", "Profit Factor", "pf"]:
            if key in data:
                value = data[key]
                if isinstance(value, (int, float)):
                    return float(value)
        return None


# 注册验证器
register_validator("sharpe_ratio", SharpeRatioValidator)
register_validator("max_drawdown", MaxDrawdownValidator)
register_validator("win_rate", WinRateValidator)
register_validator("profit_factor", ProfitFactorValidator)
