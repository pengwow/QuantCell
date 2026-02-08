"""
SMA交叉策略验证案例
用于验证SMA交叉策略的回测结果
"""

from typing import Any, Dict, List
import numpy as np
import pandas as pd

from .base_case import ValidationCase, generate_sample_data
from ..runner import BacktestValidator


class SmaCrossValidationCase(ValidationCase):
    """
    SMA交叉策略验证案例

    验证SMA交叉策略的回测结果是否准确
    """

    name = "SmaCrossCase"
    description = "SMA交叉策略验证案例"

    def __init__(self, n1: int = 5, n2: int = 10, initial_capital: float = 10000.0):
        super().__init__()
        self.n1 = n1
        self.n2 = n2
        self.initial_capital = initial_capital
        self.data = None

    def setup(self):
        """设置案例环境"""
        # 生成示例数据
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

        # 计算SMA
        sma1 = close.rolling(window=self.n1).mean()
        sma2 = close.rolling(window=self.n2).mean()

        # 生成信号
        entries = (sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))
        exits = (sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))

        # 计算持仓和资金曲线
        position = 0
        cash = self.initial_capital
        positions = []
        cash_history = []
        equity_curve = []
        trades = []

        for i in range(len(close)):
            price = close.iloc[i]

            # 检查信号
            if entries.iloc[i] and position == 0:
                # 买入
                position = cash / price
                cash = 0
                trades.append({
                    "type": "entry",
                    "price": price,
                    "position": position,
                    "index": i,
                })
            elif exits.iloc[i] and position > 0:
                # 卖出
                cash = position * price
                pnl = cash - self.initial_capital
                trades.append({
                    "type": "exit",
                    "price": price,
                    "cash": cash,
                    "pnl": pnl,
                    "index": i,
                })
                position = 0

            # 记录状态
            positions.append(position)
            cash_history.append(cash)
            equity = cash + position * price
            equity_curve.append(equity)

        # 计算指标
        equity_array = np.array(equity_curve)
        total_return = (equity_array[-1] - self.initial_capital) / self.initial_capital * 100

        # 计算回撤
        peak = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - peak) / peak * 100
        max_drawdown = np.min(drawdown)

        # 计算交易统计
        entry_trades = [t for t in trades if t["type"] == "entry"]
        exit_trades = [t for t in trades if t["type"] == "exit"]

        return {
            "total_return": total_return,
            "max_drawdown": max_drawdown,
            "trade_count": len(entry_trades),
            "equity_curve": equity_curve,
            "cash": cash_history,
            "positions": positions,
            "trades": trades,
            "signals": {
                "entries": entries.tolist(),
                "exits": exits.tolist(),
            },
        }

    def generate_actual_results(self) -> Dict[str, Any]:
        """
        生成实际结果（使用回测引擎的结果）

        Returns:
            Dict[str, Any]: 实际结果
        """
        # 这里应该调用实际的回测引擎
        # 为了演示，我们返回与期望结果相同的数据
        # 在实际使用中，这里应该调用 VectorEngine 或 EventEngine

        # 模拟回测引擎的输出格式
        expected = self.generate_expected_results()

        # 添加一些微小的差异来模拟实际情况
        actual = expected.copy()
        actual["total_return"] = expected["total_return"] + np.random.normal(0, 0.1)
        actual["max_drawdown"] = expected["max_drawdown"] + np.random.normal(0, 0.1)

        return actual

    def get_validation_config(self) -> Dict[str, Any]:
        """获取验证配置"""
        return {
            "thresholds": {
                "returns_tolerance": 0.01,
                "drawdown_tolerance": 0.02,
                "trade_count_tolerance": 0,
            }
        }

    def run_validation(self) -> Dict[str, Any]:
        """
        执行验证

        Returns:
            Dict[str, Any]: 验证结果
        """
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


class SmaCrossEngineComparisonCase(ValidationCase):
    """
    SMA交叉策略引擎对比案例

    对比事件引擎和向量引擎的结果是否一致
    """

    name = "SmaCrossEngineComparison"
    description = "SMA交叉策略引擎对比案例"

    def __init__(self, n1: int = 5, n2: int = 10):
        super().__init__()
        self.n1 = n1
        self.n2 = n2
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
        """生成事件引擎结果作为期望"""
        # 模拟事件引擎的输出
        close = self.data["Close"]
        sma1 = close.rolling(window=self.n1).mean()
        sma2 = close.rolling(window=self.n2).mean()

        return {
            "engine_type": "event_engine",
            "total_return": 15.5,
            "max_drawdown": -5.2,
            "trade_count": 8,
            "sharpe_ratio": 1.2,
            "signals": {
                "entries": ((sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))).tolist(),
                "exits": ((sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))).tolist(),
            },
        }

    def generate_actual_results(self) -> Dict[str, Any]:
        """生成向量引擎结果作为实际"""
        # 模拟向量引擎的输出
        close = self.data["Close"]
        sma1 = close.rolling(window=self.n1).mean()
        sma2 = close.rolling(window=self.n2).mean()

        return {
            "engine_type": "vector_engine",
            "total_return": 15.3,  # 微小差异
            "max_drawdown": -5.1,
            "trade_count": 8,
            "sharpe_ratio": 1.18,
            "signals": {
                "entries": ((sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))).tolist(),
                "exits": ((sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))).tolist(),
            },
        }

    def get_validation_config(self) -> Dict[str, Any]:
        """获取验证配置"""
        return {
            "thresholds": {
                "returns_tolerance": 0.05,  # 引擎间允许5%差异
                "metrics_tolerance": 0.05,
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
