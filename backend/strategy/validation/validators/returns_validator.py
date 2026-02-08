"""
收益率验证器
用于验证回测结果中的收益率计算准确性
"""

from typing import Any, Dict, Optional, Union
import numpy as np
import pandas as pd
from datetime import datetime

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class TotalReturnValidator(BaseValidator):
    """
    总收益率验证器
    验证回测的总收益率计算是否准确
    """

    name = "TotalReturnValidator"
    description = "验证总收益率计算准确性"
    default_threshold = 0.01  # 1% 容差

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证总收益率

        Args:
            expected: 期望结果，包含 'total_return' 或 'total_return_pct'
            actual: 实际结果，包含 'total_return' 或 'total_return_pct'
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        # 提取总收益率
        expected_return = self._extract_return(expected)
        actual_return = self._extract_return(actual)

        # 检查是否为 None
        if expected_return is None or actual_return is None:
            return self.create_result(
                passed=False,
                message="总收益率数据缺失",
                expected=expected_return,
                actual=actual_return,
                severity=ValidationSeverity.CRITICAL,
            )

        # 计算差异
        difference, difference_pct = self.calculate_difference(
            expected_return, actual_return
        )

        # 判断是否通过
        passed = self.check_threshold(difference_pct / 100)  # 转换为小数

        # 确定严重程度
        severity = self.determine_severity(difference_pct / 100)

        # 生成消息
        if passed:
            message = f"总收益率验证通过 (期望: {expected_return:.4f}%, 实际: {actual_return:.4f}%)"
        else:
            message = (
                f"总收益率偏差过大 (期望: {expected_return:.4f}%, "
                f"实际: {actual_return:.4f}%, 差异: {difference_pct:.2f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=expected_return,
            actual=actual_return,
            difference=difference,
            difference_pct=difference_pct,
            severity=severity,
            details={
                "expected_return_pct": expected_return,
                "actual_return_pct": actual_return,
                "absolute_difference": difference,
            },
        )

    def _extract_return(self, data: Dict[str, Any]) -> Optional[float]:
        """
        从数据中提取总收益率

        Args:
            data: 数据字典

        Returns:
            Optional[float]: 总收益率百分比
        """
        if not isinstance(data, dict):
            return None

        # 尝试不同的键名
        for key in ["total_return_pct", "total_return", "Total Return [%]", "Return [%]"]:
            if key in data:
                value = data[key]
                # 如果值已经是百分比形式（大于1），直接返回
                if isinstance(value, (int, float)):
                    return float(value) if abs(value) < 100 else float(value)
                break

        # 尝试从其他字段计算
        if "equity_curve" in data and len(data["equity_curve"]) > 0:
            equity = data["equity_curve"]
            if isinstance(equity, (list, pd.Series, np.ndarray)):
                start_value = equity[0] if isinstance(equity, list) else equity.iloc[0]
                end_value = equity[-1] if isinstance(equity, list) else equity.iloc[-1]
                if start_value and start_value != 0:
                    return ((end_value / start_value) - 1) * 100

        return None


class AnnualizedReturnValidator(BaseValidator):
    """
    年化收益率验证器
    验证年化收益率计算是否准确
    """

    name = "AnnualizedReturnValidator"
    description = "验证年化收益率计算准确性"
    default_threshold = 0.02  # 2% 容差

    def validate(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        **kwargs
    ) -> ValidationResult:
        """
        验证年化收益率

        Args:
            expected: 期望结果
            actual: 实际结果
            **kwargs: 额外参数，可包含 start_date, end_date

        Returns:
            ValidationResult: 验证结果
        """
        expected_annual = self._extract_annual_return(expected)
        actual_annual = self._extract_annual_return(actual)

        if expected_annual is None or actual_annual is None:
            return self.create_result(
                passed=False,
                message="年化收益率数据缺失",
                expected=expected_annual,
                actual=actual_annual,
                severity=ValidationSeverity.CRITICAL,
            )

        difference, difference_pct = self.calculate_difference(
            expected_annual, actual_annual
        )
        passed = self.check_threshold(difference_pct / 100)
        severity = self.determine_severity(difference_pct / 100)

        message = (
            f"年化收益率验证通过 (期望: {expected_annual:.4f}%, 实际: {actual_annual:.4f}%)"
            if passed
            else f"年化收益率偏差过大 (差异: {difference_pct:.2f}%)"
        )

        return self.create_result(
            passed=passed,
            message=message,
            expected=expected_annual,
            actual=actual_annual,
            difference=difference,
            difference_pct=difference_pct,
            severity=severity,
        )

    def _extract_annual_return(self, data: Dict[str, Any]) -> Optional[float]:
        """提取年化收益率"""
        if not isinstance(data, dict):
            return None

        for key in ["annualized_return", "annual_return", "Annualized Return [%]"]:
            if key in data:
                return float(data[key])

        # 尝试从总收益率计算
        total_return = None
        for key in ["total_return_pct", "total_return", "Return [%]"]:
            if key in data:
                total_return = float(data[key])
                break

        if total_return is not None:
            # 获取时间范围
            start_date = data.get("start_date") or data.get("Start")
            end_date = data.get("end_date") or data.get("End")

            if start_date and end_date:
                try:
                    if isinstance(start_date, str):
                        start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                    if isinstance(end_date, str):
                        end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

                    days = (end_date - start_date).days
                    years = days / 365.25

                    if years > 0:
                        # 使用几何平均计算年化收益率
                        total_return_decimal = total_return / 100
                        annual_return = ((1 + total_return_decimal) ** (1 / years) - 1) * 100
                        return annual_return
                except Exception:
                    pass

        return None


class DailyReturnsValidator(BaseValidator):
    """
    日收益率序列验证器
    验证日收益率序列的一致性
    """

    name = "DailyReturnsValidator"
    description = "验证日收益率序列一致性"
    default_threshold = 0.005  # 0.5% 容差

    def validate(
        self,
        expected: Union[pd.Series, np.ndarray, list],
        actual: Union[pd.Series, np.ndarray, list],
        **kwargs
    ) -> ValidationResult:
        """
        验证日收益率序列

        Args:
            expected: 期望的日收益率序列
            actual: 实际的日收益率序列
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        # 转换为 numpy 数组
        expected_arr = self._to_numpy(expected)
        actual_arr = self._to_numpy(actual)

        if expected_arr is None or actual_arr is None:
            return self.create_result(
                passed=False,
                message="日收益率数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 检查长度
        if len(expected_arr) != len(actual_arr):
            return self.create_result(
                passed=False,
                message=f"日收益率序列长度不一致 (期望: {len(expected_arr)}, 实际: {len(actual_arr)})",
                expected=len(expected_arr),
                actual=len(actual_arr),
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异统计
        diff = np.abs(expected_arr - actual_arr)
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)
        diff_pct = np.mean(np.abs((expected_arr - actual_arr) / (expected_arr + 1e-10))) * 100

        # 统计超出阈值的点数
        threshold_count = np.sum(diff > self.threshold)
        threshold_pct = threshold_count / len(expected_arr) * 100

        # 判断是否通过（允许少量点超出阈值）
        passed = threshold_pct < 5 and max_diff < self.threshold * 5

        severity = self.determine_severity(diff_pct / 100)

        if passed:
            message = f"日收益率序列验证通过 (平均差异: {mean_diff:.6f}, 最大差异: {max_diff:.6f})"
        else:
            message = (
                f"日收益率序列存在差异 (超出阈值比例: {threshold_pct:.2f}%, "
                f"最大差异: {max_diff:.6f})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"序列长度: {len(expected_arr)}",
            actual=f"序列长度: {len(actual_arr)}",
            difference=float(mean_diff),
            difference_pct=float(diff_pct),
            severity=severity,
            details={
                "sequence_length": len(expected_arr),
                "max_difference": float(max_diff),
                "mean_difference": float(mean_diff),
                "threshold_exceeded_count": int(threshold_count),
                "threshold_exceeded_pct": float(threshold_pct),
            },
        )

    def _to_numpy(self, data) -> Optional[np.ndarray]:
        """转换为 numpy 数组"""
        try:
            if isinstance(data, pd.Series):
                return data.values
            elif isinstance(data, np.ndarray):
                return data
            elif isinstance(data, list):
                return np.array(data)
            elif isinstance(data, dict) and "daily_returns" in data:
                return np.array(data["daily_returns"])
            return None
        except Exception:
            return None


class CumulativeReturnsValidator(BaseValidator):
    """
    累计收益率曲线验证器
    验证累计收益率曲线的一致性
    """

    name = "CumulativeReturnsValidator"
    description = "验证累计收益率曲线一致性"
    default_threshold = 0.01  # 1% 容差

    def validate(
        self,
        expected: Union[pd.Series, np.ndarray, list],
        actual: Union[pd.Series, np.ndarray, list],
        **kwargs
    ) -> ValidationResult:
        """
        验证累计收益率曲线

        Args:
            expected: 期望的累计收益率曲线
            actual: 实际的累计收益率曲线
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_arr = self._to_numpy(expected)
        actual_arr = self._to_numpy(actual)

        if expected_arr is None or actual_arr is None:
            return self.create_result(
                passed=False,
                message="累计收益率数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 检查长度
        if len(expected_arr) != len(actual_arr):
            return self.create_result(
                passed=False,
                message=f"累计收益率曲线长度不一致 (期望: {len(expected_arr)}, 实际: {len(actual_arr)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异
        diff = np.abs(expected_arr - actual_arr)
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)
        rmse = np.sqrt(np.mean(diff ** 2))

        # 计算相关性
        try:
            correlation = np.corrcoef(expected_arr, actual_arr)[0, 1]
        except Exception:
            correlation = 0.0

        # 判断是否通过
        passed = max_diff < self.threshold * 100 and correlation > 0.99

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = (
                f"累计收益率曲线验证通过 (RMSE: {rmse:.6f}, 相关性: {correlation:.6f})"
            )
        else:
            message = (
                f"累计收益率曲线存在差异 (最大差异: {max_diff:.4f}%, 相关性: {correlation:.4f})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"曲线长度: {len(expected_arr)}",
            actual=f"曲线长度: {len(actual_arr)}",
            difference=float(mean_diff),
            severity=severity,
            details={
                "curve_length": len(expected_arr),
                "max_difference": float(max_diff),
                "mean_difference": float(mean_diff),
                "rmse": float(rmse),
                "correlation": float(correlation),
            },
        )

    def _to_numpy(self, data) -> Optional[np.ndarray]:
        """转换为 numpy 数组"""
        try:
            if isinstance(data, pd.Series):
                return data.values
            elif isinstance(data, np.ndarray):
                return data
            elif isinstance(data, list):
                return np.array(data)
            elif isinstance(data, dict):
                # 尝试从 equity_curve 计算累计收益率
                if "equity_curve" in data:
                    equity = np.array(data["equity_curve"])
                    if len(equity) > 0 and equity[0] != 0:
                        return (equity / equity[0] - 1) * 100
            return None
        except Exception:
            return None


# 注册验证器
register_validator("total_return", TotalReturnValidator)
register_validator("annualized_return", AnnualizedReturnValidator)
register_validator("daily_returns", DailyReturnsValidator)
register_validator("cumulative_returns", CumulativeReturnsValidator)
