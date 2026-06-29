"""
结果格式化服务模块（基于 axond 体系）

负责将回测引擎的原始结果转换为QuantCell标准格式，
包括单品种和多品种场景的结果格式化、绩效指标计算等。
支持 axond 回测引擎和事件驱动引擎的结果格式化。

作者: QuantCell Team
版本: 2.0.0
日期: 2026-06-29
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
        格式化多品种事件驱动回测结果（修复版）

        核心改进：
        1. 从 results['trades'] 和 results['positions'] 提取数据（而非 portfolio）
        2. 使用字典的 'symbol' 字段进行过滤（修复 hasattr 问题）
        3. 为每个品种独立计算 metrics

        Args:
            results: 事件驱动回测原始结果（来自 EventDrivenBacktestEngine._process_results()）
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称
            instruments: Instrument映射

        Returns:
            dict: 格式化的多品种回测结果
        """
        formatted = {}

        # ✅ 从正确的位置提取全局数据
        all_trades = results.get('trades', [])           # 来自 _process_results()
        all_positions = results.get('positions', [])      # 来自 _process_results()
        account = results.get('account', {})             # 账户信息
        global_metrics = results.get('metrics', {})     # 全局指标
        equity_curve = results.get('equity_curve', [])   # 权益曲线

        logger.info(f"[format_event_results_multi] 开始格式化，共 {len(symbols)} 个品种")
        logger.info(f"[format_event_results_multi] 总交易数: {len(all_trades)}, 总持仓数: {len(all_positions)}")

        # 为每个品种提取单独结果
        for symbol in symbols:
            key = f"{symbol}_{timeframe}"

            # ✅ 正确过滤：使用字典的 'symbol' 字段（修复 hasattr 问题）
            symbol_trades = [t for t in all_trades if isinstance(t, dict) and t.get('symbol') == symbol]
            symbol_positions = [p for p in all_positions if isinstance(p, dict) and p.get('symbol') == symbol]

            logger.debug(f"[{key}] 过滤结果: trades={len(symbol_trades)}, positions={len(symbol_positions)}")

            # ✅ 为每个品种独立计算 metrics
            symbol_metrics = ResultFormatterService.calculate_symbol_metrics(
                trades=symbol_trades,
                positions=symbol_positions,
                account=account
            )

            # ✅ 构建该品种的权益曲线（基于该品种的持仓变化）
            symbol_equity_curve = ResultFormatterService._extract_symbol_equity_curve(
                global_equity_curve=equity_curve,
                symbol=symbol,
                positions=symbol_positions
            )

            formatted[key] = {
                'symbol': symbol,
                'timeframe': timeframe,
                'metrics': symbol_metrics,          # ✅ 独立计算
                'trades': symbol_trades,            # ✅ 已正确过滤
                'positions': symbol_positions,       # ✅ 已正确过滤
                'equity_curve': symbol_equity_curve, # ✅ 独立提取或使用全局
            }

        # 添加全局账户信息
        formatted['account'] = account

        # 添加投资组合汇总（包含所有品种的数据）
        formatted['portfolio'] = {
            'metrics': global_metrics,              # 使用全局计算的指标
            'trades': all_trades,                   # 所有交易
            'positions': all_positions,             # 所有持仓
            'equity_curve': equity_curve,           # 全局权益曲线
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
    def _extract_symbol_equity_curve(global_equity_curve: List[Dict], symbol: str, positions: List[Dict]) -> List[Dict]:
        """
        提取单个品种的权益曲线

        如果无法按品种分离，则返回全局权益曲线（因为所有品种共享同一账户）

        Args:
            global_equity_curve: 全局权益曲线
            symbol: 品种名称
            positions: 该品种的持仓列表

        Returns:
            List[Dict]: 权益曲线数据
        """
        # 当前实现：返回全局权益曲线
        # TODO: 未来可以基于持仓价值变化计算每个品种的贡献
        return global_equity_curve
    
    @staticmethod
    def calculate_symbol_metrics(trades, positions, account):
        """
        计算单品种绩效指标（支持字典和对象两种格式）

        Args:
            trades: 交易记录列表（字典或对象）
            positions: 持仓记录列表
            account: 账户信息（字典或对象）

        Returns:
            dict: 绩效指标字典
        """

        # ✅ 辅助函数：安全获取属性/键值（支持 dict 和 object）
        def get_attr_or_get(obj, attr, default=0):
            """安全获取属性值，兼容字典和对象"""
            if isinstance(obj, dict):
                return obj.get(attr, default)
            else:
                return getattr(obj, attr, default)

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
                    'total_pnl': 0.0,
                }

            # ✅ 使用安全的属性访问方法
            total_pnl = sum(
                get_attr_or_get(t, 'pnl', get_attr_or_get(t, 'realized_pnl', 0))
                for t in trades
            )
            winning_trades = [t for t in trades if (get_attr_or_get(t, 'pnl', 0) > 0)]
            losing_trades = [t for t in trades if (get_attr_or_get(t, 'pnl', 0) <= 0)]

            win_rate = len(winning_trades) / len(trades) * 100 if trades else 0

            total_wins = sum(get_attr_or_get(t, 'pnl', 0) for t in winning_trades)
            total_losses = abs(sum(get_attr_or_get(t, 'pnl', 0) for t in losing_trades))
            profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

            # ✅ 使用安全的属性访问方法
            initial_balance = get_attr_or_get(account, 'starting_balance',
                             get_attr_or_get(account, 'initial_balance', 10000))
            final_balance = get_attr_or_get(account, 'balance', initial_balance) + total_pnl
            total_return = ((final_balance - initial_balance) / initial_balance) * 100

            metrics = {
                'total_return': round(total_return, 2),
                'total_pnl': round(total_pnl, 8),   # PnL保留8位精度
                'total_trades': len(trades),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': round(win_rate, 2),
                'profit_factor': round(profit_factor, 4),  # 盈亏比保留4位
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

    @staticmethod
    def format_axon_results(
        results: dict,
        symbol: str,
        timeframe: str,
        strategy_name: str,
    ) -> dict:
        """
        格式化 axond 回测引擎结果为 QuantCell 标准格式（单品种版本）

        Args:
            results: AxonBacktestEngine.run() 返回的结果字典
            symbol: 品种符号
            timeframe: 时间周期
            strategy_name: 策略名称

        Returns:
            dict: 格式化的回测结果（与事件驱动格式兼容）
        """
        key = f"{symbol}_{timeframe}"

        # axond 引擎结果通常包含: final_nav, total_pnl, max_drawdown,
        # orders_accepted, orders_rejected, fills
        metrics = {
            'final_nav': results.get('final_nav', 0.0),
            'total_pnl': results.get('total_pnl', 0.0),
            'max_drawdown': results.get('max_drawdown', 0.0),
            'orders_accepted': results.get('orders_accepted', 0),
            'orders_rejected': results.get('orders_rejected', 0),
            'fills': results.get('fills', 0),
            'total_return': ResultFormatterService._calc_return_from_pnl(
                results.get('total_pnl', 0.0),
                results.get('initial_capital', 100000.0),
            ),
        }

        formatted = {
            key: {
                'symbol': symbol,
                'timeframe': timeframe,
                'metrics': metrics,
                'trades': results.get('trades', []),
                'positions': results.get('positions', []),
                'equity_curve': results.get('equity_curve', []),
            }
        }

        # 全局账户信息
        formatted['account'] = {
            'starting_balance': results.get('initial_capital', 100000.0),
            'final_nav': results.get('final_nav', 0.0),
            'total_pnl': results.get('total_pnl', 0.0),
        }

        # 投资组合汇总
        formatted['portfolio'] = {
            'metrics': metrics,
            'trades': results.get('trades', []),
            'equity_curve': results.get('equity_curve', []),
        }

        # 元数据
        now = datetime.now()
        formatted['_meta'] = {
            'engine': 'axon',
            'strategy': strategy_name,
            'timestamp': int(now.timestamp()),
            'formatted_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

        return formatted

    @staticmethod
    def format_axon_results_multi(
        results_by_symbol: dict,
        symbols: List[str],
        timeframe: str,
        strategy_name: str,
    ) -> dict:
        """
        格式化 axond 回测引擎多品种结果

        Args:
            results_by_symbol: 每个品种的结果字典 {symbol: result_dict}
            symbols: 品种列表
            timeframe: 时间周期
            strategy_name: 策略名称

        Returns:
            dict: 格式化的多品种回测结果
        """
        formatted = {}

        # 组合级指标汇总
        total_pnl = 0.0
        max_drawdown = 0.0
        total_nav = 0.0
        total_orders_accepted = 0
        total_orders_rejected = 0
        total_fills = 0
        total_initial_capital = 0.0
        all_trades = []
        all_positions = []
        all_equity_curve = []

        for symbol in symbols:
            key = f"{symbol}_{timeframe}"
            symbol_result = results_by_symbol.get(symbol, {})

            # 格式化单品种结果
            symbol_formatted = ResultFormatterService.format_axon_results(
                results=symbol_result,
                symbol=symbol,
                timeframe=timeframe,
                strategy_name=strategy_name,
            )
            formatted[key] = symbol_formatted[key]

            # 累加组合级指标
            total_pnl += symbol_result.get('total_pnl', 0.0)
            max_drawdown = max(max_drawdown, symbol_result.get('max_drawdown', 0.0))
            total_nav += symbol_result.get('final_nav', 0.0)
            total_orders_accepted += symbol_result.get('orders_accepted', 0)
            total_orders_rejected += symbol_result.get('orders_rejected', 0)
            total_fills += symbol_result.get('fills', 0)
            total_initial_capital += symbol_result.get('initial_capital', 100000.0)

            all_trades.extend(symbol_result.get('trades', []))
            all_positions.extend(symbol_result.get('positions', []))
            all_equity_curve.extend(symbol_result.get('equity_curve', []))

        # 计算组合级 metrics
        portfolio_metrics = {
            'final_nav': total_nav,
            'total_pnl': total_pnl,
            'max_drawdown': max_drawdown,
            'orders_accepted': total_orders_accepted,
            'orders_rejected': total_orders_rejected,
            'fills': total_fills,
            'symbols_count': len(symbols),
            'total_return': ResultFormatterService._calc_return_from_pnl(
                total_pnl, total_initial_capital
            ),
        }

        # 投资组合汇总
        formatted['account'] = {
            'starting_balance': total_initial_capital,
            'final_nav': total_nav,
            'total_pnl': total_pnl,
        }

        formatted['portfolio'] = {
            'metrics': portfolio_metrics,
            'trades': all_trades,
            'positions': all_positions,
            'equity_curve': all_equity_curve,
        }

        # 元数据
        now = datetime.now()
        formatted['_meta'] = {
            'engine': 'axon_multi',
            'strategy': strategy_name,
            'symbols_count': len(symbols),
            'timestamp': int(now.timestamp()),
            'formatted_time': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

        return formatted

    @staticmethod
    def _calc_return_from_pnl(total_pnl: float, initial_capital: float) -> float:
        """从 PnL 和初始资金计算回报率（百分比）

        Args:
            total_pnl: 总盈亏
            initial_capital: 初始资金

        Returns:
            float: 回报率（百分比）
        """
        if initial_capital <= 0:
            return 0.0
        return round((total_pnl / initial_capital) * 100.0, 2)
