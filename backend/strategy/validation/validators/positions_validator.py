"""
持仓变化验证器
用于验证回测结果中的持仓变化准确性
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class PositionQuantityValidator(BaseValidator):
    """
    持仓数量验证器
    验证持仓数量的一致性
    """

    name = "PositionQuantityValidator"
    description = "验证持仓数量一致性"
    default_threshold = 0.001  # 0.1% 容差

    def validate(
        self,
        expected: Union[pd.Series, np.ndarray, List, Dict],
        actual: Union[pd.Series, np.ndarray, List, Dict],
        **kwargs
    ) -> ValidationResult:
        """
        验证持仓数量

        Args:
            expected: 期望持仓数据
            actual: 实际持仓数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_pos = self._extract_positions(expected)
        actual_pos = self._extract_positions(actual)

        if expected_pos is None or actual_pos is None:
            return self.create_result(
                passed=False,
                message="持仓数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 检查长度
        if len(expected_pos) != len(actual_pos):
            return self.create_result(
                passed=False,
                message=f"持仓序列长度不一致 (期望: {len(expected_pos)}, 实际: {len(actual_pos)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异统计
        diff = np.abs(expected_pos - actual_pos)
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)

        # 计算相对差异
        non_zero_mask = expected_pos != 0
        if np.any(non_zero_mask):
            rel_diff = np.abs(
                (expected_pos[non_zero_mask] - actual_pos[non_zero_mask])
                / expected_pos[non_zero_mask]
            )
            max_rel_diff = np.max(rel_diff)
            mean_rel_diff = np.mean(rel_diff)
        else:
            max_rel_diff = max_diff
            mean_rel_diff = mean_diff

        # 判断是否通过
        passed = max_rel_diff <= self.threshold

        severity = self.determine_severity(max_rel_diff)

        if passed:
            message = f"持仓数量验证通过 (最大相对差异: {max_rel_diff*100:.4f}%)"
        else:
            message = (
                f"持仓数量存在差异 (最大相对差异: {max_rel_diff*100:.4f}%, "
                f"平均相对差异: {mean_rel_diff*100:.4f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            severity=severity,
            details={
                "sequence_length": len(expected_pos),
                "max_absolute_diff": float(max_diff),
                "mean_absolute_diff": float(mean_diff),
                "max_relative_diff": float(max_rel_diff),
                "mean_relative_diff": float(mean_rel_diff),
                "positions_with_diff": int(np.sum(diff > 0)),
            },
        )

    def _extract_positions(self, data) -> Optional[np.ndarray]:
        """提取持仓数组"""
        try:
            if isinstance(data, dict):
                for key in ["positions", "position", "holdings", "qty"]:
                    if key in data:
                        pos = data[key]
                        if isinstance(pos, (np.ndarray, pd.Series, list)):
                            return np.array(pos, dtype=float)

                # 尝试从DataFrame中提取
                if "positions" in data and isinstance(data["positions"], pd.DataFrame):
                    df = data["positions"]
                    if "quantity" in df.columns:
                        return df["quantity"].values.astype(float)
                    elif "size" in df.columns:
                        return df["size"].values.astype(float)

            elif isinstance(data, (pd.Series, np.ndarray, list)):
                return np.array(data, dtype=float)

            return None
        except Exception:
            return None


class PositionValueValidator(BaseValidator):
    """
    持仓价值验证器
    验证持仓价值的一致性
    """

    name = "PositionValueValidator"
    description = "验证持仓价值一致性"
    default_threshold = 0.01  # 1% 容差

    def validate(
        self,
        expected: Union[pd.Series, np.ndarray, List, Dict],
        actual: Union[pd.Series, np.ndarray, List, Dict],
        **kwargs
    ) -> ValidationResult:
        """
        验证持仓价值

        Args:
            expected: 期望持仓价值数据
            actual: 实际持仓价值数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_value = self._extract_position_values(expected)
        actual_value = self._extract_position_values(actual)

        if expected_value is None or actual_value is None:
            return self.create_result(
                passed=False,
                message="持仓价值数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 检查长度
        if len(expected_value) != len(actual_value):
            return self.create_result(
                passed=False,
                message=f"持仓价值序列长度不一致 (期望: {len(expected_value)}, 实际: {len(actual_value)})",
                severity=ValidationSeverity.ERROR,
            )

        # 计算差异
        diff = np.abs(expected_value - actual_value)
        max_diff = np.max(diff)
        mean_diff = np.mean(diff)

        # 计算相对差异
        non_zero_mask = expected_value != 0
        if np.any(non_zero_mask):
            rel_diff = np.abs(
                (expected_value[non_zero_mask] - actual_value[non_zero_mask])
                / expected_value[non_zero_mask]
            )
            max_rel_diff = np.max(rel_diff)
            mean_rel_diff = np.mean(rel_diff)
        else:
            max_rel_diff = 0.0
            mean_rel_diff = 0.0

        # 判断是否通过
        passed = max_rel_diff <= self.threshold

        severity = self.determine_severity(max_rel_diff)

        if passed:
            message = f"持仓价值验证通过 (最大相对差异: {max_rel_diff*100:.4f}%)"
        else:
            message = (
                f"持仓价值存在差异 (最大相对差异: {max_rel_diff*100:.4f}%, "
                f"平均相对差异: {mean_rel_diff*100:.4f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            severity=severity,
            details={
                "sequence_length": len(expected_value),
                "max_absolute_diff": float(max_diff),
                "mean_absolute_diff": float(mean_diff),
                "max_relative_diff": float(max_rel_diff),
                "mean_relative_diff": float(mean_rel_diff),
            },
        )

    def _extract_position_values(self, data) -> Optional[np.ndarray]:
        """提取持仓价值数组"""
        try:
            if isinstance(data, dict):
                for key in ["position_values", "position_value", "holding_values", "market_values"]:
                    if key in data:
                        values = data[key]
                        if isinstance(values, (np.ndarray, pd.Series, list)):
                            return np.array(values, dtype=float)

                # 尝试从DataFrame中提取
                if "positions" in data and isinstance(data["positions"], pd.DataFrame):
                    df = data["positions"]
                    for col in ["value", "market_value", "position_value"]:
                        if col in df.columns:
                            return df[col].values.astype(float)

                # 尝试从持仓和价格计算
                if "positions" in data and "prices" in data:
                    positions = np.array(data["positions"], dtype=float)
                    prices = np.array(data["prices"], dtype=float)
                    if len(positions) == len(prices):
                        return positions * prices

            elif isinstance(data, (pd.Series, np.ndarray, list)):
                return np.array(data, dtype=float)

            return None
        except Exception:
            return None


class PositionChangeTimingValidator(BaseValidator):
    """
    持仓变化时间验证器
    验证持仓变化的时间点是否一致
    """

    name = "PositionChangeTimingValidator"
    description = "验证持仓变化时间点一致性"
    default_threshold = 1  # 允许1个时间单位的偏差

    def validate(
        self,
        expected: Union[pd.DataFrame, Dict],
        actual: Union[pd.DataFrame, Dict],
        **kwargs
    ) -> ValidationResult:
        """
        验证持仓变化时间

        Args:
            expected: 期望持仓数据（包含时间戳）
            actual: 实际持仓数据（包含时间戳）
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_changes = self._extract_change_times(expected)
        actual_changes = self._extract_change_times(actual)

        if expected_changes is None or actual_changes is None:
            return self.create_result(
                passed=False,
                message="持仓变化时间数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 比较变化时间点
        matched = 0
        for exp_time in expected_changes:
            for act_time in actual_changes:
                if abs((exp_time - act_time).total_seconds()) <= self.threshold * 60:
                    matched += 1
                    break

        total_expected = len(expected_changes)
        match_rate = matched / total_expected if total_expected > 0 else 0

        passed = match_rate >= 0.95

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = f"持仓变化时间验证通过 (匹配率: {match_rate*100:.2f}%)"
        else:
            message = (
                f"持仓变化时间存在差异 (期望变化: {total_expected}, "
                f"实际变化: {len(actual_changes)}, 匹配: {matched})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"{total_expected} 次变化",
            actual=f"{len(actual_changes)} 次变化",
            severity=severity,
            details={
                "expected_changes": total_expected,
                "actual_changes": len(actual_changes),
                "matched": matched,
                "match_rate": match_rate,
            },
        )

    def _extract_change_times(self, data) -> Optional[List[pd.Timestamp]]:
        """提取持仓变化时间列表"""
        try:
            if isinstance(data, dict):
                # 尝试直接获取变化时间
                for key in ["change_times", "position_changes", "trade_times"]:
                    if key in data:
                        return pd.to_datetime(data[key]).tolist()

                # 从持仓序列计算变化点
                if "positions" in data:
                    positions = data["positions"]
                    timestamps = data.get("timestamps") or data.get("datetime")

                    if timestamps is not None and isinstance(positions, (np.ndarray, pd.Series, list)):
                        positions = np.array(positions, dtype=float)
                        timestamps = pd.to_datetime(timestamps)

                        # 找到持仓变化的位置
                        changes = np.diff(positions) != 0
                        change_indices = np.where(changes)[0] + 1

                        return [timestamps[i] for i in change_indices]

                # 从DataFrame中提取
                if "positions" in data and isinstance(data["positions"], pd.DataFrame):
                    df = data["positions"]
                    if isinstance(df.index, pd.DatetimeIndex):
                        # 找到持仓变化的时间点
                        if "quantity" in df.columns:
                            changes = df["quantity"].diff() != 0
                            return df.index[changes].tolist()

            elif isinstance(data, pd.DataFrame):
                if isinstance(data.index, pd.DatetimeIndex):
                    for col in ["position", "quantity", "size"]:
                        if col in data.columns:
                            changes = data[col].diff() != 0
                            return data.index[changes].tolist()

            return None
        except Exception:
            return None


# 注册验证器
register_validator("position_quantity", PositionQuantityValidator)
register_validator("position_value", PositionValueValidator)
register_validator("position_change_timing", PositionChangeTimingValidator)
