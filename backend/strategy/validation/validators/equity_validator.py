"""
资金曲线验证器
用于验证回测结果中的资金曲线准确性
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class EquityCurveValidator(BaseValidator):
    """
    资金曲线验证器
    验证资金曲线的一致性
    """

    name = "EquityCurveValidator"
    description = "验证资金曲线一致性"
    default_threshold = 0.01  # 1% 容差

    def validate(
        self,
        expected: Union[pd.Series, np.ndarray, List, Dict],
        actual: Union[pd.Series, np.ndarray, List, Dict],
        **kwargs
    ) -> ValidationResult:
        """
        验证资金曲线

        Args:
            expected: 期望资金曲线数据
            actual: 实际资金曲线数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_equity = self._extract_equity(expected)
        actual_equity = self._extract_equity(actual)

        if expected_equity is None or actual_equity is None:
            return self.create_result(
                passed=False,
                message="资金曲线数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 检查长度
        if len(expected_equity) != len(actual_equity):
            return self.create_result(
                passed=False,
                message=f"资金曲线长度不一致 (期望: {len(expected_equity)}, 实际: {len(actual_equity)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异统计
        diff = np.abs(expected_equity - actual_equity)
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)
        rmse = np.sqrt(np.mean(diff ** 2))

        # 计算相对差异
        non_zero_mask = expected_equity != 0
        if np.any(non_zero_mask):
            rel_diff = np.abs(
                (expected_equity[non_zero_mask] - actual_equity[non_zero_mask])
                / expected_equity[non_zero_mask]
            )
            max_rel_diff = np.max(rel_diff)
            mean_rel_diff = np.mean(rel_diff)
        else:
            max_rel_diff = 0.0
            mean_rel_diff = 0.0

        # 计算相关性
        try:
            correlation = np.corrcoef(expected_equity, actual_equity)[0, 1]
        except Exception:
            correlation = 0.0

        # 判断是否通过
        passed = max_rel_diff <= self.threshold and correlation > 0.99

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = (
                f"资金曲线验证通过 (最大相对差异: {max_rel_diff*100:.4f}%, "
                f"相关性: {correlation:.6f})"
            )
        else:
            message = (
                f"资金曲线存在差异 (最大相对差异: {max_rel_diff*100:.4f}%, "
                f"相关性: {correlation:.4f}, RMSE: {rmse:.2f})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            severity=severity,
            details={
                "curve_length": len(expected_equity),
                "max_absolute_diff": float(max_diff),
                "mean_absolute_diff": float(mean_diff),
                "max_relative_diff": float(max_rel_diff),
                "mean_relative_diff": float(mean_rel_diff),
                "rmse": float(rmse),
                "correlation": float(correlation),
                "start_value_expected": float(expected_equity[0]),
                "start_value_actual": float(actual_equity[0]),
                "end_value_expected": float(expected_equity[-1]),
                "end_value_actual": float(actual_equity[-1]),
            },
        )

    def _extract_equity(self, data) -> Optional[np.ndarray]:
        """提取资金曲线数组"""
        try:
            if isinstance(data, dict):
                for key in ["equity_curve", "equity", "portfolio_value", "total_value"]:
                    if key in data:
                        equity = data[key]
                        if isinstance(equity, (np.ndarray, pd.Series, list)):
                            return np.array(equity, dtype=float)
                        elif isinstance(equity, pd.DataFrame):
                            if "Equity" in equity.columns:
                                return equity["Equity"].values.astype(float)
                            elif "equity" in equity.columns:
                                return equity["equity"].values.astype(float)

            elif isinstance(data, (pd.Series, np.ndarray, list)):
                return np.array(data, dtype=float)

            elif isinstance(data, pd.DataFrame):
                for col in ["Equity", "equity", "portfolio_value", "total_value"]:
                    if col in data.columns:
                        return data[col].values.astype(float)

            return None
        except Exception:
            return None


class DrawdownValidator(BaseValidator):
    """
    回撤验证器
    验证回撤计算的一致性
    """

    name = "DrawdownValidator"
    description = "验证回撤计算一致性"
    default_threshold = 0.02  # 2% 容差

    def validate(
        self,
        expected: Union[Dict, pd.Series, np.ndarray],
        actual: Union[Dict, pd.Series, np.ndarray],
        **kwargs
    ) -> ValidationResult:
        """
        验证回撤

        Args:
            expected: 期望回撤数据
            actual: 实际回撤数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_dd = self._extract_drawdown(expected)
        actual_dd = self._extract_drawdown(actual)

        if expected_dd is None or actual_dd is None:
            return self.create_result(
                passed=False,
                message="回撤数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 验证最大回撤
        expected_max_dd = np.min(expected_dd)  # 回撤为负值
        actual_max_dd = np.min(actual_dd)

        max_dd_diff = abs(expected_max_dd - actual_max_dd)
        max_dd_diff_pct = abs(max_dd_diff / expected_max_dd) if expected_max_dd != 0 else 0

        # 验证回撤序列
        if len(expected_dd) != len(actual_dd):
            return self.create_result(
                passed=False,
                message=f"回撤序列长度不一致 (期望: {len(expected_dd)}, 实际: {len(actual_dd)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算回撤序列的差异
        dd_diff = np.abs(expected_dd - actual_dd)
        mean_dd_diff = np.mean(dd_diff)
        max_dd_seq_diff = np.max(dd_diff)

        # 计算相关性
        try:
            correlation = np.corrcoef(expected_dd, actual_dd)[0, 1]
        except Exception:
            correlation = 0.0

        # 判断是否通过
        passed = max_dd_diff_pct <= self.threshold and correlation > 0.95

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = (
                f"回撤验证通过 (最大回撤差异: {max_dd_diff_pct*100:.4f}%, "
                f"相关性: {correlation:.4f})"
            )
        else:
            message = (
                f"回撤存在差异 (期望最大回撤: {expected_max_dd:.4f}%, "
                f"实际最大回撤: {actual_max_dd:.4f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"最大回撤: {expected_max_dd:.4f}%",
            actual=f"最大回撤: {actual_max_dd:.4f}%",
            difference=float(max_dd_diff),
            severity=severity,
            details={
                "sequence_length": len(expected_dd),
                "expected_max_drawdown": float(expected_max_dd),
                "actual_max_drawdown": float(actual_max_dd),
                "max_drawdown_diff": float(max_dd_diff),
                "max_drawdown_diff_pct": float(max_dd_diff_pct),
                "mean_drawdown_diff": float(mean_dd_diff),
                "max_sequence_diff": float(max_dd_seq_diff),
                "correlation": float(correlation),
            },
        )

    def _extract_drawdown(self, data) -> Optional[np.ndarray]:
        """提取回撤数组"""
        try:
            if isinstance(data, dict):
                for key in ["drawdown", "drawdowns", "drawdown_pct", "DrawdownPct"]:
                    if key in data:
                        dd = data[key]
                        if isinstance(dd, (np.ndarray, pd.Series, list)):
                            return np.array(dd, dtype=float)

                # 尝试从资金曲线计算回撤
                if "equity_curve" in data:
                    equity = np.array(data["equity_curve"], dtype=float)
                    if len(equity) > 0:
                        peak = np.maximum.accumulate(equity)
                        drawdown = (equity - peak) / peak * 100
                        return drawdown

            elif isinstance(data, (pd.Series, np.ndarray, list)):
                return np.array(data, dtype=float)

            elif isinstance(data, pd.DataFrame):
                for col in ["Drawdown", "drawdown", "DrawdownPct", "drawdown_pct"]:
                    if col in data.columns:
                        return data[col].values.astype(float)

                # 尝试从Equity列计算
                if "Equity" in data.columns:
                    equity = data["Equity"].values.astype(float)
                    peak = np.maximum.accumulate(equity)
                    drawdown = (equity - peak) / peak * 100
                    return drawdown

            return None
        except Exception:
            return None


class CashBalanceValidator(BaseValidator):
    """
    现金余额验证器
    验证现金余额的一致性
    """

    name = "CashBalanceValidator"
    description = "验证现金余额一致性"
    default_threshold = 0.01  # 1% 容差

    def validate(
        self,
        expected: Union[pd.Series, np.ndarray, List, Dict],
        actual: Union[pd.Series, np.ndarray, List, Dict],
        **kwargs
    ) -> ValidationResult:
        """
        验证现金余额

        Args:
            expected: 期望现金余额数据
            actual: 实际现金余额数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_cash = self._extract_cash(expected)
        actual_cash = self._extract_cash(actual)

        if expected_cash is None or actual_cash is None:
            return self.create_result(
                passed=False,
                message="现金余额数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 检查长度
        if len(expected_cash) != len(actual_cash):
            return self.create_result(
                passed=False,
                message=f"现金余额序列长度不一致 (期望: {len(expected_cash)}, 实际: {len(actual_cash)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异统计
        diff = np.abs(expected_cash - actual_cash)
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)

        # 计算相对差异
        non_zero_mask = expected_cash != 0
        if np.any(non_zero_mask):
            rel_diff = np.abs(
                (expected_cash[non_zero_mask] - actual_cash[non_zero_mask])
                / expected_cash[non_zero_mask]
            )
            max_rel_diff = np.max(rel_diff)
            mean_rel_diff = np.mean(rel_diff)
        else:
            max_rel_diff = 0.0
            mean_rel_diff = 0.0

        # 判断是否通过
        passed = max_rel_diff <= self.threshold

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = f"现金余额验证通过 (最大相对差异: {max_rel_diff*100:.4f}%)"
        else:
            message = (
                f"现金余额存在差异 (最大相对差异: {max_rel_diff*100:.4f}%, "
                f"平均相对差异: {mean_rel_diff*100:.4f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            severity=severity,
            details={
                "sequence_length": len(expected_cash),
                "max_absolute_diff": float(max_diff),
                "mean_absolute_diff": float(mean_diff),
                "max_relative_diff": float(max_rel_diff),
                "mean_relative_diff": float(mean_rel_diff),
                "start_balance_expected": float(expected_cash[0]),
                "start_balance_actual": float(actual_cash[0]),
                "end_balance_expected": float(expected_cash[-1]),
                "end_balance_actual": float(actual_cash[-1]),
            },
        )

    def _extract_cash(self, data) -> Optional[np.ndarray]:
        """提取现金余额数组"""
        try:
            if isinstance(data, dict):
                for key in ["cash", "cash_balance", "cash_history", "free_cash"]:
                    if key in data:
                        cash = data[key]
                        if isinstance(cash, (np.ndarray, pd.Series, list)):
                            return np.array(cash, dtype=float)

            elif isinstance(data, (pd.Series, np.ndarray, list)):
                return np.array(data, dtype=float)

            elif isinstance(data, pd.DataFrame):
                for col in ["Cash", "cash", "CashBalance", "cash_balance"]:
                    if col in data.columns:
                        return data[col].values.astype(float)

            return None
        except Exception:
            return None


# 注册验证器
register_validator("equity_curve", EquityCurveValidator)
register_validator("drawdown", DrawdownValidator)
register_validator("cash_balance", CashBalanceValidator)
