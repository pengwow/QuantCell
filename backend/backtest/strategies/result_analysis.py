# 回测结果分析工具
# 用于统一不同回测引擎的结果格式，进行比较和可视化

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, Any, Optional


class BacktestResult:
    """
    回测结果封装类
    统一不同回测引擎的结果格式，提供标准化和比较方法
    """

    def __init__(self, results: Any, engine: str = "native"):
        """
        初始化回测结果

        Args:
            results: 原始回测结果
            engine: 回测引擎名称，如 'native'（自研）
        """
        self.raw_results = results
        self.engine = engine
        self.standardized_results = self.standardize_results()

    def standardize_results(self) -> Dict[str, Any]:
        """
        标准化回测结果

        Returns:
            Dict[str, Any]: 标准化后的回测结果
        """
        # 统一使用自研引擎的结果格式
        return self._standardize_native()

    def _standardize_native(self) -> Dict[str, Any]:
        """
        标准化自研引擎回测结果
        """
        results = self.raw_results

        # 提取关键指标
        standardized = {
            'start_date': results.get('Start'),
            'end_date': results.get('End'),
            'duration': results.get('Duration'),
            'exposure_time_pct': results.get('Exposure Time [%]'),
            'start_value': results.get('Start Value'),
            'end_value': results.get('Equity Final [$]'),
            'total_return_pct': results.get('Return [%]'),
            'buy_hold_return_pct': results.get('Buy & Hold Return [%]'),
            'sharpe_ratio': results.get('Sharpe Ratio'),
            'sortino_ratio': results.get('Sortino Ratio'),
            'calmar_ratio': results.get('Calmar Ratio'),
            'omega_ratio': results.get('Omega Ratio'),
            'max_drawdown_pct': results.get('Max. Drawdown [%]'),
            'avg_drawdown_pct': results.get('Avg. Drawdown [%]'),
            'max_drawdown_duration': results.get('Max. Drawdown Duration'),
            'avg_drawdown_duration': results.get('Avg. Drawdown Duration'),
            'total_trades': results.get('# Trades'),
            'win_rate_pct': results.get('Win Rate [%]'),
            'best_trade_pct': results.get('Best Trade [%]'),
            'worst_trade_pct': results.get('Worst Trade [%]'),
            'avg_trade_pct': results.get('Avg. Trade [%]'),
            'win_trades': results.get('# Wins'),
            'loss_trades': results.get('# Losses'),
            'max_trade_duration': results.get('Max. Trade Duration'),
            'avg_trade_duration': results.get('Avg. Trade Duration'),
            'profit_factor': results.get('Profit Factor'),
            'expectancy_pct': results.get('Expectancy [%]'),
            'sqn': results.get('SQN'),
            'equity_curve': results.get('_equity_curve'),
            'trades': results.get('_trades')
        }

        return standardized

    def get_metric(self, metric_name: str) -> Any:
        """
        获取标准化指标

        Args:
            metric_name: 指标名称

        Returns:
            Any: 指标值
        """
        return self.standardized_results.get(metric_name)

    def compare(self, other: 'BacktestResult') -> pd.DataFrame:
        """
        比较两个回测结果

        Args:
            other: 另一个回测结果

        Returns:
            pd.DataFrame: 比较结果
        """
        # 定义要比较的指标
        metrics = [
            # 基本指标
            'start_value',
            'end_value',
            'total_return_pct',
            'buy_hold_return_pct',

            # 风险调整收益指标
            'sharpe_ratio',
            'sortino_ratio',
            'calmar_ratio',
            'omega_ratio',

            # 回撤指标
            'max_drawdown_pct',
            'avg_drawdown_pct',

            # 交易统计
            'total_trades',
            'win_trades',
            'loss_trades',
            'win_rate_pct',
            'best_trade_pct',
            'worst_trade_pct',
            'avg_trade_pct',
            'profit_factor',
            'expectancy_pct',
            'sqn'
        ]

        # 提取指标值
        data = {
            self.engine: [self.get_metric(metric) for metric in metrics],
            other.engine: [other.get_metric(metric) for metric in metrics]
        }

        # 创建 DataFrame
        df = pd.DataFrame(data, index=metrics)

        # 添加差异列
        df['Difference'] = df[self.engine] - df[other.engine]
        df['Difference (%)'] = (df[self.engine] - df[other.engine]) / df[other.engine] * 100

        return df

    def plot_equity_curve(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制权益曲线

        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 plot 方法的参数

        Returns:
            plt.Axes: 绘制后的轴
        """
        equity_curve = self.get_metric('equity_curve')

        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        if isinstance(equity_curve, pd.Series):
            equity_curve.plot(ax=ax, label=f'{self.engine}', **kwargs)
        elif isinstance(equity_curve, pd.DataFrame) and 'Equity' in equity_curve.columns:
            equity_curve['Equity'].plot(ax=ax, label=f'{self.engine}', **kwargs)

        ax.set_title('Equity Curve')
        ax.set_xlabel('Date')
        ax.set_ylabel('Equity')
        ax.legend()
        ax.grid(True)

        return ax

    def plot_drawdown(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制回撤曲线

        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 plot 方法的参数

        Returns:
            plt.Axes: 绘制后的轴
        """
        equity_curve = self.get_metric('equity_curve')

        if isinstance(equity_curve, pd.DataFrame) and 'Drawdown' in equity_curve.columns:
            drawdown = equity_curve['Drawdown'] * 100
        elif isinstance(equity_curve, pd.Series):
            # 计算回撤
            peak = equity_curve.expanding().max()
            drawdown = (peak - equity_curve) / peak * 100
        else:
            drawdown = pd.Series()

        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        if not drawdown.empty:
            drawdown.plot(ax=ax, label=f'{self.engine}', **kwargs)
            ax.fill_between(drawdown.index, drawdown, 0, alpha=0.3, **kwargs)

        ax.set_title('Drawdown')
        ax.set_xlabel('Date')
        ax.set_ylabel('Drawdown (%)')
        ax.legend()
        ax.grid(True)

        return ax

    def generate_report(self, other: Optional['BacktestResult'] = None) -> str:
        """
        生成回测报告

        Args:
            other: 可选的另一个回测结果，用于比较

        Returns:
            str: 回测报告
        """
        report = f"# 回测报告\n\n"
        report += f"## 基本信息\n\n"
        report += f"- 回测引擎: {self.engine}\n"
        report += f"- 开始日期: {self.get_metric('start_date')}\n"
        report += f"- 结束日期: {self.get_metric('end_date')}\n"
        report += f"- 回测周期: {self.get_metric('duration')}\n\n"

        report += f"## 业绩指标\n\n"
        report += f"- 初始资金: {self.get_metric('start_value'):.2f}\n"
        report += f"- 最终资金: {self.get_metric('end_value'):.2f}\n"
        report += f"- 总收益率: {self.get_metric('total_return_pct'):.2f}%\n"
        report += f"- 基准收益率: {self.get_metric('buy_hold_return_pct'):.2f}%\n"
        report += f"- Sharpe 比率: {self.get_metric('sharpe_ratio'):.2f}\n"
        report += f"- Sortino 比率: {self.get_metric('sortino_ratio'):.2f}\n"
        report += f"- 最大回撤: {self.get_metric('max_drawdown_pct'):.2f}%\n\n"

        report += f"## 交易指标\n\n"
        report += f"- 总交易次数: {self.get_metric('total_trades')}\n"
        report += f"- 胜率: {self.get_metric('win_rate_pct'):.2f}%\n"
        report += f"- 最佳交易: {self.get_metric('best_trade_pct'):.2f}%\n"
        report += f"- 最差交易: {self.get_metric('worst_trade_pct'):.2f}%\n"
        report += f"- 平均交易: {self.get_metric('avg_trade_pct'):.2f}%\n"
        report += f"- 盈利因子: {self.get_metric('profit_factor'):.2f}\n"
        report += f"- 期望收益: {self.get_metric('expectancy_pct'):.2f}%\n\n"

        if other:
            report += f"## 与 {other.engine} 比较\n\n"
            comparison_df = self.compare(other)
            report += comparison_df.to_markdown()
            report += "\n\n"

        return report


class ResultAnalyzer:
    """
    回测结果分析器
    用于分析和比较多个回测结果
    """

    def __init__(self, results_list: Optional[list] = None):
        """
        初始化结果分析器

        Args:
            results_list: 回测结果列表，每个元素为 (results, engine) 元组
        """
        self.results = []
        if results_list:
            for results, engine in results_list:
                self.add_result(results, engine)

    def add_result(self, results: Any, engine: str = "native"):
        """
        添加回测结果

        Args:
            results: 原始回测结果
            engine: 回测引擎名称
        """
        result = BacktestResult(results, engine)
        self.results.append(result)

    def compare_all(self) -> pd.DataFrame:
        """
        比较所有回测结果

        Returns:
            pd.DataFrame: 比较结果
        """
        if len(self.results) < 2:
            raise ValueError("At least two results are needed for comparison")

        # 定义要比较的指标
        metrics = [
            # 基本指标
            'start_value',
            'end_value',
            'total_return_pct',
            'buy_hold_return_pct',

            # 风险调整收益指标
            'sharpe_ratio',
            'sortino_ratio',
            'calmar_ratio',

            # 回撤指标
            'max_drawdown_pct',

            # 交易统计
            'total_trades',
            'win_rate_pct',
            'profit_factor'
        ]

        # 提取所有结果的数据
        data = {}
        for result in self.results:
            data[result.engine] = [result.get_metric(metric) for metric in metrics]

        # 创建 DataFrame
        df = pd.DataFrame(data, index=metrics)

        return df

    def plot_all_equity_curves(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制所有权益曲线

        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 plot 方法的参数

        Returns:
            plt.Axes: 绘制后的轴
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))

        for result in self.results:
            result.plot_equity_curve(ax=ax, **kwargs)

        return ax
