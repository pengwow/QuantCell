"""
交易记录验证器
用于验证回测结果中的交易记录准确性
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class TradeCountValidator(BaseValidator):
    """
    交易数量验证器
    验证交易记录的数量是否一致
    """

    name = "TradeCountValidator"
    description = "验证交易记录数量一致性"
    default_threshold = 0  # 交易数量必须完全一致

    def validate(
        self,
        expected: Union[Dict, pd.DataFrame, List],
        actual: Union[Dict, pd.DataFrame, List],
        **kwargs
    ) -> ValidationResult:
        """
        验证交易数量

        Args:
            expected: 期望交易数据
            actual: 实际交易数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_count = self._count_trades(expected)
        actual_count = self._count_trades(actual)

        if expected_count is None or actual_count is None:
            return self.create_result(
                passed=False,
                message="交易数据格式错误，无法统计数量",
                severity=ValidationSeverity.CRITICAL,
            )

        difference = abs(expected_count - actual_count)
        passed = difference <= self.threshold

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = f"交易数量验证通过 (期望: {expected_count}, 实际: {actual_count})"
        else:
            message = f"交易数量不一致 (期望: {expected_count}, 实际: {actual_count}, 差异: {difference})"

        return self.create_result(
            passed=passed,
            message=message,
            expected=expected_count,
            actual=actual_count,
            difference=float(difference),
            severity=severity,
            details={
                "expected_count": expected_count,
                "actual_count": actual_count,
                "difference": difference,
            },
        )

    def _count_trades(self, data) -> Optional[int]:
        """统计交易数量"""
        try:
            if isinstance(data, dict):
                if "trades" in data:
                    trades = data["trades"]
                    if isinstance(trades, (list, np.ndarray, pd.Series)):
                        return len(trades)
                    elif isinstance(trades, pd.DataFrame):
                        return len(trades)

                # 尝试其他键名
                for key in ["trade_count", "total_trades", "# Trades"]:
                    if key in data:
                        return int(data[key])

            elif isinstance(data, (list, np.ndarray, pd.Series)):
                return len(data)

            elif isinstance(data, pd.DataFrame):
                return len(data)

            return None
        except Exception:
            return None


class TradePnLValidator(BaseValidator):
    """
    交易盈亏验证器
    验证交易盈亏计算的一致性
    """

    name = "TradePnLValidator"
    description = "验证交易盈亏计算一致性"
    default_threshold = 0.01  # 1% 容差

    def validate(
        self,
        expected: Union[Dict, pd.DataFrame, List],
        actual: Union[Dict, pd.DataFrame, List],
        **kwargs
    ) -> ValidationResult:
        """
        验证交易盈亏

        Args:
            expected: 期望交易数据
            actual: 实际交易数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_pnl = self._extract_pnl(expected)
        actual_pnl = self._extract_pnl(actual)

        if expected_pnl is None or actual_pnl is None:
            return self.create_result(
                passed=False,
                message="交易盈亏数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 计算总盈亏
        expected_total = np.sum(expected_pnl)
        actual_total = np.sum(actual_pnl)

        # 计算差异
        total_diff = abs(expected_total - actual_total)
        total_diff_pct = abs(total_diff / expected_total) if expected_total != 0 else 0

        # 计算盈亏序列的差异（如果长度相同）
        if len(expected_pnl) == len(actual_pnl):
            pnl_diff = np.abs(expected_pnl - actual_pnl)
            max_pnl_diff = np.max(pnl_diff)
            mean_pnl_diff = np.mean(pnl_diff)

            # 计算相对差异
            non_zero_mask = expected_pnl != 0
            if np.any(non_zero_mask):
                rel_diff = np.abs(
                    (expected_pnl[non_zero_mask] - actual_pnl[non_zero_mask])
                    / expected_pnl[non_zero_mask]
                )
                max_rel_diff = np.max(rel_diff)
            else:
                max_rel_diff = 0.0
        else:
            max_pnl_diff = total_diff
            mean_pnl_diff = total_diff
            max_rel_diff = total_diff_pct

        # 判断是否通过
        passed = total_diff_pct <= self.threshold

        severity = self.determine_severity(total_diff_pct)

        if passed:
            message = (
                f"交易盈亏验证通过 (期望总盈亏: {expected_total:.2f}, "
                f"实际总盈亏: {actual_total:.2f})"
            )
        else:
            message = (
                f"交易盈亏存在差异 (期望总盈亏: {expected_total:.2f}, "
                f"实际总盈亏: {actual_total:.2f}, 差异: {total_diff_pct*100:.2f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=float(expected_total),
            actual=float(actual_total),
            difference=float(total_diff),
            severity=severity,
            details={
                "expected_total_pnl": float(expected_total),
                "actual_total_pnl": float(actual_total),
                "total_diff": float(total_diff),
                "total_diff_pct": float(total_diff_pct),
                "max_pnl_diff": float(max_pnl_diff),
                "mean_pnl_diff": float(mean_pnl_diff),
                "max_relative_diff": float(max_rel_diff),
                "trade_count": len(expected_pnl),
            },
        )

    def _extract_pnl(self, data) -> Optional[np.ndarray]:
        """提取盈亏数组"""
        try:
            if isinstance(data, dict):
                if "trades" in data:
                    trades = data["trades"]
                    if isinstance(trades, pd.DataFrame):
                        for col in ["PnL", "pnl", "profit", "return"]:
                            if col in trades.columns:
                                return trades[col].values.astype(float)
                    elif isinstance(trades, (list, np.ndarray)):
                        # 假设是字典列表
                        pnl_list = []
                        for trade in trades:
                            if isinstance(trade, dict):
                                for key in ["PnL", "pnl", "profit", "return"]:
                                    if key in trade:
                                        pnl_list.append(float(trade[key]))
                                        break
                        return np.array(pnl_list) if pnl_list else None

                # 尝试直接获取盈亏列表
                for key in ["pnl", "PnL", "profits", "returns"]:
                    if key in data:
                        return np.array(data[key], dtype=float)

            elif isinstance(data, pd.DataFrame):
                for col in ["PnL", "pnl", "profit", "return"]:
                    if col in data.columns:
                        return data[col].values.astype(float)

            elif isinstance(data, (list, np.ndarray)):
                # 假设是盈亏值列表
                return np.array(data, dtype=float)

            return None
        except Exception:
            return None


class TradeFeeValidator(BaseValidator):
    """
    交易费用验证器
    验证交易费用计算的一致性
    """

    name = "TradeFeeValidator"
    description = "验证交易费用计算一致性"
    default_threshold = 0.001  # 0.1% 容差

    def validate(
        self,
        expected: Union[Dict, pd.DataFrame, List],
        actual: Union[Dict, pd.DataFrame, List],
        **kwargs
    ) -> ValidationResult:
        """
        验证交易费用

        Args:
            expected: 期望交易数据
            actual: 实际交易数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_fees = self._extract_fees(expected)
        actual_fees = self._extract_fees(actual)

        if expected_fees is None or actual_fees is None:
            return self.create_result(
                passed=False,
                message="交易费用数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 计算总费用
        expected_total = np.sum(expected_fees)
        actual_total = np.sum(actual_fees)

        # 计算差异
        total_diff = abs(expected_total - actual_total)
        total_diff_pct = abs(total_diff / expected_total) if expected_total != 0 else 0

        # 判断是否通过
        passed = total_diff_pct <= self.threshold

        severity = self.determine_severity(total_diff_pct)

        if passed:
            message = (
                f"交易费用验证通过 (期望总费用: {expected_total:.4f}, "
                f"实际总费用: {actual_total:.4f})"
            )
        else:
            message = (
                f"交易费用存在差异 (期望总费用: {expected_total:.4f}, "
                f"实际总费用: {actual_total:.4f}, 差异: {total_diff_pct*100:.4f}%)"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=float(expected_total),
            actual=float(actual_total),
            difference=float(total_diff),
            severity=severity,
            details={
                "expected_total_fees": float(expected_total),
                "actual_total_fees": float(actual_total),
                "total_diff": float(total_diff),
                "total_diff_pct": float(total_diff_pct),
                "trade_count": len(expected_fees),
            },
        )

    def _extract_fees(self, data) -> Optional[np.ndarray]:
        """提取费用数组"""
        try:
            if isinstance(data, dict):
                if "trades" in data:
                    trades = data["trades"]
                    if isinstance(trades, pd.DataFrame):
                        for col in ["fees", "Fees", "commission", "Commission", "fee"]:
                            if col in trades.columns:
                                return trades[col].values.astype(float)
                    elif isinstance(trades, (list, np.ndarray)):
                        fee_list = []
                        for trade in trades:
                            if isinstance(trade, dict):
                                for key in ["fees", "Fees", "commission", "Commission", "fee"]:
                                    if key in trade:
                                        fee_list.append(float(trade[key]))
                                        break
                        return np.array(fee_list) if fee_list else None

                # 尝试直接获取费用列表
                for key in ["fees", "Fees", "total_fees", "commissions"]:
                    if key in data:
                        return np.array(data[key], dtype=float)

            elif isinstance(data, pd.DataFrame):
                for col in ["fees", "Fees", "commission", "Commission", "fee"]:
                    if col in data.columns:
                        return data[col].values.astype(float)

            elif isinstance(data, (list, np.ndarray)):
                return np.array(data, dtype=float)

            return None
        except Exception:
            return None


class TradeTimingValidator(BaseValidator):
    """
    交易时间验证器
    验证交易时间戳的一致性
    """

    name = "TradeTimingValidator"
    description = "验证交易时间戳一致性"
    default_threshold = 1  # 允许1分钟偏差

    def validate(
        self,
        expected: Union[Dict, pd.DataFrame, List],
        actual: Union[Dict, pd.DataFrame, List],
        **kwargs
    ) -> ValidationResult:
        """
        验证交易时间

        Args:
            expected: 期望交易数据
            actual: 实际交易数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_times = self._extract_trade_times(expected)
        actual_times = self._extract_trade_times(actual)

        if expected_times is None or actual_times is None:
            return self.create_result(
                passed=False,
                message="交易时间数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 比较交易时间
        matched = 0
        unmatched_expected = []

        for exp_time in expected_times:
            found = False
            for act_time in actual_times:
                if abs((exp_time - act_time).total_seconds()) <= self.threshold * 60:
                    matched += 1
                    found = True
                    break
            if not found:
                unmatched_expected.append(exp_time)

        total_expected = len(expected_times)
        match_rate = matched / total_expected if total_expected > 0 else 0

        passed = match_rate >= 0.95

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = f"交易时间验证通过 (匹配率: {match_rate*100:.2f}%)"
        else:
            message = (
                f"交易时间存在差异 (期望交易: {total_expected}, "
                f"实际交易: {len(actual_times)}, 匹配: {matched})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"{total_expected} 笔交易",
            actual=f"{len(actual_times)} 笔交易",
            severity=severity,
            details={
                "expected_count": total_expected,
                "actual_count": len(actual_times),
                "matched": matched,
                "match_rate": match_rate,
                "unmatched_count": len(unmatched_expected),
            },
        )

    def _extract_trade_times(self, data) -> Optional[List[pd.Timestamp]]:
        """提取交易时间列表"""
        try:
            if isinstance(data, dict):
                if "trades" in data:
                    trades = data["trades"]
                    if isinstance(trades, pd.DataFrame):
                        for col in ["EntryTime", "ExitTime", "timestamp", "datetime", "time"]:
                            if col in trades.columns:
                                return pd.to_datetime(trades[col]).tolist()
                        if isinstance(trades.index, pd.DatetimeIndex):
                            return trades.index.tolist()
                    elif isinstance(trades, (list, np.ndarray)):
                        times = []
                        for trade in trades:
                            if isinstance(trade, dict):
                                for key in ["EntryTime", "ExitTime", "timestamp", "datetime", "time"]:
                                    if key in trade:
                                        times.append(pd.to_datetime(trade[key]))
                                        break
                        return times if times else None

            elif isinstance(data, pd.DataFrame):
                for col in ["EntryTime", "ExitTime", "timestamp", "datetime", "time"]:
                    if col in data.columns:
                        return pd.to_datetime(data[col]).tolist()
                if isinstance(data.index, pd.DatetimeIndex):
                    return data.index.tolist()

            return None
        except Exception:
            return None


# 注册验证器
register_validator("trade_count", TradeCountValidator)
register_validator("trade_pnl", TradePnLValidator)
register_validator("trade_fee", TradeFeeValidator)
register_validator("trade_timing", TradeTimingValidator)
