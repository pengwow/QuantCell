# -*- coding: utf-8 -*-
"""
投资组合回测适配器

支持多交易对共享资金池的回测，实现正确的资金分配逻辑：
- 所有交易对共享一份总初始资金
- 交易对之间的资金相互影响
- 支持持仓管理和资金调度
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger
from datetime import datetime

from strategy.core.vector_engine import VectorEngine
from strategy.core.strategy_base import StrategyBase


@dataclass
class Position:
    """持仓信息"""
    symbol: str
    size: float = 0.0
    entry_price: float = 0.0
    entry_time: Optional[datetime] = None
    
    @property
    def value(self, current_price: float = 0.0) -> float:
        """计算持仓价值"""
        return self.size * current_price if current_price > 0 else 0.0
    
    @property
    def is_open(self) -> bool:
        """是否有持仓"""
        return self.size != 0


@dataclass
class PortfolioState:
    """投资组合状态"""
    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    total_equity: float = 0.0
    
    def get_position_value(self, symbol: str, current_price: float) -> float:
        """获取指定持仓的价值"""
        pos = self.positions.get(symbol)
        if pos and pos.is_open:
            # 调用 Position 的 value 方法计算持仓价值
            return float(pos.size) * float(current_price)
        return 0.0

    def get_total_position_value(self, prices: Dict[str, float]) -> float:
        """获取所有持仓的总价值"""
        total = 0.0
        for symbol, pos in self.positions.items():
            if pos.is_open and symbol in prices:
                total += float(pos.size) * float(prices[symbol])
        return total
    
    def update_equity(self, prices: Dict[str, float]):
        """更新总权益"""
        position_value = self.get_total_position_value(prices)
        self.total_equity = self.cash + position_value


class PortfolioBacktestAdapter:
    """
    投资组合回测适配器
    
    实现多交易对共享资金池的回测逻辑：
    1. 所有交易对共享一份初始资金
    2. 每个交易对根据信号独立执行交易
    3. 交易相互影响共享资金池
    4. 统一计算组合权益曲线
    """
    
    def __init__(self, strategy: StrategyBase):
        """
        初始化适配器
        
        参数：
            strategy: 策略实例
        """
        self.strategy = strategy
        self.engine = VectorEngine()
        self.results = None
        self.portfolio = None
        
    def run_backtest(
        self,
        data: Dict[str, pd.DataFrame],
        init_cash: float = 100000.0,
        fees: float = 0.001,
        slippage: float = 0.0001,
        position_size_pct: float = 0.1,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """
        运行投资组合回测

        参数：
            data: 多交易对数据字典 {symbol: DataFrame}
            init_cash: 初始总资金（所有交易对共享）
            fees: 手续费率
            slippage: 滑点
            position_size_pct: 单笔交易资金使用比例（默认10%）
            verbose: 是否显示详细交易输出

        返回：
            Dict: 回测结果，包含组合整体和各交易对的详细数据
        """
        if not data:
            raise ValueError("数据字典不能为空")

        logger.info(f"开始投资组合回测，交易对数量: {len(data)}")
        logger.info(f"初始总资金: {init_cash:.2f}")
        
        # 初始化投资组合状态
        self.portfolio = PortfolioState(cash=init_cash)
        
        # 对齐所有数据的时间索引
        aligned_data = self._align_data(data)
        
        # 获取统一的时间索引
        common_index = self._get_common_index(aligned_data)
        
        # 初始化各交易对的策略状态
        symbol_states = {}
        for symbol in aligned_data.keys():
            self.portfolio.positions[symbol] = Position(symbol=symbol)
            symbol_states[symbol] = {
                'signals': [],
                'trades': [],
                'orders': []
            }
        
        # 生成所有交易对的信号
        all_signals = {}
        for symbol, df in aligned_data.items():
            signals = self._generate_signals(df, symbol)
            all_signals[symbol] = signals
        
        # 运行组合回测
        portfolio_equity_curve = []
        portfolio_trades = []
        
        for i, timestamp in enumerate(common_index):
            # 获取当前时刻所有交易对的价格
            current_prices = {}
            for symbol, df in aligned_data.items():
                if timestamp in df.index:
                    current_prices[symbol] = df.loc[timestamp, 'Close']
            
            # 更新组合权益
            self.portfolio.update_equity(current_prices)
            
            # 记录组合权益
            portfolio_equity_curve.append({
                'timestamp': timestamp,
                'datetime': timestamp.isoformat() if isinstance(timestamp, pd.Timestamp) else str(timestamp),
                'equity': self.portfolio.total_equity,
                'cash': self.portfolio.cash,
                'position_value': self.portfolio.total_equity - self.portfolio.cash
            })
            
            # 处理每个交易对的信号
            for symbol in aligned_data.keys():
                if timestamp not in aligned_data[symbol].index:
                    continue
                
                df = aligned_data[symbol]
                signals = all_signals[symbol]
                price = float(df.loc[timestamp, 'Close'])

                # 检查信号
                entry_signal = signals['entries'].loc[timestamp] if timestamp in signals['entries'].index else False
                exit_signal = signals['exits'].loc[timestamp] if timestamp in signals['exits'].index else False

                position = self.portfolio.positions[symbol]

                # 处理入场信号
                if entry_signal and not position.is_open:
                    # 计算可用资金（考虑已用资金）
                    available_cash = self.portfolio.cash
                    trade_cash = min(available_cash * position_size_pct, available_cash * 0.95)

                    if trade_cash > 0:
                        # 计算可买入数量
                        size = trade_cash / price
                        
                        # 扣除资金和手续费
                        cost = size * price * (1 + fees)
                        if self.portfolio.cash >= cost:
                            self.portfolio.cash -= cost
                            position.size = size
                            position.entry_price = price
                            position.entry_time = timestamp
                            
                            trade = {
                                'symbol': symbol,
                                'direction': 'buy',
                                'size': size,
                                'price': price,
                                'timestamp': timestamp,
                                'cost': cost,
                                'fees': size * price * fees
                            }
                            portfolio_trades.append(trade)
                            symbol_states[symbol]['trades'].append(trade)
                            if verbose:
                                logger.info(f"【买入】{symbol} @ {price:.2f}, 数量: {size:.4f}")
                
                # 处理出场信号
                elif exit_signal and position.is_open:
                    # 卖出持仓
                    revenue = position.size * price * (1 - fees)
                    pnl = position.size * (price - position.entry_price) - (position.size * price * fees)
                    
                    self.portfolio.cash += revenue
                    
                    trade = {
                        'symbol': symbol,
                        'direction': 'sell',
                        'size': position.size,
                        'price': price,
                        'timestamp': timestamp,
                        'revenue': revenue,
                        'pnl': pnl,
                        'fees': position.size * price * fees,
                        'entry_price': position.entry_price,
                        'entry_time': position.entry_time
                    }
                    portfolio_trades.append(trade)
                    symbol_states[symbol]['trades'].append(trade)

                    # 清空持仓
                    position.size = 0
                    position.entry_price = 0
                    position.entry_time = None

                    if verbose:
                        logger.info(f"【卖出】{symbol} @ {price:.2f}, 盈亏: {pnl:.2f}")
        
        # 回测结束，强制平仓所有持仓
        final_timestamp = common_index[-1]
        for symbol, position in self.portfolio.positions.items():
            if position.is_open:
                df = aligned_data[symbol]
                if final_timestamp in df.index:
                    price = float(df.loc[final_timestamp, 'Close'])
                    position_size = float(position.size)
                    entry_price = float(position.entry_price) if position.entry_price else 0.0

                    revenue = position_size * price * (1 - fees)
                    pnl = position_size * (price - entry_price) - (position_size * price * fees)

                    self.portfolio.cash += revenue

                    trade = {
                        'symbol': symbol,
                        'direction': 'sell',
                        'size': position_size,
                        'price': price,
                        'timestamp': final_timestamp,
                        'revenue': revenue,
                        'pnl': pnl,
                        'fees': position_size * price * fees,
                        'entry_price': entry_price,
                        'entry_time': position.entry_time,
                        'forced_exit': True
                    }
                    portfolio_trades.append(trade)
                    symbol_states[symbol]['trades'].append(trade)

                    position.size = 0.0
                    if verbose:
                        logger.info(f"【强制平仓】{symbol} @ {price:.2f}, 盈亏: {pnl:.2f}")
        
        # 计算最终权益
        final_prices = {}
        for symbol, df in aligned_data.items():
            if final_timestamp in df.index:
                final_prices[symbol] = df.loc[final_timestamp, 'Close']
        self.portfolio.update_equity(final_prices)
        
        # 计算组合绩效指标
        metrics = self._calculate_portfolio_metrics(
            portfolio_equity_curve, portfolio_trades, init_cash
        )
        
        # 构建结果
        results = {
            'portfolio': {
                'equity_curve': portfolio_equity_curve,
                'trades': portfolio_trades,
                'metrics': metrics,
                'cash_history': [e['cash'] for e in portfolio_equity_curve],
                'final_cash': self.portfolio.cash,
                'final_equity': self.portfolio.total_equity
            }
        }
        
        # 为每个交易对生成单独的结果
        for symbol, df in aligned_data.items():
            symbol_result = self._generate_symbol_result(
                symbol, df, symbol_states[symbol], aligned_data,
                portfolio_equity_curve, portfolio_trades, init_cash
            )
            results[symbol] = symbol_result
        
        self.results = results
        
        logger.info(f"投资组合回测完成")
        logger.info(f"最终总权益: {self.portfolio.total_equity:.2f}")
        logger.info(f"总收益率: {metrics['total_return']:.2f}%")
        logger.info(f"总交易次数: {metrics['total_trades']}")
        
        return results
    
    def _align_data(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """对齐所有数据的时间索引"""
        aligned = {}
        
        # 找到共同的时间范围
        start_times = [df.index[0] for df in data.values()]
        end_times = [df.index[-1] for df in data.values()]
        
        common_start = max(start_times)
        common_end = min(end_times)
        
        logger.info(f"数据时间范围: {common_start} ~ {common_end}")
        
        # 截取共同时间范围
        for symbol, df in data.items():
            aligned_df = df[(df.index >= common_start) & (df.index <= common_end)].copy()
            aligned[symbol] = aligned_df
            logger.info(f"  {symbol}: {len(aligned_df)} 条数据")
        
        return aligned
    
    def _get_common_index(self, data: Dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
        """获取统一的时间索引"""
        # 使用第一个交易对的时间索引作为基准
        first_symbol = list(data.keys())[0]
        index = data[first_symbol].index
        # 确保返回 DatetimeIndex 类型
        if isinstance(index, pd.DatetimeIndex):
            return index
        return pd.DatetimeIndex(index)
    
    def _generate_signals(self, df: pd.DataFrame, symbol: str) -> Dict[str, pd.Series]:
        """
        生成交易信号
        
        通过调用策略的 on_bar 方法来生成信号，确保策略逻辑被正确执行。
        每个交易对使用独立的策略实例。
        """
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        
        # 为每个交易对创建独立的策略实例
        # 复制当前策略的参数
        strategy_params = getattr(self.strategy, 'params', {})
        
        # 尝试创建新的策略实例
        try:
            strategy_class = self.strategy.__class__
            symbol_strategy = strategy_class(strategy_params)
        except Exception as e:
            logger.warning(f"无法为 {symbol} 创建独立策略实例，使用共享实例: {e}")
            symbol_strategy = self.strategy
        
        # 初始化策略
        symbol_strategy.on_init()
        
        last_bar = None
        for idx, row in df.iterrows():
            bar = {
                'datetime': idx,
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row['Volume']),
                'symbol': symbol
            }
            last_bar = bar
            
            # 调用策略的 on_bar 方法
            symbol_strategy.on_bar(bar)
            
            # 检查策略是否产生了交易信号（使用 getattr 避免类型检查错误）
            last_order = getattr(symbol_strategy, 'last_order', None)
            if last_order and isinstance(last_order, dict):
                direction = last_order.get('direction', '')
                if direction in ['buy', 'long']:
                    entries.loc[idx] = True
                elif direction in ['sell', 'short', 'close']:
                    exits.loc[idx] = True
        
        # 回测结束强制平仓
        if last_bar is not None:
            symbol_strategy.on_stop(last_bar)
        
        return {'entries': entries, 'exits': exits}
    
    def _calculate_portfolio_metrics(
        self,
        equity_curve: List[Dict],
        trades: List[Dict],
        init_cash: float
    ) -> Dict[str, float]:
        """计算组合绩效指标"""
        if not equity_curve:
            return {}
        
        equities = [e['equity'] for e in equity_curve]
        final_equity = equities[-1]
        total_return = (final_equity - init_cash) / init_cash * 100 if init_cash > 0 else 0
        
        # 计算最大回撤
        max_drawdown = 0.0
        peak = equities[0]
        for equity in equities:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak * 100 if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 计算夏普比率
        returns = []
        for i in range(1, len(equities)):
            if equities[i-1] > 0:
                ret = (equities[i] - equities[i-1]) / equities[i-1]
                returns.append(ret)
        
        sharpe_ratio = 0.0
        if returns and np.std(returns) > 0:
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)
        
        # 统计交易
        total_trades = len([t for t in trades if 'pnl' in t])
        winning_trades = len([t for t in trades if t.get('pnl', 0) > 0])
        win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t.get('pnl', 0) for t in trades if 'pnl' in t)
        total_fees = sum(t.get('fees', 0) for t in trades)
        
        return {
            'total_return': total_return,
            'total_pnl': total_pnl,
            'final_equity': final_equity,
            'initial_equity': init_cash,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'total_fees': total_fees
        }
    
    def _generate_symbol_result(
        self,
        symbol: str,
        df: pd.DataFrame,
        state: Dict,
        all_data: Dict[str, pd.DataFrame],
        portfolio_equity: List[Dict],
        all_trades: List[Dict],
        init_cash: float
    ) -> Dict[str, Any]:
        """生成单个交易对的结果"""
        # 筛选该交易对的交易
        symbol_trades = [t for t in all_trades if t['symbol'] == symbol]
        
        # 计算该交易对的盈亏
        symbol_pnl = sum(t.get('pnl', 0) for t in symbol_trades if 'pnl' in t)
        
        # 构建结果
        result = {
            'symbol': symbol,
            'data': df,
            'trades': symbol_trades,
            'orders': state['orders'],
            'metrics': {
                'total_pnl': symbol_pnl,
                'trade_count': len([t for t in symbol_trades if 'pnl' in t])
            }
        }
        
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """获取回测摘要"""
        if self.results is None:
            return {}
        
        portfolio = self.results.get('portfolio', {})
        metrics = portfolio.get('metrics', {})
        
        return {
            'symbols': [k for k in self.results.keys() if k != 'portfolio'],
            'total_trades': metrics.get('total_trades', 0),
            'total_pnl': metrics.get('total_pnl', 0.0),
            'total_return': metrics.get('total_return', 0.0),
            'final_equity': metrics.get('final_equity', 0.0),
            'max_drawdown': metrics.get('max_drawdown', 0.0),
            'sharpe_ratio': metrics.get('sharpe_ratio', 0.0)
        }
