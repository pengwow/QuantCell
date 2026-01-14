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
    
    def __init__(self, results: Any, engine: str):
        """
        初始化回测结果
        
        Args:
            results: 原始回测结果
            engine: 回测引擎名称，如 'backtesting.py' 或 'vectorbt'
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
        if self.engine == 'backtesting.py':
            return self._standardize_backtesting_py()
        elif self.engine == 'vectorbt':
            return self._standardize_vectorbt()
        else:
            raise ValueError(f"Unsupported engine: {self.engine}")
    
    def _standardize_backtesting_py(self) -> Dict[str, Any]:
        """
        标准化 backtesting.py 回测结果
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
            'calmar_ratio': results.get('Calmar Ratio', None),  # 添加 Calmar 比率
            'omega_ratio': results.get('Omega Ratio', None),  # 添加 Omega 比率
            'max_drawdown_pct': results.get('Max. Drawdown [%]'),
            'avg_drawdown_pct': results.get('Avg. Drawdown [%]'),
            'max_drawdown_duration': results.get('Max. Drawdown Duration'),
            'avg_drawdown_duration': results.get('Avg. Drawdown Duration'),
            'total_trades': results.get('# Trades'),
            'win_rate_pct': results.get('Win Rate [%]'),
            'best_trade_pct': results.get('Best Trade [%]'),
            'worst_trade_pct': results.get('Worst Trade [%]'),
            'avg_trade_pct': results.get('Avg. Trade [%]'),
            'win_trades': results.get('# Wins'),  # 添加盈利交易次数
            'loss_trades': results.get('# Losses'),  # 添加亏损交易次数
            'max_trade_duration': results.get('Max. Trade Duration'),
            'avg_trade_duration': results.get('Avg. Trade Duration'),
            'profit_factor': results.get('Profit Factor'),
            'expectancy_pct': results.get('Expectancy [%]'),
            'sqn': results.get('SQN', None),  # 添加系统质量数
            'equity_curve': results.get('_equity_curve'),
            'trades': results.get('_trades')
        }
        
        return standardized
    
    def _standardize_vectorbt(self) -> Dict[str, Any]:
        """
        标准化 vectorbt 回测结果
        """
        results = self.raw_results
        
        # 提取关键指标
        stats = results.stats()
        
        standardized = {
            'start_date': stats.get('Start'),
            'end_date': stats.get('End'),
            'duration': stats.get('Period'),
            'exposure_time_pct': stats.get('Exposure [%]', None),  # vectorbt 0.20+ 支持
            'start_value': stats.get('Start Value'),
            'end_value': stats.get('End Value'),
            'total_return_pct': stats.get('Total Return [%]'),
            'buy_hold_return_pct': stats.get('Benchmark Return [%]'),
            'sharpe_ratio': stats.get('Sharpe Ratio'),
            'sortino_ratio': stats.get('Sortino Ratio'),
            'calmar_ratio': stats.get('Calmar Ratio', None),  # 添加 Calmar 比率
            'omega_ratio': stats.get('Omega Ratio', None),  # 添加 Omega 比率
            'max_drawdown_pct': stats.get('Max Drawdown [%]'),
            'avg_drawdown_pct': None,  # vectorbt 没有直接提供平均回撤百分比
            'max_drawdown_duration': stats.get('Max Drawdown Duration'),
            'avg_drawdown_duration': None,  # vectorbt 没有直接提供平均回撤持续时间
            'total_trades': stats.get('Total Trades'),
            'win_rate_pct': stats.get('Win Rate [%]'),
            'best_trade_pct': stats.get('Best Trade [%]'),
            'worst_trade_pct': stats.get('Worst Trade [%]'),
            'avg_trade_pct': (stats.get('Avg Winning Trade [%]') * stats.get('Win Rate [%]') / 100 + 
                             stats.get('Avg Losing Trade [%]') * (1 - stats.get('Win Rate [%]') / 100)),
            'win_trades': stats.get('Total Winning Trades', None),  # 添加盈利交易次数
            'loss_trades': stats.get('Total Losing Trades', None),  # 添加亏损交易次数
            'max_trade_duration': stats.get('Max Trade Duration', None),  # vectorbt 0.20+ 支持
            'avg_trade_duration': (stats.get('Avg Winning Trade Duration') * stats.get('Win Rate [%]') / 100 + 
                                 stats.get('Avg Losing Trade Duration') * (1 - stats.get('Win Rate [%]') / 100)),
            'profit_factor': stats.get('Profit Factor'),
            'expectancy_pct': stats.get('Expectancy'),
            'sqn': stats.get('SQN', None),  # 添加系统质量数
            'equity_curve': results.value(),
            'trades': results.trades.records_readable
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
        
        if self.engine == 'backtesting.py':
            equity_curve['Equity'].plot(ax=ax, label=f'{self.engine}', **kwargs)
        elif self.engine == 'vectorbt':
            equity_curve.plot(ax=ax, label=f'{self.engine}', **kwargs)
        
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
        if self.engine == 'backtesting.py':
            equity_curve = self.get_metric('equity_curve')
            drawdown = equity_curve['Drawdown'] * 100
        elif self.engine == 'vectorbt':
            # vectorbt 直接提供回撤数据
            drawdown = self.raw_results.drawdown() * 100
        else:
            raise ValueError(f"Unsupported engine: {self.engine}")
        
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))
        
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
    
    def add_result(self, results: Any, engine: str):
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
        
        # 提取所有结果的指标值
        data = {}
        for result in self.results:
            data[result.engine] = [result.get_metric(metric) for metric in metrics]
        
        # 创建 DataFrame
        df = pd.DataFrame(data, index=metrics)
        
        return df
    
    def plot_equity_curves(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制所有回测结果的权益曲线
        
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
        
        ax.set_title('Equity Curves Comparison')
        ax.set_xlabel('Date')
        ax.set_ylabel('Equity')
        ax.legend()
        ax.grid(True)
        
        return ax
    
    def plot_drawdowns(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制所有回测结果的回撤曲线
        
        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 plot 方法的参数
        
        Returns:
            plt.Axes: 绘制后的轴
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))
        
        for result in self.results:
            result.plot_drawdown(ax=ax, **kwargs)
        
        ax.set_title('Drawdown Comparison')
        ax.set_xlabel('Date')
        ax.set_ylabel('Drawdown (%)')
        ax.legend()
        ax.grid(True)
        
        return ax
    
    def plot_risk_return_scatter(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制风险收益散点图
        
        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 scatter 方法的参数
        
        Returns:
            plt.Axes: 绘制后的轴
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 8))
        
        for result in self.results:
            sharpe = result.get_metric('sharpe_ratio')
            return_pct = result.get_metric('total_return_pct')
            max_dd = result.get_metric('max_drawdown_pct')
            
            if sharpe is not None and return_pct is not None and max_dd is not None:
                ax.scatter(
                    max_dd,  # x轴：最大回撤
                    return_pct,  # y轴：总收益率
                    s=sharpe * 100,  # 点大小：Sharpe比率
                    label=result.engine,
                    alpha=0.7,
                    **kwargs
                )
        
        ax.set_title('Risk-Return Scatter Plot')
        ax.set_xlabel('Max Drawdown (%)')
        ax.set_ylabel('Total Return (%)')
        ax.legend()
        ax.grid(True)
        
        # 添加说明文本
        ax.text(0.05, 0.95, 'Point size = Sharpe Ratio', transform=ax.transAxes, 
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        return ax
    
    def plot_monthly_returns(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制月度收益对比图
        
        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 plot 方法的参数
        
        Returns:
            plt.Axes: 绘制后的轴
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(12, 6))
        
        for result in self.results:
            equity_curve = result.get_metric('equity_curve')
            if equity_curve is not None:
                # 计算月度收益率
                if hasattr(equity_curve, 'iloc'):
                    # 对于 backtesting.py
                    monthly_returns = equity_curve['Equity'].resample('M').last().pct_change() * 100
                else:
                    # 对于 vectorbt
                    monthly_returns = equity_curve.resample('M').last().pct_change() * 100
                
                monthly_returns.plot(ax=ax, label=result.engine, **kwargs)
        
        ax.set_title('Monthly Returns Comparison')
        ax.set_xlabel('Date')
        ax.set_ylabel('Monthly Return (%)')
        ax.legend()
        ax.grid(True)
        
        return ax
    
    def plot_metrics_radar(self, ax: Optional[plt.Axes] = None, **kwargs) -> plt.Axes:
        """
        绘制指标雷达图
        
        Args:
            ax: 可选的 matplotlib 轴
            **kwargs: 传递给 plot 方法的参数
        
        Returns:
            plt.Axes: 绘制后的轴
        """
        # 定义要显示的指标和权重
        radar_metrics = [
            'total_return_pct',
            'sharpe_ratio',
            'sortino_ratio',
            'win_rate_pct',
            'profit_factor',
            'expectancy_pct'
        ]
        
        # 收集数据
        data = {}
        for result in self.results:
            engine_data = []
            for metric in radar_metrics:
                value = result.get_metric(metric)
                engine_data.append(value if value is not None else 0)
            data[result.engine] = engine_data
        
        # 创建雷达图
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
        
        # 计算角度
        angles = np.linspace(0, 2 * np.pi, len(radar_metrics), endpoint=False).tolist()
        angles += angles[:1]  # 闭合
        
        # 绘制每个引擎的数据
        for engine, values in data.items():
            values += values[:1]  # 闭合
            ax.plot(angles, values, linewidth=2, linestyle='solid', label=engine, **kwargs)
            ax.fill(angles, values, alpha=0.25, **kwargs)
        
        # 设置标签
        ax.set_thetagrids(np.degrees(angles[:-1]), radar_metrics)
        ax.set_title('Metrics Radar Chart')
        ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
        ax.grid(True)
        
        return ax
    
    def generate_comparison_report(self) -> str:
        """
        生成比较报告
        
        Returns:
            str: 比较报告
        """
        if len(self.results) < 2:
            raise ValueError("At least two results are needed for comparison")
        
        report = f"# 回测结果比较报告\n\n"
        report += f"## 参与比较的回测引擎\n\n"
        for i, result in enumerate(self.results, 1):
            report += f"{i}. {result.engine}\n"
        
        report += f"\n## 比较结果\n\n"
        comparison_df = self.compare_all()
        report += comparison_df.to_markdown()
        report += "\n\n"
        
        # 添加最佳指标标注
        report += f"## 最佳指标\n\n"
        for metric in comparison_df.index:
            # 跳过包含 NaN 的指标
            if comparison_df.loc[metric].isna().all():
                continue
            
            # 确定指标是越大越好还是越小越好
            higher_is_better = metric not in ['max_drawdown_pct', 'avg_drawdown_pct', 'worst_trade_pct']
            
            if higher_is_better:
                best_engine = comparison_df.loc[metric].idxmax()
                best_value = comparison_df.loc[metric].max()
            else:
                best_engine = comparison_df.loc[metric].idxmin()
                best_value = comparison_df.loc[metric].min()
            
            report += f"- {metric}: {best_engine} ({best_value:.2f})\n"
        
        # 添加引擎评分
        report += f"\n## 引擎综合评分\n\n"
        # 计算每个引擎的综合评分
        engine_scores = {}
        for result in self.results:
            score = 0
            for metric in comparison_df.index:
                # 跳过包含 NaN 的指标
                if comparison_df.loc[metric].isna().all():
                    continue
                
                value = result.get_metric(metric)
                if value is None:
                    continue
                
                higher_is_better = metric not in ['max_drawdown_pct', 'avg_drawdown_pct', 'worst_trade_pct']
                
                if higher_is_better:
                    # 归一化到 0-100
                    max_val = comparison_df.loc[metric].max()
                    min_val = comparison_df.loc[metric].min()
                    if max_val > min_val:
                        normalized = (value - min_val) / (max_val - min_val) * 100
                        score += normalized
                else:
                    # 越小越好的指标，反向归一化
                    max_val = comparison_df.loc[metric].max()
                    min_val = comparison_df.loc[metric].min()
                    if max_val > min_val:
                        normalized = (max_val - value) / (max_val - min_val) * 100
                        score += normalized
            
            engine_scores[result.engine] = score
        
        # 按分数排序
        sorted_scores = sorted(engine_scores.items(), key=lambda x: x[1], reverse=True)
        
        for engine, score in sorted_scores:
            report += f"- {engine}: {score:.2f} 分\n"
        
        report += f"\n## 结论\n\n"
        best_engine = sorted_scores[0][0]
        report += f"根据以上比较，{best_engine} 在本次回测中表现最佳。\n"
        report += f"建议根据具体的策略需求和偏好选择合适的回测引擎。\n"
        
        return report
