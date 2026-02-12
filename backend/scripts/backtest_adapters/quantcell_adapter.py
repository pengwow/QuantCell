#!/usr/bin/env python3
"""
QuantCell 回测适配器

将QuantCell框架的回测结果转换为统一格式
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


class QuantCellAdapter(BaseBacktestAdapter):
    """
    QuantCell框架回测适配器
    
    支持StrategyCore和StrategyBase两种策略类型
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.name = "QuantCell"
    
    def load_data(self,
                  symbol: str,
                  start_date: datetime,
                  end_date: datetime,
                  timeframe: str = '1d') -> pd.DataFrame:
        """
        加载历史数据
        
        从Yahoo Finance或本地数据源加载
        """
        try:
            import yfinance as yf
            
            # 转换symbol格式 (BTC/USDT -> BTC-USDT)
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
            
            # 确保必要的列存在
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_cols:
                if col not in df.columns:
                    raise ValueError(f"数据缺少必要的列: {col}")
            
            return df
            
        except Exception as e:
            print(f"从Yahoo Finance加载数据失败: {e}")
            print("尝试生成模拟数据...")
            return self._generate_mock_data(start_date, end_date, timeframe)
    
    def _generate_mock_data(self, 
                           start_date: datetime, 
                           end_date: datetime,
                           timeframe: str) -> pd.DataFrame:
        """生成模拟数据用于测试"""
        # 根据timeframe生成日期范围
        freq = 'D' if timeframe == '1d' else 'H'
        periods = (end_date - start_date).days + 1
        
        if timeframe == '1h':
            periods *= 24
        
        dates = pd.date_range(start=start_date, periods=periods, freq=freq)
        
        # 生成随机价格数据
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
        执行QuantCell回测
        
        根据策略类型选择不同的回测方式
        """
        # 检查策略类型
        if self._is_strategy_core(strategy_class):
            return self._run_strategy_core_backtest(
                strategy_class, strategy_params, data,
                initial_capital, commission, slippage
            )
        else:
            return self._run_strategy_base_backtest(
                strategy_class, strategy_params, data,
                initial_capital, commission, slippage
            )
    
    def _is_strategy_core(self, strategy_class: type) -> bool:
        """检查是否是StrategyCore子类"""
        try:
            from strategy.core.strategy_core import StrategyCore
            return issubclass(strategy_class, StrategyCore)
        except ImportError:
            return False
    
    def _run_strategy_core_backtest(self,
                                    strategy_class: type,
                                    strategy_params: Dict[str, Any],
                                    data: pd.DataFrame,
                                    initial_capital: float,
                                    commission: float,
                                    slippage: float) -> BacktestResult:
        """运行StrategyCore策略回测"""
        # 创建策略实例
        strategy = strategy_class(strategy_params)

        # 【调试输出】打印数据信息
        print(f"\n[QuantCell调试] 数据形状: {data.shape}")
        print(f"[QuantCell调试] 数据列: {list(data.columns)}")
        print(f"[QuantCell调试] 前5行Close价格:\n{data['Close'].head()}")
        print(f"[QuantCell调试] 数据日期范围: {data.index[0]} 至 {data.index[-1]}")

        # 计算指标
        indicators = strategy.calculate_indicators(data)

        # 【调试输出】打印指标信息
        print(f"\n[QuantCell调试] 指标键: {list(indicators.keys())}")
        print(f"[QuantCell调试] 前5行sma_fast:\n{indicators['sma_fast'].head()}")
        print(f"[QuantCell调试] 前5行sma_slow:\n{indicators['sma_slow'].head()}")

        # 生成信号
        signals = strategy.generate_signals(indicators)

        # 【调试输出】打印信号信息
        print(f"\n[QuantCell调试] 信号键: {list(signals.keys())}")
        entries = signals.get('entries', pd.Series(False, index=data.index))
        exits = signals.get('exits', pd.Series(False, index=data.index))
        print(f"[QuantCell调试] 买入信号数量: {entries.sum()}")
        print(f"[QuantCell调试] 卖出信号数量: {exits.sum()}")
        if entries.sum() > 0:
            first_entry = entries[entries].index[0]
            print(f"[QuantCell调试] 第一个买入信号时间: {first_entry}")
            print(f"[QuantCell调试] 第一个买入信号时sma_fast: {indicators['sma_fast'].loc[first_entry]:.2f}")
            print(f"[QuantCell调试] 第一个买入信号时sma_slow: {indicators['sma_slow'].loc[first_entry]:.2f}")
            print(f"[QuantCell调试] 第一个买入信号时Close价格: {data['Close'].loc[first_entry]:.2f}")

        # 将 entries/exits 信号转换为统一的 signal 格式
        # 1: 买入信号, -1: 卖出信号, 0: 无信号
        signal_series = pd.Series(0, index=data.index)
        signal_series[entries] = 1   # 买入信号
        signal_series[exits] = -1    # 卖出信号

        # 执行回测模拟
        return self._simulate_trades(
            data, signal_series, initial_capital, commission, slippage
        )
    
    def _run_strategy_base_backtest(self,
                                    strategy_class: type,
                                    strategy_params: Dict[str, Any],
                                    data: pd.DataFrame,
                                    initial_capital: float,
                                    commission: float,
                                    slippage: float) -> BacktestResult:
        """运行StrategyBase策略回测"""
        # 创建策略实例
        strategy = strategy_class(strategy_params)
        
        # 初始化
        if hasattr(strategy, 'on_init'):
            strategy.on_init()
        
        # 模拟事件驱动回测
        signals = []
        for timestamp, row in data.iterrows():
            if hasattr(strategy, 'on_bar'):
                strategy.on_bar(row)
            
            # 获取当前信号（假设策略有has_position属性）
            if hasattr(strategy, 'has_position'):
                if strategy.has_position:
                    signals.append(1)  # 持有多头
                else:
                    signals.append(0)  # 空仓
            else:
                signals.append(0)
        
        signal_series = pd.Series(signals, index=data.index)
        
        # 执行回测模拟
        return self._simulate_trades(
            data, signal_series, initial_capital, commission, slippage
        )
    
    def _simulate_trades(self,
                        data: pd.DataFrame,
                        signals: pd.Series,
                        initial_capital: float,
                        commission: float,
                        slippage: float) -> BacktestResult:
        """
        模拟交易执行（使用Numba优化版本）

        根据信号执行买卖，计算回测结果
        """
        # 尝试使用Numba优化版本
        try:
            from strategy.core.numba_backtest import (
                simulate_trades_numba,
                calculate_drawdown_numba,
                calculate_returns_numba,
                calculate_sharpe_numba
            )

            prices = np.asarray(data['Close'].values, dtype=np.float64)
            signals_array = np.asarray(signals.values, dtype=np.int32)

            # 使用Numba优化的回测模拟
            equity, cash, position, entry_indices, exit_indices = simulate_trades_numba(
                prices, signals_array, initial_capital, commission, slippage
            )

            # 计算最终资金
            final_capital = equity[-1] if len(equity) > 0 else initial_capital

            # 计算回撤
            drawdown, max_drawdown = calculate_drawdown_numba(equity)
            max_drawdown_pct = max_drawdown * 100

            # 计算收益率和夏普比率
            returns = calculate_returns_numba(equity)
            sharpe_ratio = calculate_sharpe_numba(returns)

            # 构建交易记录（向量化优化）
            trades = []
            valid_trades = min(len(entry_indices), len(exit_indices))

            if valid_trades > 0:
                # 批量获取时间戳
                entry_times = [pd.Timestamp(data.index[idx]).to_pydatetime() for idx in entry_indices[:valid_trades]]
                exit_times = [pd.Timestamp(data.index[idx]).to_pydatetime() for idx in exit_indices[:valid_trades] if idx >= 0]

                # 批量计算交易数据
                entry_prices_list = prices[entry_indices[:valid_trades]]
                exit_prices_list = prices[exit_indices[:valid_trades]]
                cash_list = cash[entry_indices[:valid_trades]]
                equity_entry = equity[entry_indices[:valid_trades]]
                equity_exit = equity[exit_indices[:valid_trades]]

                # 向量化计算size和pnl
                sizes = np.where(entry_prices_list > 0, cash_list / entry_prices_list, 0.0)
                pnls = equity_exit - equity_entry
                pnl_pcts = np.where(equity_entry > 0, (equity_exit - equity_entry) / equity_entry * 100, 0.0)

                # 批量创建交易记录
                for i in range(valid_trades):
                    if exit_indices[i] >= 0 and i < len(exit_times):
                        trade = TradeRecord(
                            entry_time=entry_times[i],
                            exit_time=exit_times[i],
                            entry_price=float(entry_prices_list[i]),
                            exit_price=float(exit_prices_list[i]),
                            size=float(sizes[i]),
                            side='long',
                            pnl=float(pnls[i]),
                            pnl_pct=float(pnl_pcts[i]),
                            status='closed'
                        )
                        trades.append(trade)

            # 构建权益曲线（向量化优化）
            equity_curve_data = {
                'timestamp': data.index,
                'equity': equity,
                'cash': cash,
                'position': position,
                'position_value': position * prices,
            }
            equity_curve = pd.DataFrame(equity_curve_data)

            # 计算统计指标
            closed_trades = [t for t in trades if t.status == 'closed']
            winning_trades = [t for t in closed_trades if t.pnl and t.pnl > 0]
            losing_trades = [t for t in closed_trades if t.pnl and t.pnl <= 0]

            total_trades = len(closed_trades)
            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

            avg_profit = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
            avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0

            total_return = final_capital - initial_capital
            total_return_pct = (total_return / initial_capital) * 100

        except ImportError:
            # 回退到Python实现
            return self._simulate_trades_python(
                data, signals, initial_capital, commission, slippage
            )

        # 构建返回结果
        return BacktestResult(
            start_date=pd.Timestamp(data.index[0]).to_pydatetime(),
            end_date=pd.Timestamp(data.index[-1]).to_pydatetime(),
            initial_capital=initial_capital,
            final_capital=float(final_capital),
            total_return=float(total_return),
            total_return_pct=float(total_return_pct),
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=float(win_rate),
            avg_profit=float(avg_profit),
            avg_loss=float(avg_loss),
            profit_factor=0.0,  # 需要计算
            max_drawdown=float(max_drawdown),
            max_drawdown_pct=float(max_drawdown_pct),
            sharpe_ratio=float(sharpe_ratio),
            sortino_ratio=0.0,  # 可以后续计算
            trades=trades,
            equity_curve=pd.DataFrame(equity_curve),
            raw_result=None
        )

    def _simulate_trades_python(self,
                        data: pd.DataFrame,
                        signals: pd.Series,
                        initial_capital: float,
                        commission: float,
                        slippage: float) -> BacktestResult:
        """
        模拟交易执行（Python回退版本）

        根据信号执行买卖，计算回测结果
        """
        capital = initial_capital
        position = 0.0
        trades = []
        equity_curve = []

        current_trade = None

        for timestamp, row in data.iterrows():
            price = float(row['Close'])
            signal = int(signals.loc[timestamp])

            # 记录权益
            position_value = position * price if position > 0 else 0
            total_value = capital + position_value
            equity_curve.append({
                'timestamp': timestamp,
                'equity': float(total_value),
                'cash': float(capital),
                'position': float(position),
                'position_value': float(position_value)
            })

            # 处理信号
            if signal == 1 and position == 0:  # 买入信号
                # 计算买入数量（使用全部资金）
                position_size = float(capital / price * (1 - commission))
                position = position_size
                capital = 0

                current_trade = TradeRecord(
                    entry_time=timestamp,
                    exit_time=None,
                    entry_price=float(price),
                    exit_price=None,
                    size=float(position_size),
                    side='long',
                    pnl=None,
                    pnl_pct=None,
                    status='open'
                )

            elif signal == -1 and position > 0:  # 卖出信号
                # 检查是否有当前交易记录
                if current_trade is None:
                    # 没有交易记录，直接平仓
                    sell_value = float(position * price * (1 - commission))
                    capital = sell_value
                    position = 0
                else:
                    # 有交易记录，计算盈亏
                    sell_value = float(position * price * (1 - commission))
                    pnl = float(sell_value - (current_trade.size * current_trade.entry_price))
                    pnl_pct = float(pnl / (current_trade.size * current_trade.entry_price))

                    capital = sell_value

                    current_trade.exit_time = timestamp
                    current_trade.exit_price = float(price)
                    current_trade.pnl = pnl
                    current_trade.pnl_pct = pnl_pct
                    current_trade.status = 'closed'
                    trades.append(current_trade)

                    position = 0
                    current_trade = None

        # 如果还有持仓，计算最终价值
        final_price = float(data['Close'].iloc[-1])
        position_value = float(position * final_price) if position > 0 else 0
        final_capital = float(capital + position_value)

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
        max_drawdown = 0.0
        max_drawdown_pct = 0.0
        sharpe_ratio = 0.0
        
        if not equity_df.empty:
            equity_df['peak'] = equity_df['equity'].cummax()
            equity_df['drawdown'] = (equity_df['equity'] - equity_df['peak']) / equity_df['peak']
            max_drawdown_pct = float(equity_df['drawdown'].min() * 100)
            max_drawdown = float(equity_df['drawdown'].min() * equity_df['peak'].max())
            
            # 计算夏普比率（简化版）
            returns = equity_df['equity'].pct_change().dropna()
            if len(returns) > 0 and returns.std() > 0:
                sharpe_ratio = float(returns.mean() / returns.std() * np.sqrt(252))
            else:
                sharpe_ratio = 0.0
        
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
            sortino_ratio=0.0,  # 简化处理
            trades=trades,
            equity_curve=equity_df if not equity_df.empty else pd.DataFrame(),
            raw_result={'signals': signals.to_dict()}
        )
    
    def validate_strategy(self, strategy_class: type) -> tuple[bool, str]:
        """
        验证策略类是否有效
        """
        try:
            # 检查是否是StrategyCore子类
            from strategy.core.strategy_core import StrategyCore
            if issubclass(strategy_class, StrategyCore):
                # 检查必需方法
                if not hasattr(strategy_class, 'calculate_indicators'):
                    return False, "StrategyCore子类必须实现calculate_indicators方法"
                if not hasattr(strategy_class, 'generate_signals'):
                    return False, "StrategyCore子类必须实现generate_signals方法"
                return True, ""
            
            # 检查是否是StrategyBase子类
            from strategy.core.strategy_base import StrategyBase
            if issubclass(strategy_class, StrategyBase):
                return True, ""
            
            return False, "策略类必须继承自StrategyCore或StrategyBase"
            
        except ImportError as e:
            return False, f"导入策略基类失败: {e}"
        except Exception as e:
            return False, f"验证失败: {e}"
