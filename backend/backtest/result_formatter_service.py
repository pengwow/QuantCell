"""
结果格式化服务模块

负责将回测引擎的原始结果转换为QuantCell标准格式，
包括单品种和多品种场景的结果格式化、绩效指标计算等。
"""

from datetime import datetime
from typing import Any, Dict, List
from utils.logger import get_logger, LogType


# 获取模块日志器
logger = get_logger(__name__, LogType.APPLICATION)


class ResultFormatterService:
    """
    回测结果格式化服务
    
    提供统一的结果格式化接口，支持：
    - 单品种事件驱动结果格式化
    - 多品种事件驱动结果格式化
    - 时间周期转换
    - 绩效指标计算
    
    使用示例：
        formatted = ResultFormatterService.format_event_results(
            results=raw_results,
            symbol="BTCUSDT",
            timeframe="1h",
            strategy_name="sma_cross"
        )
    """
    
    @staticmethod
    def convert_timeframe_to_event(timeframe: str) -> str:
        """
        将时间周期转换为事件驱动引擎格式
        
        Args:
            timeframe: 时间周期字符串（如 1h, 15m, 1d）
            
        Returns:
            str: 事件驱动引擎格式（如 1-HOUR, 15-MINUTE, 1-DAY）
        """
        mapping = {
            '1m': '1-MINUTE',
            '3m': '3-MINUTE',
            '5m': '5-MINUTE',
            '15m': '15-MINUTE',
            '30m': '30-MINUTE',
            '1h': '1-HOUR',
            '2h': '2-HOUR',
            '4h': '4-HOUR',
            '6h': '6-HOUR',
            '8h': '8-HOUR',
            '12h': '12-HOUR',
            '1d': '1-DAY',
            '3d': '3-DAY',
            '1w': '1-WEEK',
            '1M': '1-MONTH',
        }
        
        return mapping.get(timeframe, '1-HOUR')
    
    @staticmethod
    def format_event_results(
        results: dict,
        symbol: str,
        timeframe: str,
        strategy_name: str
    ) -> dict:
        """
        格式化事件驱动回测结果为QuantCell标准格式（单品种版本）
        
        Args:
            results: 事件驱动回测原始结果
            symbol: 品种符号
            timeframe: 时间周期
            strategy_name: 策略名称
            
        Returns:
            dict: 格式化的回测结果
        """
        key = f"{symbol}_{timeframe}"
        
        formatted = {
            key: {
                'symbol': symbol,
                'timeframe': timeframe,
                'metrics': results.get('metrics', {}),
                'trades': results.get('trades', []),
                'positions': results.get('positions', []),
                'equity_curve': results.get('equity_curve', []),
            }
        }
        
        # 添加全局账户信息
        formatted['account'] = results.get('account', {})
        
        # 添加投资组合汇总（单品种时与品种结果相同）
        formatted['portfolio'] = {
            'metrics': results.get('metrics', {}),
            'trades': results.get('trades', []),
            'equity_curve': results.get('equity_curve', []),
        }
        
        # 添加元数据
        now = datetime.now()
        formatted['_meta'] = {
            'engine': 'event',
            'strategy': strategy_name,
            'timestamp': int(now.timestamp()),
            'formatted_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        return formatted
    
    @staticmethod
    def format_event_results_multi(
        results: dict,
        symbols: List[str],
        timeframe: str,
        strategy_name: str,
        instruments: dict
    ) -> dict:
        """
        格式化多品种事件驱动回测结果
        
        Args:
            results: 事件驱动回测原始结果
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称
            instruments: Instrument映射
            
        Returns:
            dict: 格式化的多品种回测结果
        """
        formatted = {}
        
        # 为每个品种提取单独结果
        for symbol in symbols:
            key = f"{symbol}_{timeframe}"
            
            # 从组合级结果中提取该品种的指标
            portfolio_metrics = results.get('portfolio', {}).get('metrics', {})
            
            # 尝试从positions中过滤出该品种的持仓和交易
            all_positions = results.get('portfolio', {}).get('positions', [])
            symbol_positions = [p for p in all_positions if hasattr(p, 'symbol') and p.symbol == symbol]
            
            # 如果没有按品种分开的数据，使用组合级数据
            if not symbol_positions:
                symbol_positions = all_positions
            
            all_trades = results.get('portfolio', {}).get('trades', [])
            symbol_trades = [t for t in all_trades if hasattr(t, 'symbol') and t.symbol == symbol]
            if not symbol_trades:
                symbol_trades = all_trades
            
            equity_curve = results.get('portfolio', {}).get('equity_curve', [])
            
            formatted[key] = {
                'symbol': symbol,
                'timeframe': timeframe,
                'metrics': portfolio_metrics,
                'trades': symbol_trades,
                'positions': symbol_positions,
                'equity_curve': equity_curve,
            }
        
        # 添加全局账户信息
        formatted['account'] = results.get('account', {})
        
        # 添加投资组合汇总
        formatted['portfolio'] = {
            'metrics': results.get('portfolio', {}).get('metrics', {}),
            'trades': results.get('portfolio', {}).get('trades', []),
            'equity_curve': results.get('portfolio', {}).get('equity_curve', []),
        }
        
        # 添加元数据
        now = datetime.now()
        formatted['_meta'] = {
            'engine': 'event',
            'strategy': strategy_name,
            'symbols_count': len(symbols),
            'timestamp': int(now.timestamp()),
            'formatted_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        }
        
        logger.info(f"[ResultFormatterService] 多品种结果格式化完成，共 {len(symbols)} 个品种")
        
        return formatted
    
    @staticmethod
    def calculate_symbol_metrics(trades, positions, account):
        """
        计算单品种绩效指标
        
        Args:
            trades: 交易记录列表
            positions: 持仓记录列表
            account: 账户信息
            
        Returns:
            dict: 绩效指标字典
        """
        metrics = {}
        
        try:
            if not trades or len(trades) == 0:
                return {
                    'total_return': 0.0,
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'profit_factor': 0.0,
                    'max_drawdown': 0.0,
                    'sharpe_ratio': 0.0,
                }
            
            total_pnl = sum(getattr(t, 'pnl', getattr(t, 'realized_pnl', 0)) for t in trades)
            winning_trades = [t for t in trades if (getattr(t, 'pnl', 0) > 0)]
            losing_trades = [t for t in trades if (getattr(t, 'pnl', 0) <= 0)]
            
            win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
            
            total_wins = sum(getattr(t, 'pnl', 0) for t in winning_trades)
            total_losses = abs(sum(getattr(t, 'pnl', 0) for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
            
            initial_balance = getattr(account, 'starting_balance', 10000)
            final_balance = getattr(account, 'balance', initial_balance) + total_pnl
            total_return = ((final_balance - initial_balance) / initial_balance) * 100
            
            metrics = {
                'total_return': round(total_return, 2),
                'total_pnl': round(total_pnl, 2),
                'total_trades': len(trades),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': round(win_rate, 2),
                'profit_factor': round(profit_factor, 2),
            }
            
        except Exception as e:
            logger.warning(f"[ResultFormatterService] 计算单品种指标失败: {e}")
        
        return metrics
    
    @staticmethod
    def calculate_portfolio_metrics(trades, positions, equity_curve, symbols, account):
        """
        计算组合级别绩效指标
        
        Args:
            trades: 所有交易记录
            positions: 所有持仓记录
            equity_curve: 权益曲线数据
            symbols: 品种列表
            account: 账户信息
            
        Returns:
            dict: 组合级别绩效指标
        """
        from statistics import mean
        
        metrics = {}
        
        try:
            if not trades or len(trades) == 0:
                return {
                    'total_return': 0.0,
                    'total_trades': 0,
                    'win_rate': 0.0,
                    'avg_trade_return': 0.0,
                    'max_drawdown': 0.0,
                    'sharpe_ratio': 0.0,
                }
            
            total_pnl = sum(getattr(t, 'pnl', getattr(t, 'realized_pnl', 0)) for t in trades)
            winning_trades = [t for t in trades if (getattr(t, 'pnl', 0) > 0)]
            losing_trades = [t for t in trades if (getattr(t, 'pnl', 0) <= 0)]
            
            win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
            
            trade_returns = [getattr(t, 'pnl', 0) for t in trades]
            avg_trade = mean(trade_returns) if trade_returns else 0
            
            total_wins = sum(getattr(t, 'pnl', 0) for t in winning_trades)
            total_losses = abs(sum(getattr(t, 'pnl', 0) for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
            
            initial_balance = getattr(account, 'starting_balance', 10000)
            final_balance = getattr(account, 'balance', initial_balance) + total_pnl
            total_return = ((final_balance - initial_balance) / initial_balance) * 100
            
            # 计算最大回撤
            max_drawdown = 0.0
            if equity_curve and len(equity_curve) > 1:
                peak = equity_curve[0].get('Equity', equity_curve[0].get('equity', initial_balance))
                for eq in equity_curve[1:]:
                    eq_val = eq.get('Equity', eq.get('equity', 0))
                    if eq_val > peak:
                        peak = eq_val
                    drawdown = (peak - eq_val) / peak * 100 if peak > 0 else 0
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
            
            # 计算夏普比率（简化版）
            sharpe_ratio = 0.0
            if trade_returns and len(trade_returns) > 1:
                avg_return = mean(trade_returns)
                std_return = (sum((x - avg_return) ** 2 for x in trade_returns) / (len(trade_returns) - 1)) ** 0.5
                if std_return > 0:
                    risk_free_rate = 0.02 / 252  # 假设年化无风险利率2%，日化
                    sharpe_ratio = (avg_return - risk_free_rate) / std_return
            
            metrics = {
                'total_return': round(total_return, 2),
                'total_pnl': round(total_pnl, 2),
                'total_trades': len(trades),
                'symbols_count': len(symbols),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': round(win_rate, 2),
                'avg_trade_return': round(avg_trade, 4),
                'profit_factor': round(profit_factor, 2),
                'max_drawdown': round(max_drawdown, 2),
                'sharpe_ratio': round(sharpe_ratio, 4),
            }
            
        except Exception as e:
            logger.warning(f"[ResultFormatterService] 计算组合指标失败: {e}")
        
        return metrics
