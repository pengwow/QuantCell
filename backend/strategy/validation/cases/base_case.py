"""
验证案例基类
定义验证案例的标准接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime

import numpy as np
import pandas as pd

from ..core.base import ValidationResult


@dataclass
class CaseResult:
    """
    案例验证结果
    """

    case_name: str
    passed: bool
    results: List[ValidationResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "case_name": self.case_name,
            "passed": self.passed,
            "summary": self.summary,
            "execution_time": self.execution_time,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "results": [r.to_dict() for r in self.results],
        }


class ValidationCase(ABC):
    """
    验证案例基类

    所有验证案例都需要继承此类
    """

    name: str = "BaseCase"
    description: str = "基础验证案例"

    def __init__(self):
        self.expected_results: Optional[Dict[str, Any]] = None
        self.actual_results: Optional[Dict[str, Any]] = None

    @abstractmethod
    def generate_expected_results(self) -> Dict[str, Any]:
        """
        生成期望结果（已知正确的结果）

        Returns:
            Dict[str, Any]: 期望结果
        """
        pass

    @abstractmethod
    def generate_actual_results(self) -> Dict[str, Any]:
        """
        生成实际结果（待验证的结果）

        Returns:
            Dict[str, Any]: 实际结果
        """
        pass

    @abstractmethod
    def get_validation_config(self) -> Dict[str, Any]:
        """
        获取验证配置

        Returns:
            Dict[str, Any]: 验证配置
        """
        pass

    def setup(self):
        """
        设置案例环境
        """
        pass

    def teardown(self):
        """
        清理案例环境
        """
        pass

    def run(self, validator) -> CaseResult:
        """
        执行验证案例

        Args:
            validator: 验证器实例

        Returns:
            CaseResult: 案例验证结果
        """
        import time

        start_time = time.time()

        try:
            # 设置环境
            self.setup()

            # 生成结果
            self.expected_results = self.generate_expected_results()
            self.actual_results = self.generate_actual_results()

            # 执行验证
            validation_results = validator.validate(
                self.expected_results,
                self.actual_results,
            )

            # 判断是否通过
            passed = all(r.passed for r in validation_results)

            execution_time = time.time() - start_time

            return CaseResult(
                case_name=self.name,
                passed=passed,
                results=validation_results,
                execution_time=execution_time,
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return CaseResult(
                case_name=self.name,
                passed=False,
                execution_time=execution_time,
                error_message=str(e),
            )

        finally:
            self.teardown()


def generate_sample_data(
    start_date: str = "2023-01-01",
    periods: int = 100,
    trend: str = "up",
    volatility: float = 0.02,
) -> pd.DataFrame:
    """
    生成示例K线数据

    Args:
        start_date: 开始日期
        periods: 数据点数量
        trend: 趋势方向 (up, down, sideways)
        volatility: 波动率

    Returns:
        pd.DataFrame: K线数据
    """
    dates = pd.date_range(start=start_date, periods=periods, freq="D")

    # 生成价格序列
    np.random.seed(42)  # 固定随机种子以保证可重复性

    if trend == "up":
        trend_component = np.linspace(0, 0.2, periods)
    elif trend == "down":
        trend_component = np.linspace(0, -0.2, periods)
    else:
        trend_component = np.zeros(periods)

    noise = np.random.normal(0, volatility, periods)
    returns = trend_component + noise
    prices = 100 * np.exp(np.cumsum(returns))

    # 生成OHLC数据
    df = pd.DataFrame(index=dates)
    df["Open"] = prices * (1 + np.random.normal(0, 0.005, periods))
    df["High"] = prices * (1 + np.abs(np.random.normal(0, 0.01, periods)))
    df["Low"] = prices * (1 - np.abs(np.random.normal(0, 0.01, periods)))
    df["Close"] = prices
    df["Volume"] = np.random.randint(1000000, 10000000, periods)

    return df
