"""
验证运行器
用于执行完整的验证流程
"""

from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from .core.base import ValidationSuite, ValidationResult
from .core.registry import registry
from .reports.report_generator import ValidationReporter


class ValidationRunner:
    """
    验证运行器

    用于执行完整的验证流程，包括：
    1. 加载验证套件
    2. 执行验证
    3. 生成报告
    """

    def __init__(self):
        self.reporter = ValidationReporter()
        self.suites: Dict[str, ValidationSuite] = {}

    def create_suite(
        self,
        name: str,
        description: str = "",
        validator_names: Optional[List[str]] = None,
    ) -> ValidationSuite:
        """
        创建验证套件

        Args:
            name: 套件名称
            description: 套件描述
            validator_names: 验证器名称列表，如果为None则使用所有已注册的验证器

        Returns:
            ValidationSuite: 验证套件
        """
        suite = ValidationSuite(name=name, description=description)

        if validator_names is None:
            # 使用所有已注册的验证器
            validator_names = registry.list_validators()

        for validator_name in validator_names:
            try:
                validator = registry.get(validator_name)
                suite.add_validator(validator)
                logger.debug(f"添加验证器到套件: {validator_name}")
            except Exception as e:
                logger.warning(f"无法添加验证器 {validator_name}: {e}")

        self.suites[name] = suite
        return suite

    def run_validation(
        self,
        suite_name: str,
        expected: Any,
        actual: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[ValidationResult]:
        """
        执行验证

        Args:
            suite_name: 套件名称
            expected: 期望值
            actual: 实际值
            context: 上下文信息

        Returns:
            List[ValidationResult]: 验证结果列表
        """
        if suite_name not in self.suites:
            raise ValueError(f"验证套件不存在: {suite_name}")

        suite = self.suites[suite_name]
        logger.info(f"开始执行验证套件: {suite_name}")

        results = suite.run(expected, actual, context)

        logger.info(f"验证套件执行完成: {suite_name}")
        return results

    def run_and_report(
        self,
        suite_name: str,
        expected: Any,
        actual: Any,
        context: Optional[Dict[str, Any]] = None,
        output_dir: Optional[str] = None,
    ) -> ValidationSuite:
        """
        执行验证并生成报告

        Args:
            suite_name: 套件名称
            expected: 期望值
            actual: 实际值
            context: 上下文信息
            output_dir: 报告输出目录

        Returns:
            ValidationSuite: 验证套件
        """
        # 执行验证
        self.run_validation(suite_name, expected, actual, context)

        # 获取套件
        suite = self.suites[suite_name]

        # 生成报告
        self.reporter.quick_report(suite, output_dir)

        return suite

    def get_suite_summary(self, suite_name: str) -> Dict[str, Any]:
        """
        获取验证套件摘要

        Args:
            suite_name: 套件名称

        Returns:
            Dict[str, Any]: 验证摘要
        """
        if suite_name not in self.suites:
            raise ValueError(f"验证套件不存在: {suite_name}")

        return self.suites[suite_name].get_summary()

    def list_suites(self) -> List[str]:
        """
        获取所有验证套件名称

        Returns:
            List[str]: 套件名称列表
        """
        return list(self.suites.keys())


class BacktestValidator:
    """
    回测验证器

    专门用于验证回测结果的便捷类
    """

    def __init__(self):
        self.runner = ValidationRunner()
        self._setup_default_suites()

    def _setup_default_suites(self):
        """设置默认验证套件"""
        # 完整验证套件
        self.runner.create_suite(
            name="full_validation",
            description="完整的回测结果验证",
        )

        # 收益率验证套件
        self.runner.create_suite(
            name="returns_validation",
            description="收益率相关验证",
            validator_names=[
                "total_return",
                "annualized_return",
                "daily_returns",
                "cumulative_returns",
            ],
        )

        # 信号验证套件
        self.runner.create_suite(
            name="signals_validation",
            description="交易信号相关验证",
            validator_names=[
                "signal_count",
                "signal_timing",
                "signal_type",
                "signal_price",
            ],
        )

        # 持仓验证套件
        self.runner.create_suite(
            name="positions_validation",
            description="持仓变化相关验证",
            validator_names=[
                "position_quantity",
                "position_value",
                "position_change_timing",
            ],
        )

        # 资金验证套件
        self.runner.create_suite(
            name="equity_validation",
            description="资金曲线相关验证",
            validator_names=[
                "equity_curve",
                "drawdown",
                "cash_balance",
            ],
        )

        # 交易验证套件
        self.runner.create_suite(
            name="trades_validation",
            description="交易记录相关验证",
            validator_names=[
                "trade_count",
                "trade_pnl",
                "trade_fee",
                "trade_timing",
            ],
        )

        # 指标验证套件
        self.runner.create_suite(
            name="metrics_validation",
            description="绩效指标相关验证",
            validator_names=[
                "sharpe_ratio",
                "max_drawdown",
                "win_rate",
                "profit_factor",
            ],
        )

    def validate_full(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
        output_dir: Optional[str] = None,
    ) -> ValidationSuite:
        """
        执行完整验证

        Args:
            expected: 期望结果
            actual: 实际结果
            output_dir: 报告输出目录

        Returns:
            ValidationSuite: 验证套件
        """
        return self.runner.run_and_report(
            suite_name="full_validation",
            expected=expected,
            actual=actual,
            output_dir=output_dir,
        )

    def validate_returns(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
    ) -> List[ValidationResult]:
        """验证收益率"""
        return self.runner.run_validation(
            suite_name="returns_validation",
            expected=expected,
            actual=actual,
        )

    def validate_signals(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
    ) -> List[ValidationResult]:
        """验证交易信号"""
        return self.runner.run_validation(
            suite_name="signals_validation",
            expected=expected,
            actual=actual,
        )

    def validate_positions(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
    ) -> List[ValidationResult]:
        """验证持仓变化"""
        return self.runner.run_validation(
            suite_name="positions_validation",
            expected=expected,
            actual=actual,
        )

    def validate_equity(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
    ) -> List[ValidationResult]:
        """验证资金曲线"""
        return self.runner.run_validation(
            suite_name="equity_validation",
            expected=expected,
            actual=actual,
        )

    def validate_trades(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
    ) -> List[ValidationResult]:
        """验证交易记录"""
        return self.runner.run_validation(
            suite_name="trades_validation",
            expected=expected,
            actual=actual,
        )

    def validate_metrics(
        self,
        expected: Dict[str, Any],
        actual: Dict[str, Any],
    ) -> List[ValidationResult]:
        """验证绩效指标"""
        return self.runner.run_validation(
            suite_name="metrics_validation",
            expected=expected,
            actual=actual,
        )


def quick_validate(
    expected: Dict[str, Any],
    actual: Dict[str, Any],
    output_dir: Optional[str] = None,
) -> ValidationSuite:
    """
    快速验证函数

    Args:
        expected: 期望结果
        actual: 实际结果
        output_dir: 报告输出目录

    Returns:
        ValidationSuite: 验证套件
    """
    validator = BacktestValidator()
    return validator.validate_full(expected, actual, output_dir)
