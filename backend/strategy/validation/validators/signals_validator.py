"""
交易信号验证器
用于验证回测结果中的交易信号生成准确性
"""

from typing import Any, Dict, List, Optional, Union
import numpy as np
import pandas as pd

from ..core.base import BaseValidator, ValidationResult, ValidationSeverity
from ..core.registry import register_validator


class SignalCountValidator(BaseValidator):
    """
    信号数量验证器
    验证交易信号的数量是否一致
    """

    name = "SignalCountValidator"
    description = "验证交易信号数量一致性"
    default_threshold = 0  # 信号数量必须完全一致

    def validate(
        self,
        expected: Union[Dict, List, pd.Series, np.ndarray],
        actual: Union[Dict, List, pd.Series, np.ndarray],
        **kwargs
    ) -> ValidationResult:
        """
        验证信号数量

        Args:
            expected: 期望信号数据
            actual: 实际信号数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_count = self._count_signals(expected)
        actual_count = self._count_signals(actual)

        if expected_count is None or actual_count is None:
            return self.create_result(
                passed=False,
                message="信号数据格式错误，无法统计数量",
                severity=ValidationSeverity.CRITICAL,
            )

        difference = abs(expected_count - actual_count)
        passed = difference <= self.threshold

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = f"信号数量验证通过 (期望: {expected_count}, 实际: {actual_count})"
        else:
            message = f"信号数量不一致 (期望: {expected_count}, 实际: {actual_count}, 差异: {difference})"

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

    def _count_signals(self, data) -> Optional[int]:
        """统计信号数量"""
        try:
            if isinstance(data, dict):
                # 尝试不同的键
                for key in ["signals", "entries", "exits", "trades"]:
                    if key in data:
                        signals = data[key]
                        if isinstance(signals, (list, np.ndarray, pd.Series)):
                            return len(signals)
                        elif isinstance(signals, pd.DataFrame):
                            return len(signals)
                # 如果没有找到，尝试统计所有布尔值为True的数量
                count = 0
                for key in ["entries", "exits", "long_entries", "short_entries"]:
                    if key in data:
                        signals = data[key]
                        if isinstance(signals, (np.ndarray, pd.Series)):
                            count += np.sum(signals)
                        elif isinstance(signals, list):
                            count += sum(1 for s in signals if s)
                return int(count) if count > 0 else None

            elif isinstance(data, (list, np.ndarray, pd.Series)):
                return len(data)

            return None
        except Exception:
            return None


class SignalTimingValidator(BaseValidator):
    """
    信号时间验证器
    验证交易信号的时间戳是否一致
    """

    name = "SignalTimingValidator"
    description = "验证交易信号时间戳一致性"
    default_threshold = 1  # 允许1个时间单位的偏差

    def validate(
        self,
        expected: Union[pd.DataFrame, pd.Series, Dict, List],
        actual: Union[pd.DataFrame, pd.Series, Dict, List],
        **kwargs
    ) -> ValidationResult:
        """
        验证信号时间

        Args:
            expected: 期望信号数据（包含时间戳）
            actual: 实际信号数据（包含时间戳）
            **kwargs: 额外参数，可包含 time_tolerance

        Returns:
            ValidationResult: 验证结果
        """
        tolerance = kwargs.get("time_tolerance", self.threshold)

        expected_times = self._extract_timestamps(expected)
        actual_times = self._extract_timestamps(actual)

        if expected_times is None or actual_times is None:
            return self.create_result(
                passed=False,
                message="信号时间数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 比较时间戳
        matched = 0
        unmatched_expected = []
        unmatched_actual = []

        for exp_time in expected_times:
            # 查找最近的实际时间
            found = False
            for act_time in actual_times:
                if abs((exp_time - act_time).total_seconds()) <= tolerance * 60:  # 转换为秒
                    matched += 1
                    found = True
                    break
            if not found:
                unmatched_expected.append(exp_time)

        for act_time in actual_times:
            found = False
            for exp_time in expected_times:
                if abs((exp_time - act_time).total_seconds()) <= tolerance * 60:
                    found = True
                    break
            if not found:
                unmatched_actual.append(act_time)

        total_expected = len(expected_times)
        match_rate = matched / total_expected if total_expected > 0 else 0

        passed = match_rate >= 0.95 and len(unmatched_actual) <= max(1, total_expected * 0.05)

        severity = ValidationSeverity.INFO if passed else ValidationSeverity.ERROR

        if passed:
            message = f"信号时间验证通过 (匹配率: {match_rate*100:.2f}%)"
        else:
            message = (
                f"信号时间存在差异 (匹配: {matched}/{total_expected}, "
                f"未匹配期望: {len(unmatched_expected)}, 未匹配实际: {len(unmatched_actual)})"
            )

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"{total_expected} 个信号",
            actual=f"{len(actual_times)} 个信号",
            severity=severity,
            details={
                "expected_count": total_expected,
                "actual_count": len(actual_times),
                "matched": matched,
                "match_rate": match_rate,
                "unmatched_expected": len(unmatched_expected),
                "unmatched_actual": len(unmatched_actual),
                "time_tolerance_minutes": tolerance,
            },
        )

    def _extract_timestamps(self, data) -> Optional[List[pd.Timestamp]]:
        """提取时间戳列表"""
        try:
            timestamps = []

            if isinstance(data, pd.DataFrame):
                if "timestamp" in data.columns:
                    return pd.to_datetime(data["timestamp"]).tolist()
                elif "datetime" in data.columns:
                    return pd.to_datetime(data["datetime"]).tolist()
                elif isinstance(data.index, pd.DatetimeIndex):
                    return data.index.tolist()

            elif isinstance(data, pd.Series):
                if isinstance(data.index, pd.DatetimeIndex):
                    return data.index.tolist()
                else:
                    return pd.to_datetime(data).tolist()

            elif isinstance(data, dict):
                for key in ["timestamps", "datetime", "time", "date"]:
                    if key in data:
                        return pd.to_datetime(data[key]).tolist()

                # 尝试从信号数据中提取
                for key in ["signals", "entries", "exits", "trades"]:
                    if key in data and isinstance(data[key], pd.DataFrame):
                        df = data[key]
                        if "timestamp" in df.columns:
                            return pd.to_datetime(df["timestamp"]).tolist()
                        elif isinstance(df.index, pd.DatetimeIndex):
                            return df.index.tolist()

            elif isinstance(data, list):
                # 假设是时间戳列表
                return pd.to_datetime(data).tolist()

            return timestamps if timestamps else None
        except Exception:
            return None


class SignalTypeValidator(BaseValidator):
    """
    信号类型验证器
    验证交易信号的类型（买入/卖出）是否一致
    """

    name = "SignalTypeValidator"
    description = "验证交易信号类型一致性"
    default_threshold = 0.02  # 允许2%的信号类型不一致

    def validate(
        self,
        expected: Union[Dict, pd.DataFrame, pd.Series],
        actual: Union[Dict, pd.DataFrame, pd.Series],
        **kwargs
    ) -> ValidationResult:
        """
        验证信号类型

        Args:
            expected: 期望信号数据
            actual: 实际信号数据
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_types = self._extract_signal_types(expected)
        actual_types = self._extract_signal_types(actual)

        if expected_types is None or actual_types is None:
            return self.create_result(
                passed=False,
                message="信号类型数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 对齐并比较
        min_len = min(len(expected_types), len(actual_types))
        if min_len == 0:
            return self.create_result(
                passed=len(expected_types) == len(actual_types),
                message="信号类型列表为空",
                severity=ValidationSeverity.WARNING,
            )

        mismatches = sum(
            1 for i in range(min_len) if expected_types[i] != actual_types[i]
        )
        mismatch_rate = mismatches / min_len

        passed = mismatch_rate <= self.threshold

        severity = self.determine_severity(mismatch_rate)

        if passed:
            message = f"信号类型验证通过 (一致率: {(1-mismatch_rate)*100:.2f}%)"
        else:
            message = f"信号类型存在差异 (不一致: {mismatches}/{min_len}, 不一致率: {mismatch_rate*100:.2f}%)"

        return self.create_result(
            passed=passed,
            message=message,
            expected=f"{len(expected_types)} 个信号",
            actual=f"{len(actual_types)} 个信号",
            difference=float(mismatch_rate),
            severity=severity,
            details={
                "expected_count": len(expected_types),
                "actual_count": len(actual_types),
                "mismatches": mismatches,
                "mismatch_rate": mismatch_rate,
                "expected_buy_count": sum(1 for t in expected_types if t in ["buy", "long", 1, True]),
                "expected_sell_count": sum(1 for t in expected_types if t in ["sell", "short", -1, False]),
                "actual_buy_count": sum(1 for t in actual_types if t in ["buy", "long", 1, True]),
                "actual_sell_count": sum(1 for t in actual_types if t in ["sell", "short", -1, False]),
            },
        )

    def _extract_signal_types(self, data) -> Optional[List[str]]:
        """提取信号类型列表"""
        try:
            if isinstance(data, dict):
                # 尝试不同的键
                for key in ["signal_types", "types", "directions", "actions"]:
                    if key in data:
                        return [str(t).lower() for t in data[key]]

                # 尝试从entries/exits推断
                types = []
                if "entries" in data and "exits" in data:
                    entries = data["entries"]
                    exits = data["exits"]
                    if isinstance(entries, (np.ndarray, pd.Series, list)):
                        for i, e in enumerate(entries):
                            if e:
                                types.append("entry")
                            elif exits[i] if i < len(exits) else False:
                                types.append("exit")
                return types if types else None

            elif isinstance(data, pd.DataFrame):
                for col in ["type", "signal_type", "direction", "action"]:
                    if col in data.columns:
                        return [str(t).lower() for t in data[col]]

            elif isinstance(data, pd.Series):
                return [str(t).lower() for t in data]

            return None
        except Exception:
            return None


class SignalPriceValidator(BaseValidator):
    """
    信号价格验证器
    验证交易信号触发价格是否一致
    """

    name = "SignalPriceValidator"
    description = "验证交易信号触发价格一致性"
    default_threshold = 0.001  # 0.1% 价格容差

    def validate(
        self,
        expected: Union[Dict, pd.DataFrame],
        actual: Union[Dict, pd.DataFrame],
        **kwargs
    ) -> ValidationResult:
        """
        验证信号价格

        Args:
            expected: 期望信号数据（包含价格）
            actual: 实际信号数据（包含价格）
            **kwargs: 额外参数

        Returns:
            ValidationResult: 验证结果
        """
        expected_prices = self._extract_prices(expected)
        actual_prices = self._extract_prices(actual)

        if expected_prices is None or actual_prices is None:
            return self.create_result(
                passed=False,
                message="信号价格数据缺失或格式错误",
                severity=ValidationSeverity.CRITICAL,
            )

        # 对齐并比较价格
        min_len = min(len(expected_prices), len(actual_prices))
        if min_len == 0:
            return self.create_result(
                passed=len(expected_prices) == len(actual_prices),
                message="信号价格列表为空",
                severity=ValidationSeverity.WARNING,
            )

        price_diffs = []
        price_diff_pcts = []

        for i in range(min_len):
            exp_price = expected_prices[i]
            act_price = actual_prices[i]

            if exp_price and act_price and exp_price != 0:
                diff = abs(exp_price - act_price)
                diff_pct = diff / exp_price
                price_diffs.append(diff)
                price_diff_pcts.append(diff_pct)

        if not price_diffs:
            return self.create_result(
                passed=True,
                message="信号价格验证通过（无有效价格对比）",
                severity=ValidationSeverity.INFO,
            )

        max_diff_pct = max(price_diff_pcts)
        mean_diff_pct = sum(price_diff_pcts) / len(price_diff_pcts)

        passed = max_diff_pct <= self.threshold

        severity = self.determine_severity(max_diff_pct)

        if passed:
            message = f"信号价格验证通过 (最大偏差: {max_diff_pct*100:.4f}%)"
        else:
            message = f"信号价格存在差异 (最大偏差: {max_diff_pct*100:.4f}%, 平均偏差: {mean_diff_pct*100:.4f}%)"

        return self.create_result(
            passed=passed,
            message=message,
            severity=severity,
            details={
                "compared_count": len(price_diffs),
                "max_price_diff_pct": max_diff_pct,
                "mean_price_diff_pct": mean_diff_pct,
                "max_price_diff": max(price_diffs),
                "mean_price_diff": sum(price_diffs) / len(price_diffs),
            },
        )

    def _extract_prices(self, data) -> Optional[List[float]]:
        """提取价格列表"""
        try:
            if isinstance(data, dict):
                for key in ["prices", "signal_prices", "entry_prices", "exit_prices"]:
                    if key in data:
                        prices = data[key]
                        if isinstance(prices, (list, np.ndarray, pd.Series)):
                            return [float(p) for p in prices if p is not None]

                # 尝试从DataFrame中提取
                for key in ["signals", "trades", "entries", "exits"]:
                    if key in data and isinstance(data[key], pd.DataFrame):
                        df = data[key]
                        for col in ["price", "entry_price", "exit_price", "signal_price"]:
                            if col in df.columns:
                                return df[col].dropna().astype(float).tolist()

            elif isinstance(data, pd.DataFrame):
                for col in ["price", "entry_price", "exit_price", "signal_price"]:
                    if col in data.columns:
                        return data[col].dropna().astype(float).tolist()

            return None
        except Exception:
            return None


# 注册验证器
register_validator("signal_count", SignalCountValidator)
register_validator("signal_timing", SignalTimingValidator)
register_validator("signal_type", SignalTypeValidator)
register_validator("signal_price", SignalPriceValidator)
