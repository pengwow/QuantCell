#!/usr/bin/env python3
"""
回测适配器基类

定义统一的回测适配器接口，所有框架适配器都需要继承此类
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import pandas as pd


@dataclass
class TradeRecord:
    """交易记录"""
    entry_time: datetime
    exit_time: Optional[datetime]
    entry_price: float
    exit_price: Optional[float]
    size: float
    side: str  # 'long' or 'short'
    pnl: Optional[float]
    pnl_pct: Optional[float]
    status: str  # 'open' or 'closed'


@dataclass
class BacktestResult:
    """回测结果"""
    # 基本统计
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    
    # 交易统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_profit: float
    avg_loss: float
    profit_factor: float
    
    # 风险指标
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    
    # 交易记录
    trades: List[TradeRecord]
    
    # 每日/周期收益
    equity_curve: pd.DataFrame
    
    # 原始结果（适配器特定）
    raw_result: Any


class BaseBacktestAdapter(ABC):
    """
    回测适配器基类
    
    所有框架适配器都需要实现以下接口
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化适配器
        
        Args:
            config: 适配器配置
        """
        self.config = config or {}
        self.name = self.__class__.__name__
    
    @abstractmethod
    def load_data(self, 
                  symbol: str, 
                  start_date: datetime, 
                  end_date: datetime,
                  timeframe: str = '1d') -> pd.DataFrame:
        """
        加载历史数据
        
        Args:
            symbol: 交易对符号，如 'BTC/USDT'
            start_date: 开始日期
            end_date: 结束日期
            timeframe: 时间周期，如 '1d', '1h', '15m'
            
        Returns:
            pd.DataFrame: OHLCV数据
        """
        pass
    
    @abstractmethod
    def run_backtest(self,
                     strategy_class: type,
                     strategy_params: Dict[str, Any],
                     data: pd.DataFrame,
                     initial_capital: float = 10000.0,
                     commission: float = 0.001,
                     slippage: float = 0.0) -> BacktestResult:
        """
        执行回测
        
        Args:
            strategy_class: 策略类
            strategy_params: 策略参数
            data: 历史数据
            initial_capital: 初始资金
            commission: 手续费率
            slippage: 滑点
            
        Returns:
            BacktestResult: 回测结果
        """
        pass
    
    @abstractmethod
    def validate_strategy(self, strategy_class: type) -> tuple[bool, str]:
        """
        验证策略类是否有效
        
        Args:
            strategy_class: 策略类
            
        Returns:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        pass
    
    def compare_results(self, 
                        result1: BacktestResult, 
                        result2: BacktestResult,
                        tolerance: float = 0.01) -> Dict[str, Any]:
        """
        对比两个回测结果
        
        Args:
            result1: 第一个回测结果
            result2: 第二个回测结果
            tolerance: 容差比例
            
        Returns:
            Dict[str, Any]: 对比结果
        """
        comparison = {
            'total_return_match': abs(result1.total_return_pct - result2.total_return_pct) <= tolerance * 100,
            'total_trades_match': result1.total_trades == result2.total_trades,
            'win_rate_diff': abs(result1.win_rate - result2.win_rate),
            'max_drawdown_diff': abs(result1.max_drawdown_pct - result2.max_drawdown_pct),
            'sharpe_diff': abs(result1.sharpe_ratio - result2.sharpe_ratio),
            'details': []
        }
        
        # 对比交易记录
        if len(result1.trades) == len(result2.trades):
            for i, (t1, t2) in enumerate(zip(result1.trades, result2.trades)):
                trade_match = {
                    'index': i,
                    'entry_time_match': t1.entry_time == t2.entry_time,
                    'entry_price_diff': abs(t1.entry_price - t2.entry_price),
                    'exit_time_match': t1.exit_time == t2.exit_time,
                    'exit_price_diff': abs((t1.exit_price or 0) - (t2.exit_price or 0)),
                    'pnl_diff': abs((t1.pnl or 0) - (t2.pnl or 0)),
                }
                comparison['details'].append(trade_match)
        
        return comparison
    
    def generate_report(self, 
                        results: Dict[str, BacktestResult],
                        comparison: Dict[str, Any]) -> str:
        """
        生成回测对比报告
        
        Args:
            results: 各框架回测结果
            comparison: 对比结果
            
        Returns:
            str: Markdown格式报告
        """
        lines = []
        lines.append("# 回测对比报告\n")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 汇总各框架结果
        lines.append("## 各框架回测结果\n")
        for name, result in results.items():
            lines.append(f"### {name}\n")
            lines.append(f"- 总收益率: {result.total_return_pct:.2f}%")
            lines.append(f"- 总交易次数: {result.total_trades}")
            lines.append(f"- 胜率: {result.win_rate:.2f}%")
            lines.append(f"- 最大回撤: {result.max_drawdown_pct:.2f}%")
            lines.append(f"- 夏普比率: {result.sharpe_ratio:.2f}\n")
        
        # 对比结果
        lines.append("## 对比结果\n")
        lines.append(f"- 总收益率一致: {'✓' if comparison.get('total_return_match') else '✗'}")
        lines.append(f"- 交易次数一致: {'✓' if comparison.get('total_trades_match') else '✗'}")
        lines.append(f"- 胜率差异: {comparison.get('win_rate_diff', 0):.2f}%")
        lines.append(f"- 最大回撤差异: {comparison.get('max_drawdown_diff', 0):.2f}%")
        lines.append(f"- 夏普比率差异: {comparison.get('sharpe_diff', 0):.2f}\n")
        
        return '\n'.join(lines)
