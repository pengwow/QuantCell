#!/usr/bin/env python3
"""
Freqtrade 回测适配器

将Freqtrade框架的回测结果转换为统一格式
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np

# 添加backend到路径
backend_path = Path(__file__).resolve().parent.parent.parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from scripts.backtest_adapters.base_adapter import BaseBacktestAdapter, BacktestResult, TradeRecord


class FreqtradeAdapter(BaseBacktestAdapter):
    """
    Freqtrade框架回测适配器
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.name = "Freqtrade"
    
    def load_data(self,
                  symbol: str,
                  start_date: datetime,
                  end_date: datetime,
                  timeframe: str = '1d') -> pd.DataFrame:
        """
        加载历史数据
        """
        try:
            import yfinance as yf
            
            # 转换symbol格式
            yf_symbol = symbol.replace('/', '-')
            
            # 下载数据
            df = yf.download(
                yf_symbol,
                start=start_date,
                end=end_date,
                interval=timeframe,
                progress=False
            )
            
            # 标准化列名
            df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
            
            return df
            
        except Exception as e:
            print(f"从Yahoo Finance加载数据失败: {e}")
            return self._generate_mock_data(start_date, end_date, timeframe)
    
    def _generate_mock_data(self, 
                           start_date: datetime, 
                           end_date: datetime,
                           timeframe: str) -> pd.DataFrame:
        """生成模拟数据用于测试"""
        freq = 'D' if timeframe == '1d' else 'H'
        periods = (end_date - start_date).days + 1
        
        if timeframe == '1h':
            periods *= 24
        
        dates = pd.date_range(start=start_date, periods=periods, freq=freq)
        
        np.random.seed(42)
        returns = np.random.randn(len(dates)) * 0.02
        prices = 100 * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'Open': prices * (1 + np.random.randn(len(dates)) * 0.001),
            'High': prices * (1 + abs(np.random.randn(len(dates))) * 0.01),
            'Low': prices * (1 - abs(np.random.randn(len(dates))) * 0.01),
            'Close': prices,
            'Volume': np.random.randint(1000000, 10000000, len(dates))
        }, index=dates)
        
        return df
    
    def run_backtest(self,
                     strategy_class: type,
                     strategy_params: Dict[str, Any],
                     data: pd.DataFrame,
                     initial_capital: float = 10000.0,
                     commission: float = 0.001,
                     slippage: float = 0.0) -> BacktestResult:
        """
        执行Freqtrade回测
        
        由于Freqtrade需要完整的配置文件和数据库，这里使用简化的模拟回测
        """
        print("Freqtrade回测使用模拟实现...")

        # 提取参数
        fast_period = strategy_params.get('fast', 10)
        slow_period = strategy_params.get('slow', 30)

        # 【调试输出】打印数据信息
        print(f"\n[Freqtrade调试] 数据形状: {data.shape}")
        print(f"[Freqtrade调试] 数据列: {list(data.columns)}")
        print(f"[Freqtrade调试] 前5行Close价格:\n{data['Close'].head()}")

        # 计算SMA
        sma_fast = data['Close'].rolling(window=fast_period).mean()
        sma_slow = data['Close'].rolling(window=slow_period).mean()

        # 【调试输出】打印指标信息
        print(f"\n[Freqtrade调试] 前5行sma_fast:\n{sma_fast.head()}")
        print(f"[Freqtrade调试] 前5行sma_slow:\n{sma_slow.head()}")

        # 生成信号 (1=买入, -1=卖出, 0=持有)
        signals = pd.Series(0, index=data.index)
        buy_signals = (sma_fast > sma_slow) & (sma_fast.shift(1) <= sma_slow.shift(1))
        sell_signals = (sma_fast < sma_slow) & (sma_fast.shift(1) >= sma_slow.shift(1))
        signals[buy_signals] = 1
        signals[sell_signals] = -1

        # 【调试输出】打印信号信息
        print(f"\n[Freqtrade调试] 买入信号数量: {buy_signals.sum()}")
        print(f"[Freqtrade调试] 卖出信号数量: {sell_signals.sum()}")
        if buy_signals.sum() > 0:
            first_entry = buy_signals[buy_signals].index[0]
            print(f"[Freqtrade调试] 第一个买入信号时间: {first_entry}")
            print(f"[Freqtrade调试] 第一个买入信号时sma_fast: {sma_fast.loc[first_entry]:.2f}")
            print(f"[Freqtrade调试] 第一个买入信号时sma_slow: {sma_slow.loc[first_entry]:.2f}")
            print(f"[Freqtrade调试] 第一个买入信号时Close价格: {data['Close'].loc[first_entry]:.2f}")

        # 执行回测模拟
        return self._simulate_trades(
            data, signals, initial_capital, commission, slippage
        )
    
    def _simulate_trades(self,
                        data: pd.DataFrame,
                        signals: pd.Series,
                        initial_capital: float,
                        commission: float,
                        slippage: float) -> BacktestResult:
        """
        模拟交易执行
        """
        capital = initial_capital
        position = 0.0
        trades = []
        equity_curve = []
        
        current_trade = None
        
        for timestamp, row in data.iterrows():
            price = row['Close']
            signal = signals.loc[timestamp]
            
            # 记录权益
            position_value = position * price if position > 0 else 0
            total_value = capital + position_value
            equity_curve.append({
                'timestamp': timestamp,
                'equity': total_value,
                'cash': capital,
                'position': position,
                'position_value': position_value
            })
            
            # 处理信号
            if signal == 1 and position == 0:  # 买入信号
                # 计算买入数量（使用全部资金）
                position_size = capital / price * (1 - commission)
                position = position_size
                capital = 0
                
                current_trade = TradeRecord(
                    entry_time=timestamp,
                    exit_time=None,
                    entry_price=price,
                    exit_price=None,
                    size=position_size,
                    side='long',
                    pnl=None,
                    pnl_pct=None,
                    status='open'
                )
                
            elif signal == -1 and position > 0:  # 卖出信号
                # 平仓
                sell_value = position * price * (1 - commission)
                pnl = sell_value - (current_trade.size * current_trade.entry_price)
                pnl_pct = pnl / (current_trade.size * current_trade.entry_price)
                
                capital = sell_value
                
                current_trade.exit_time = timestamp
                current_trade.exit_price = price
                current_trade.pnl = pnl
                current_trade.pnl_pct = pnl_pct
                current_trade.status = 'closed'
                trades.append(current_trade)
                
                position = 0
                current_trade = None
        
        # 如果还有持仓，计算最终价值
        final_price = data['Close'].iloc[-1]
        position_value = position * final_price if position > 0 else 0
        final_capital = capital + position_value
        
        # 计算统计指标
        total_return = final_capital - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        
        closed_trades = [t for t in trades if t.status == 'closed']
        winning_trades = [t for t in closed_trades if t.pnl and t.pnl > 0]
        losing_trades = [t for t in closed_trades if t.pnl and t.pnl <= 0]
        
        total_trades = len(closed_trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        avg_profit = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0
        
        gross_profit = sum([t.pnl for t in winning_trades]) if winning_trades else 0
        gross_loss = abs(sum([t.pnl for t in losing_trades])) if losing_trades else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # 计算最大回撤
        equity_df = pd.DataFrame(equity_curve)
        if not equity_df.empty:
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']
            max_drawdown_pct = equity_df['drawdown'].min() * 100
            max_drawdown = equity_df['drawdown'].min() * equity_df['peak'].max()
            
            # 计算夏普比率（简化版）
            returns = equity_df['equity'].pct_change().dropna()
            sharpe_ratio = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        else:
            max_drawdown = 0
            max_drawdown_pct = 0
            sharpe_ratio = 0
        
        return BacktestResult(
            start_date=data.index[0],
            end_date=data.index[-1],
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=0.0,
            trades=trades,
            equity_curve=equity_df if not equity_df.empty else pd.DataFrame(),
            raw_result={'signals': signals.to_dict()}
        )
    
    def validate_strategy(self, strategy_class: type) -> tuple[bool, str]:
        """
        验证策略类是否有效
        
        Freqtrade需要IStrategy接口，这里简化为接受任何类
        """
        try:
            # Freqtrade策略通常需要实现populate_indicators和populate_buy_trend等方法
            # 这里简化为检查基本结构
            required_methods = ['populate_indicators', 'populate_buy_trend', 'populate_sell_trend']
            missing_methods = [m for m in required_methods if not hasattr(strategy_class, m)]
            
            if missing_methods:
                return True, f"缺少Freqtrade标准方法: {missing_methods}，将使用模拟回测"
            
            return True, ""
            
        except Exception as e:
            return False, f"验证失败: {e}"
