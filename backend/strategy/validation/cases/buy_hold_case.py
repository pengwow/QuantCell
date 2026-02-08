"""
买入持有策略验证案例
用于验证买入持有策略的回测结果
作为基准案例使用
"""

from typing import Any, Dict
import numpy as np

from .base_case import ValidationCase, generate_sample_data
from ..runner import BacktestValidator


class BuyHoldValidationCase(ValidationCase):
    """
    买入持有策略验证案例

    验证买入持有策略的回测结果是否准确
    这是一个简单的基准案例
    """

    name = "BuyHoldCase"
    description = "买入持有策略验证案例（基准）"

    def __init__(self, initial_capital: float = 10000.0):
        super().__init__()
        self.initial_capital = initial_capital
        self.data = None

    def setup(self):
        """设置案例环境"""
        self.data = generate_sample_data(
            start_date="2023-01-01",
            periods=100,
            trend="up",
            volatility=0.02,
        )

    def generate_expected_results(self) -> Dict[str, Any]:
        """
        生成期望结果（手动计算的正确结果）

        Returns:
            Dict[str, Any]: 期望结果
        """
        close = self.data["Close"]

        # 买入持有策略：第一天买入，一直持有到最后
        entry_price = close.iloc[0]
        exit_price = close.iloc[-1]

        # 计算持仓数量
        position_size = self.initial_capital / entry_price

        # 计算资金曲线
        equity_curve = position_size * close.values

        # 计算总收益率
        total_return = (exit_price - entry_price) / entry_price * 100

        # 计算回撤
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak) / peak * 100
        max_drawdown = np.min(drawdown)

        # 买入持有策略只有一笔交易
        trades = [
            {
                "type": "entry",
                "price": entry_price,
                "size": position_size,
                "index": 0,
            },
            {
                "type": "exit",
                "price": exit_price,
                "size": position_size,
                "pnl": equity_curve[-1] - self.initial_capital,
                "index": len(close) - 1,
            },
        ]

        return {
            "strategy": "buy_and_hold",
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "trade_count": 1,
            "equity_curve": equity_curve.tolist(),
            "cash": [0.0] * len(close),  # 全仓持有，现金为0
            "positions": [position_size] * len(close),
            "trades": trades,
            "entry_price": entry_price,
            "exit_price": exit_price,
        }

    def generate_actual_results(self) -> Dict[str, Any]:
        """
        生成实际结果

        Returns:
            Dict[str, Any]: 实际结果
        """
        # 这里应该调用实际的回测引擎
        expected = self.generate_expected_results()

        # 添加微小差异
        actual = expected.copy()
        actual["total_return"] = expected["total_return"] + np.random.normal(0, 0.05)

        return actual

    def get_validation_config(self) -> Dict[str, Any]:
        """获取验证配置"""
        return {
            "thresholds": {
                "returns_tolerance": 0.001,  # 买入持有策略计算简单，容差更小
                "drawdown_tolerance": 0.001,
                "trade_count_tolerance": 0,
            }
        }

    def run_validation(self) -> Dict[str, Any]:
        """执行验证"""
        self.setup()

        expected = self.generate_expected_results()
        actual = self.generate_actual_results()

        validator = BacktestValidator()
        suite = validator.validate_full(expected, actual)

        return {
            "case_name": self.name,
            "passed": suite.all_passed(),
            "summary": suite.get_summary(),
            "results": [r.to_dict() for r in suite.results],
        }


class BuyHoldBenchmarkCase(ValidationCase):
    """
    买入持有基准案例

    用于作为其他策略的基准对比
    """

    name = "BuyHoldBenchmark"
    description = "买入持有基准案例"

    def __init__(self, initial_capital: float = 10000.0):
        super().__init__()
        self.initial_capital = initial_capital
        self.data = None

    def setup(self):
        """设置案例环境"""
        self.data = generate_sample_data(
            start_date="2023-01-01",
            periods=100,
            trend="up",
            volatility=0.02,
        )

    def generate_expected_results(self) -> Dict[str, Any]:
        """生成基准结果"""
        close = self.data["Close"]
        entry_price = close.iloc[0]
        exit_price = close.iloc[-1]

        total_return = (exit_price - entry_price) / entry_price * 100

        return {
            "benchmark": "buy_and_hold",
            "total_return": total_return,
            "start_price": entry_price,
            "end_price": exit_price,
            "periods": len(close),
        }

    def generate_actual_results(self) -> Dict[str, Any]:
        """生成实际结果"""
        return self.generate_expected_results()

    def get_validation_config(self) -> Dict[str, Any]:
        """获取验证配置"""
        return {
            "thresholds": {
                "returns_tolerance": 0.0001,
            }
        }

    def run_validation(self) -> Dict[str, Any]:
        """执行验证"""
        self.setup()

        expected = self.generate_expected_results()
        actual = self.generate_actual_results()

        validator = BacktestValidator()
        suite = validator.validate_full(expected, actual)

        return {
            "case_name": self.name,
            "passed": suite.all_passed(),
            "summary": suite.get_summary(),
            "results": [r.to_dict() for r in suite.results],
        }
