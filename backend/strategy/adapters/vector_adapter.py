# 向量回测适配器
# 将 StrategyCore 适配到 VectorEngine

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from loguru import logger
from strategy.core.vector_engine import VectorEngine
from strategy.core.strategy_base import StrategyBase


class VectorBacktestAdapter:
    """
    向量回测适配器
    将 StrategyBase 适配到 VectorEngine
    """
    
    def __init__(self, strategy: StrategyBase):
        """
        初始化适配器
        
        参数：
        - strategy: 策略实例
        """
        self.strategy = strategy
        self.engine = VectorEngine()
        self.results = None
    
    def run_backtest(self, data: Dict[str, pd.DataFrame], 
                    init_cash: float = 100000.0,
                    fees: float = 0.001,
                    slippage: float = 0.0001) -> Dict[str, Any]:
        """
        运行向量回测
        
        参数：
        - data: 多交易对数据字典 {symbol: DataFrame}
        - init_cash: 初始资金
        - fees: 手续费率
        - slippage: 滑点
        
        返回：
        - dict: 回测结果
        """
        results = {}
        
        for symbol, df in data.items():
            logger.info(f"开始回测交易对: {symbol}")
            
            # 初始化策略
            self.strategy.on_init()
            
            # 运行策略获取信号
            signals = self._generate_signals(df, symbol)
            
            # 准备价格数组，确保数据类型为 float64
            price = df['Close'].values.astype(np.float64).reshape(-1, 1)

            # 获取策略的仓位大小
            strategy_position_size = getattr(self.strategy, 'position_size', 1.0)

            # 运行向量回测
            result = self.engine.run_backtest(
                price=price,
                entries=signals['entries'].values.astype(np.bool_).reshape(-1, 1),
                exits=signals['exits'].values.astype(np.bool_).reshape(-1, 1),
                init_cash=init_cash,
                fees=fees,
                slippage=slippage,
                position_size=strategy_position_size
            )
            
            # 添加交易对信息
            result['symbol'] = symbol
            result['data'] = df
            
            # 添加策略的订单和指标数据
            result['orders'] = list(self.strategy.orders.values())
            result['indicators'] = self.strategy.indicators
            result['strategy_trades'] = self.strategy.trades
            
            # 新增：添加指标元数据（如果策略实现了get_indicators_info方法）
            if hasattr(self.strategy, 'get_indicators_info'):
                result['indicators_info'] = self.strategy.get_indicators_info()
            
            # 新增：添加当前指标值（如果策略实现了get_indicator_values方法）
            if hasattr(self.strategy, 'get_indicator_values'):
                result['indicator_values'] = self.strategy.get_indicator_values()
            
            # 新增：添加风险控制信息
            result['risk_control'] = {
                'stop_loss': self.strategy.stop_loss,
                'take_profit': self.strategy.take_profit,
                'max_position_size': self.strategy.max_position_size,
                'max_open_positions': self.strategy.max_open_positions,
                'cooldown_period': self.strategy.cooldown_period,
                'max_drawdown': self.strategy.max_drawdown,
                'leverage_enabled': self.strategy.leverage_enabled,
                'default_leverage': self.strategy.default_leverage
            }
            
            # 新增：生成资金曲线数据（包含实际盈亏和浮动盈亏）
            equity_curve = self._generate_equity_curve(result, df)
            result['equity_curve'] = equity_curve
            
            # 新增：格式化交易记录
            trades = self._format_trades(result, df)
            result['trades'] = trades
            
            # 新增：添加盈亏统计（如果策略支持）
            pnl_stats = {}
            if hasattr(self.strategy, 'realized_pnl'):
                pnl_stats['realized_pnl'] = self.strategy.realized_pnl
            if hasattr(self.strategy, 'unrealized_pnl'):
                pnl_stats['unrealized_pnl'] = self.strategy.unrealized_pnl
            if hasattr(self.strategy, 'total_trades'):
                pnl_stats['total_trades'] = self.strategy.total_trades
            if hasattr(self.strategy, 'winning_trades'):
                pnl_stats['winning_trades'] = self.strategy.winning_trades
                if self.strategy.total_trades > 0:
                    pnl_stats['win_rate'] = self.strategy.winning_trades / self.strategy.total_trades
            
            if pnl_stats:
                result['pnl_stats'] = pnl_stats
                logger.info(f"【盈亏统计】实际盈亏: {pnl_stats.get('realized_pnl', 0):.2f}, "
                           f"浮动盈亏: {pnl_stats.get('unrealized_pnl', 0):.2f}")
            
            results[symbol] = result
            
            logger.info(f"回测完成: {symbol}, 总盈亏: {result['metrics']['total_pnl']:.2f}, 夏普比率: {result['metrics']['sharpe_ratio']:.4f}")
        
        self.results = results
        return results
    
    def _generate_signals(self, df: pd.DataFrame, symbol: str) -> Dict[str, pd.Series]:
        """
        生成交易信号
        
        参数：
        - df: K线数据
        - symbol: 交易对符号
        
        返回：
        - dict: 包含 entries 和 exits 的信号
        """
        # 调用策略的 on_bar 方法生成信号
        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        
        # 遍历每根 K线
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
            self.strategy.on_bar(bar)

            # 检查是否有订单
            if hasattr(self.strategy, 'last_order'):
                order = self.strategy.last_order
                if order['direction'] in ['buy', 'long']:
                    entries[idx] = True
                elif order['direction'] in ['sell', 'short']:
                    exits[idx] = True
                # 清除 last_order 防止重复检测
                delattr(self.strategy, 'last_order')
        
        # 回测结束，调用 on_stop 进行强制平仓
        if last_bar is not None:
            logger.info(f"【回测结束】调用策略 on_stop 进行强制平仓: {symbol}")
            self.strategy.on_stop(last_bar)
        
        return {
            'entries': entries,
            'exits': exits
        }
    
    def optimize_parameters(self, data: Dict[str, pd.DataFrame], 
                       param_ranges: Dict[str, list],
                       metric: str = 'sharpe_ratio') -> Dict[str, Any]:
        """
        参数优化
        
        参数：
        - data: 多交易对数据
        - param_ranges: 参数范围
        - metric: 优化指标
        
        返回：
        - dict: 最优参数组合
        """
        from itertools import product
        
        # 生成参数组合
        param_combinations = list(product(*param_ranges.values()))
        
        best_result = None
        best_score = -float('inf')
        
        total_combinations = len(param_combinations)
        logger.info(f"开始参数优化，总组合数: {total_combinations}")
        
        for idx, params in enumerate(param_combinations):
            param_dict = dict(zip(param_ranges.keys(), params))
            
            # 设置策略参数
            self.strategy.params.update(param_dict)
            
            # 运行回测
            results = self.run_backtest(data)
            
            # 计算平均分数
            scores = [r['metrics'][metric] for r in results.values()]
            avg_score = np.mean(scores)
            
            if avg_score > best_score:
                best_score = avg_score
                best_result = {
                    'params': param_dict,
                    'score': avg_score,
                    'results': results
                }
            
            if (idx + 1) % 10 == 0:
                logger.info(f"参数优化进度: {idx + 1}/{total_combinations}, 当前最优分数: {best_score:.4f}")
        
        logger.info(f"参数优化完成，最优参数: {best_result['params']}, 最优分数: {best_result['score']:.4f}")
        return best_result
    
    def _generate_equity_curve(self, result: Dict[str, Any], df: pd.DataFrame) -> list:
        """
        生成资金曲线数据
        
        参数：
        - result: 回测结果
        - df: K线数据
        
        返回：
        - list: 资金曲线数据点列表
        """
        positions = result['positions']
        cash = result['cash']
        price = df['Close'].values
        
        equity_curve = []
        max_equity = init_cash = float(cash[0]) if len(cash) > 0 else 100000.0
        
        # 确保 positions 是 numpy 数组
        if not isinstance(positions, np.ndarray):
            positions = np.array(positions)
        
        for i in range(len(positions)):
            # 计算当前权益
            equity_value = float(cash[i]) if i < len(cash) else float(cash[-1])
            
            # 计算持仓价值
            if i < len(price):
                pos = float(positions[i, 0]) if positions.ndim > 1 else float(positions[i])
                position_value = pos * float(price[i])
            else:
                position_value = 0.0
            
            total_equity = equity_value + position_value
            
            # 更新最大权益
            if total_equity > max_equity:
                max_equity = total_equity
            
            # 计算回撤
            drawdown = max_equity - total_equity
            drawdown_pct = (drawdown / max_equity) * 100 if max_equity > 0 else 0
            
            # 获取时间戳
            timestamp = df.index[i]
            if isinstance(timestamp, pd.Timestamp):
                timestamp_ms = int(timestamp.timestamp() * 1000)
            else:
                timestamp_ms = int(timestamp)
            
            equity_curve.append({
                'timestamp': timestamp_ms,
                'datetime': timestamp.isoformat() if isinstance(timestamp, pd.Timestamp) else str(timestamp),
                'equity': round(float(total_equity), 2),
                'cash': round(float(equity_value), 2),
                'position_value': round(float(position_value), 2),
                'drawdown': round(float(drawdown), 2),
                'drawdown_pct': round(float(drawdown_pct), 4)
            })
        
        return equity_curve
    
    def _format_trades(self, result: Dict[str, Any], df: pd.DataFrame) -> list:
        """
        格式化交易记录

        参数：
        - result: 回测结果
        - df: K线数据

        返回：
        - list: 格式化后的交易记录列表
        """
        trades = []

        # 从引擎获取交易记录
        engine_trades = result.get('trades', [])

        if isinstance(engine_trades, np.ndarray) and len(engine_trades) > 0:
            # 处理引擎返回的交易记录
            # 引擎返回的格式: [{'step': i, 'direction': 'long'/'short', 'size': ..., 'price': ..., 'value': ..., 'fees': ..., 'pnl': ...}]
            # 需要配对入场和出场记录

            entries = []  # 入场记录
            exits = []    # 出场记录

            for i, trade in enumerate(engine_trades):
                if isinstance(trade, dict):
                    direction = trade.get('direction', 'long')
                    size = float(trade.get('size', 0))
                    price = float(trade.get('price', 0))
                    fees = float(trade.get('fees', 0))
                    step = int(trade.get('step', i))

                    # 获取时间戳
                    timestamp = ''
                    if step < len(df.index):
                        ts = df.index[step]
                        if hasattr(ts, 'isoformat'):
                            timestamp = ts.isoformat()
                        else:
                            timestamp = str(ts)

                    # size > 0 表示入场，size < 0 表示出场
                    if size > 0:
                        entries.append({
                            'step': step,
                            'time': timestamp,
                            'price': price,
                            'size': size,
                            'fees': fees,
                            'direction': direction
                        })
                    else:
                        exits.append({
                            'step': step,
                            'time': timestamp,
                            'price': price,
                            'size': abs(size),
                            'fees': fees,
                            'direction': direction
                        })

            # 配对交易（简单配对：按顺序配对入场和出场）
            trade_id = 0
            min_len = min(len(entries), len(exits))
            for i in range(min_len):
                entry = entries[i]
                exit = exits[i]

                total_fees = entry['fees'] + exit['fees']
                direction = entry['direction']

                if direction == 'long':
                    realized_pnl = (exit['price'] - entry['price']) * entry['size'] - total_fees
                    return_pct = ((exit['price'] - entry['price']) / entry['price']) * 100 if entry['price'] > 0 else 0
                else:  # short
                    realized_pnl = (entry['price'] - exit['price']) * entry['size'] - total_fees
                    return_pct = ((entry['price'] - exit['price']) / entry['price']) * 100 if entry['price'] > 0 else 0

                trades.append({
                        'trade_id': trade_id,
                        'entry_time': entry['time'],
                        'exit_time': exit['time'],
                        'entry_price': entry['price'],
                        'exit_price': exit['price'],
                        'price': entry['price'],  # 兼容性：保持 price 字段
                        'size': entry['size'],
                        'pnl': round(realized_pnl, 2),
                        'return_pct': round(return_pct, 4),
                        'direction': direction,
                        'fees': round(total_fees, 2)
                    })
                trade_id += 1

        # 如果没有引擎交易记录，从订单生成交易记录
        if not trades and 'orders' in result:
            orders = result['orders']
            for i in range(0, len(orders) - 1, 2):
                if i + 1 < len(orders):
                    entry_order = orders[i]
                    exit_order = orders[i + 1]

                    entry_price = float(entry_order.get('price', 0))
                    exit_price = float(exit_order.get('price', 0))
                    size = float(entry_order.get('size', 0.1))

                    pnl = (exit_price - entry_price) * size
                    return_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0

                    trades.append({
                        'trade_id': i // 2,
                        'entry_time': entry_order.get('timestamp', ''),
                        'exit_time': exit_order.get('timestamp', ''),
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'price': entry_price,  # 兼容性：保持 price 字段
                        'size': size,
                        'pnl': round(pnl, 2),
                        'return_pct': round(return_pct, 4),
                        'direction': entry_order.get('direction', 'buy'),
                        'fees': 0.0
                    })

        return trades
    
    def get_equity_curve(self, symbol: str) -> pd.Series:
        """
        获取权益曲线
        
        参数：
        - symbol: 交易对
        
        返回：
        - pd.Series: 权益曲线
        """
        if self.results is None or symbol not in self.results:
            return pd.Series()
        
        result = self.results[symbol]
        equity_curve = result.get('equity_curve', [])
        
        if not equity_curve:
            return pd.Series()
        
        # 从equity_curve提取权益值
        equity_values = [point['equity'] for point in equity_curve]
        index = pd.to_datetime([point['datetime'] for point in equity_curve])
        
        return pd.Series(equity_values, index=index)
    
    def get_trades(self, symbol: str) -> pd.DataFrame:
        """
        获取交易记录
        
        参数：
        - symbol: 交易对
        
        返回：
        - pd.DataFrame: 交易记录
        """
        if self.results is None or symbol not in self.results:
            return pd.DataFrame()
        
        result = self.results[symbol]
        trades = result['trades']
        
        if len(trades) == 0:
            return pd.DataFrame()

        # trades 可能是列表或 numpy 数组
        if isinstance(trades, np.ndarray):
            return pd.DataFrame(trades.tolist())
        else:
            return pd.DataFrame(trades)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        获取回测摘要
        
        返回：
        - dict: 回测摘要
        """
        if self.results is None:
            return {}
        
        summary = {
            'symbols': list(self.results.keys()),
            'total_trades': 0,
            'total_pnl': 0.0,
            'total_fees': 0.0,
            'avg_sharpe': 0.0,
            'avg_win_rate': 0.0
        }
        
        for result in self.results.values():
            metrics = result['metrics']
            summary['total_trades'] += metrics['trade_count']
            summary['total_pnl'] += metrics['total_pnl']
            summary['total_fees'] += metrics['total_fees']
            summary['avg_sharpe'] += metrics['sharpe_ratio']
            summary['avg_win_rate'] += metrics['win_rate']
        
        n_symbols = len(self.results)
        if n_symbols > 0:
            summary['avg_sharpe'] /= n_symbols
            summary['avg_win_rate'] /= n_symbols
        
        return summary
