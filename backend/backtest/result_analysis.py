# -*- coding: utf-8 -*-
"""
回测结果分析模块

提供回测结果的分析、序列化和可视化功能，包括：
- 结果统计分析
- 结果序列化（JSON/CSV）
- 结果加载
- 结果输出格式化
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

import numpy as np
import pandas as pd
from loguru import logger


class ResultAnalyzer:
    """回测结果分析器"""
    
    def analyze(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析回测结果
        
        参数：
            results: 回测结果字典，格式为 {symbol_timeframe: result} 或包含 portfolio 键
            
        返回：
            Dict[str, Any]: 分析后的结果摘要
        """
        # 检查是否是投资组合回测结果
        if 'portfolio' in results:
            return self._analyze_portfolio_results(results)
        
        # 传统单交易对回测结果
        summary = {
            'total_symbols': len(results),
            'total_trades': 0,
            'total_pnl': 0.0,
            'avg_win_rate': 0.0,
            'avg_sharpe': 0.0,
            'symbols': []
        }
        
        win_rates = []
        sharpe_ratios = []
        
        for key, result in results.items():
            symbol_summary = self._analyze_single_result(key, result)
            summary['symbols'].append(symbol_summary)
            
            # 累计统计
            summary['total_trades'] += symbol_summary['trade_count']
            summary['total_pnl'] += symbol_summary['total_pnl']
            
            if 'win_rate' in symbol_summary:
                win_rates.append(symbol_summary['win_rate'])
            if 'sharpe_ratio' in symbol_summary:
                sharpe_ratios.append(symbol_summary['sharpe_ratio'])
        
        # 计算平均值
        if win_rates:
            summary['avg_win_rate'] = sum(win_rates) / len(win_rates)
        if sharpe_ratios:
            summary['avg_sharpe'] = sum(sharpe_ratios) / len(sharpe_ratios)
        
        return summary
    
    def _analyze_portfolio_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """分析投资组合回测结果"""
        portfolio = results.get('portfolio', {})
        portfolio_metrics = portfolio.get('metrics', {})
        
        summary = {
            'is_portfolio': True,
            'total_symbols': len([k for k in results.keys() if k != 'portfolio']),
            'total_trades': portfolio_metrics.get('total_trades', 0),
            'total_pnl': portfolio_metrics.get('total_pnl', 0.0),
            'win_rate': portfolio_metrics.get('win_rate', 0.0),
            'sharpe_ratio': portfolio_metrics.get('sharpe_ratio', 0.0),
            'max_drawdown': portfolio_metrics.get('max_drawdown', 0.0),
            'total_return': portfolio_metrics.get('total_return', 0.0),
            'initial_equity': portfolio_metrics.get('initial_equity', 0.0),
            'final_equity': portfolio_metrics.get('final_equity', 0.0),
            'symbols': []
        }
        
        # 分析各交易对
        for key, result in results.items():
            if key == 'portfolio':
                continue
            
            symbol_summary = self._analyze_single_result(key, result)
            summary['symbols'].append(symbol_summary)
        
        return summary
    
    def _analyze_single_result(self, key: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """分析单个交易对的结果"""
        # 解析symbol和timeframe
        parts = key.split('_')
        symbol = parts[0] if parts else key
        timeframe = parts[1] if len(parts) > 1 else 'unknown'
        
        # 获取资金曲线
        cash = result.get('cash', [])
        init_cash = cash[0] if len(cash) > 0 else 0.0
        final_cash = cash[-1] if len(cash) > 0 else 0.0
        
        # 获取持仓
        positions = result.get('positions', [])
        if isinstance(positions, np.ndarray) and positions.ndim > 1:
            final_position = positions[-1, 0] if len(positions) > 0 else 0.0
        else:
            final_position = positions[-1] if len(positions) > 0 else 0.0
        
        # 获取交易数量
        trades = result.get('trades', [])
        trade_count = len(trades)
        
        # 获取指标
        metrics = result.get('metrics', {})
        
        return {
            'key': key,
            'symbol': symbol,
            'timeframe': timeframe,
            'init_cash': float(init_cash),
            'final_cash': float(final_cash),
            'final_position': float(final_position),
            'trade_count': trade_count,
            'total_pnl': float(metrics.get('total_pnl', 0)),
            'win_rate': float(metrics.get('win_rate', 0)),
            'sharpe_ratio': float(metrics.get('sharpe_ratio', 0)),
            'max_drawdown': float(metrics.get('max_drawdown', 0)),
            'profit_factor': float(metrics.get('profit_factor', 0)),
            'metrics': metrics
        }
    
    def calculate_statistics(self, trades: List[Dict], equity_curve: List[Dict]) -> Dict[str, Any]:
        """
        计算交易统计指标
        
        参数：
            trades: 交易列表
            equity_curve: 资金曲线
            
        返回：
            Dict[str, Any]: 统计指标
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_profit': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'max_consecutive_wins': 0,
                'max_consecutive_losses': 0
            }
        
        # 计算盈亏
        profits = []
        losses = []
        
        for trade in trades:
            pnl = trade.get('pnl', 0) or trade.get('PnL', 0)
            if pnl > 0:
                profits.append(pnl)
            elif pnl < 0:
                losses.append(abs(pnl))
        
        total_trades = len(trades)
        winning_trades = len(profits)
        losing_trades = len(losses)
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        avg_profit = sum(profits) / len(profits) if profits else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        
        total_profit = sum(profits)
        total_loss = sum(losses)
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_profit': total_profit,
            'total_loss': total_loss
        }


class ResultSerializer:
    """结果序列化器"""
    
    def to_json(self, results: Dict[str, Any], file_path: str) -> bool:
        """
        将结果保存为JSON
        
        参数：
            results: 回测结果
            file_path: 文件路径
            
        返回：
            bool: 是否成功
        """
        try:
            # 序列化结果
            serializable_results = self._make_serializable(results)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True) if os.path.dirname(file_path) else None
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"结果已保存到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存JSON失败: {e}")
            return False
    
    def to_csv(self, results: Dict[str, Any], file_path: str) -> bool:
        """
        将结果保存为CSV
        
        参数：
            results: 回测结果
            file_path: 文件路径
            
        返回：
            bool: 是否成功
        """
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True) if os.path.dirname(file_path) else None
            
            # 写入CSV
            with open(file_path, 'w', encoding='utf-8') as f:
                # 写入表头
                f.write("Symbol,Cash,FinalPosition,TradeCount,")
                f.write("TotalPnl,TotalFees,WinRate,SharpeRatio,FinalEquity\n")
                
                # 写入数据
                for key, result in results.items():
                    metrics = result.get('metrics', {})
                    cash = result.get('cash', [])
                    positions = result.get('positions', [])
                    
                    init_cash = cash[0] if len(cash) > 0 else 0.0
                    
                    if isinstance(positions, np.ndarray) and positions.ndim > 1:
                        final_position = positions[-1, 0] if len(positions) > 0 else 0.0
                    else:
                        final_position = positions[-1] if len(positions) > 0 else 0.0
                    
                    trades = result.get('trades', [])
                    
                    f.write(f"{key},")
                    f.write(f"{float(init_cash):.2f},")
                    f.write(f"{float(final_position):.4f},")
                    f.write(f"{len(trades)},")
                    f.write(f"{float(metrics.get('total_pnl', 0)):.2f},")
                    f.write(f"{float(metrics.get('total_fees', 0)):.2f},")
                    f.write(f"{float(metrics.get('win_rate', 0)):.4f},")
                    f.write(f"{float(metrics.get('sharpe_ratio', 0)):.4f},")
                    f.write(f"{float(metrics.get('final_equity', 0)):.2f}\n")
            
            logger.info(f"结果已保存到: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存CSV失败: {e}")
            return False
    
    def from_json(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        从JSON加载结果
        
        参数：
            file_path: 文件路径
            
        返回：
            Optional[Dict[str, Any]]: 加载的结果
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载JSON失败: {e}")
            return None
    
    def _make_serializable(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """将结果转换为可序列化的格式"""
        serializable = {}
        
        for key, result in results.items():
            serializable[key] = self._serialize_single_result(result)
        
        return serializable
    
    def _serialize_single_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """序列化单个结果"""
        serialized = {}

        # 复制基本字段
        for k, v in result.items():
            if k in ['cash', 'positions']:
                # NumPy数组转列表
                if isinstance(v, np.ndarray):
                    serialized[k] = v.tolist()
                else:
                    serialized[k] = v
            elif k == 'equity_curve':
                # 权益曲线列表（包含字典，可能有Timestamp）
                serialized[k] = self._serialize_equity_curve(v)
            elif k == 'metrics':
                # 指标字典
                serialized[k] = {
                    mk: float(mv) if isinstance(mv, (np.floating, float)) else
                       int(mv) if isinstance(mv, (np.integer, int)) else str(mv)
                    for mk, mv in v.items()
                }
            elif k in ['orders', 'trades', 'strategy_trades']:
                # 交易/订单列表
                serialized[k] = self._serialize_orders(v)
            elif k == 'indicators':
                # 指标
                serialized[k] = self._serialize_indicators(v)
            else:
                # 其他字段
                serialized[k] = self._serialize_value(v)

        return serialized

    def _serialize_equity_curve(self, equity_curve: List[Dict]) -> List[Dict]:
        """序列化权益曲线"""
        if not equity_curve:
            return []

        serialized = []
        for point in equity_curve:
            serialized_point = {}
            for key, value in point.items():
                if hasattr(value, 'isoformat'):  # Timestamp 类型
                    serialized_point[key] = value.isoformat()
                elif isinstance(value, datetime):
                    serialized_point[key] = value.isoformat()
                elif isinstance(value, (np.floating, float)):
                    serialized_point[key] = float(value)
                elif isinstance(value, (np.integer, int)):
                    serialized_point[key] = int(value)
                else:
                    serialized_point[key] = value
            serialized.append(serialized_point)
        return serialized
    
    def _serialize_orders(self, orders: List[Dict]) -> List[Dict]:
        """序列化订单/交易列表"""
        if not orders:
            return []

        serialized = []
        for idx, order in enumerate(orders):
            if not isinstance(order, dict):
                continue

            serialized_order = {
                'order_id': str(idx + 1),
                'direction': order.get('direction', ''),
                'price': float(order.get('price', 0)) if order.get('price') is not None else 0.0,
                'volume': float(order.get('volume') or order.get('size') or 0),
                'status': order.get('status', 'filled'),
                'timestamp': self._serialize_timestamp(order.get('timestamp')),
                'formatted_time': self._format_timestamp(order.get('timestamp'))
            }

            # 保留其他字段（如symbol, pnl, fees等）
            for key, value in order.items():
                if key not in serialized_order:
                    if hasattr(value, 'isoformat'):  # Timestamp类型
                        serialized_order[key] = value.isoformat()
                    elif isinstance(value, datetime):
                        serialized_order[key] = value.isoformat()
                    elif isinstance(value, (np.floating, float)):
                        serialized_order[key] = float(value)
                    elif isinstance(value, (np.integer, int)):
                        serialized_order[key] = int(value)
                    else:
                        serialized_order[key] = value

            serialized.append(serialized_order)

        return serialized
    
    def _serialize_indicators(self, indicators: Dict) -> Dict:
        """序列化指标"""
        if not indicators:
            return {}
        
        serialized = {}
        for key, value in indicators.items():
            if isinstance(value, dict):
                serialized[str(key)] = {
                    k: float(v) if isinstance(v, (np.floating, float)) else
                       int(v) if isinstance(v, (np.integer, int)) else
                       v.isoformat() if isinstance(v, datetime) else str(v)
                    for k, v in value.items()
                }
            elif isinstance(value, (np.floating, float)):
                serialized[str(key)] = float(value)
            elif isinstance(value, (np.integer, int)):
                serialized[str(key)] = int(value)
            elif isinstance(value, datetime):
                serialized[str(key)] = value.isoformat()
            else:
                serialized[str(key)] = str(value)
        
        return serialized
    
    def _serialize_timestamp(self, timestamp: Any) -> int:
        """序列化时间戳"""
        if timestamp is None:
            return 0
        
        if isinstance(timestamp, datetime):
            return int(timestamp.timestamp() * 1000)
        elif isinstance(timestamp, str):
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                return int(dt.timestamp() * 1000)
            except:
                return 0
        else:
            return int(timestamp) if timestamp else 0
    
    def _format_timestamp(self, timestamp: Any) -> str:
        """格式化时间戳"""
        if timestamp is None:
            return ""
        
        if isinstance(timestamp, datetime):
            return timestamp.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(timestamp, str):
            return timestamp
        else:
            try:
                dt = datetime.fromtimestamp(int(timestamp) / 1000)
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                return str(timestamp)
    
    def _serialize_value(self, value: Any) -> Any:
        """序列化值"""
        if isinstance(value, np.ndarray):
            return value.tolist()
        elif isinstance(value, (np.floating, float)):
            return float(value)
        elif isinstance(value, (np.integer, int)):
            return int(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif hasattr(value, 'isoformat'):  # 处理 Pandas Timestamp 等类型
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(v) for v in value]
        else:
            return str(value) if value is not None else None


def save_results(results: Dict[str, Any], output_file: str, output_format: str = 'json') -> bool:
    """
    保存回测结果
    
    参数：
        results: 回测结果
        output_file: 输出文件路径
        output_format: 输出格式 ('json' 或 'csv')
        
    返回：
        bool: 是否成功
    """
    serializer = ResultSerializer()
    
    if output_format.lower() == 'json':
        return serializer.to_json(results, output_file)
    elif output_format.lower() == 'csv':
        return serializer.to_csv(results, output_file)
    else:
        logger.error(f"不支持的输出格式: {output_format}")
        return False


def output_results(results: Dict[str, Any], output_format: str = 'json',
                   output_file: Optional[str] = None) -> str:
    """
    输出回测结果

    参数：
        results: 回测结果
        output_format: 输出格式
        output_file: 输出文件路径，None则自动生成

    返回：
        str: 输出文件路径
    """
    # 如果没有指定输出文件，自动生成
    if output_file is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"backtest_results_{timestamp}.{output_format}"

    # 分离正常结果和失败信息
    normal_results = {k: v for k, v in results.items() if not k.startswith('_')}
    download_failures = results.get('_download_failures', [])

    # 检查是否是投资组合回测结果
    is_portfolio = 'portfolio' in normal_results

    # 打印结果摘要
    print("\n" + "=" * 70)
    if is_portfolio:
        print("投资组合回测结果（多交易对共享资金池）")
    else:
        print("回测结果")
    print("=" * 70)

    # 投资组合回测：先打印组合整体信息
    if is_portfolio:
        portfolio = normal_results['portfolio']
        portfolio_metrics = portfolio.get('metrics', {})

        print("\n【投资组合整体表现】")
        print(f"  初始总资金: {portfolio_metrics.get('initial_equity', 0):.2f}")
        print(f"  最终总权益: {portfolio_metrics.get('final_equity', 0):.2f}")
        print(f"  总收益率: {portfolio_metrics.get('total_return', 0):.2f}%")
        print(f"  总盈亏: {portfolio_metrics.get('total_pnl', 0):.2f}")
        print(f"  总交易次数: {portfolio_metrics.get('total_trades', 0)}")
        print(f"  胜率: {portfolio_metrics.get('win_rate', 0):.2f}%")
        print(f"  最大回撤: {portfolio_metrics.get('max_drawdown', 0):.2f}%")
        print(f"  夏普比率: {portfolio_metrics.get('sharpe_ratio', 0):.4f}")
        print(f"  总手续费: {portfolio_metrics.get('total_fees', 0):.2f}")

        print("\n" + "-" * 70)
        print("各交易对表现")
        print("-" * 70)

    # 打印成功回测的结果
    for key, result in normal_results.items():
        if key == 'portfolio':
            continue

        print(f"\n交易对: {key}")

        # 投资组合回测显示不同的信息
        if is_portfolio:
            # 从该交易对的结果中获取交易记录和盈亏
            symbol_trades = result.get('trades', [])
            symbol_metrics = result.get('metrics', {})
            symbol_pnl = symbol_metrics.get('total_pnl', 0)
            # 统一统计口径：统计所有交易（与portfolio的total_trades一致）
            symbol_trade_count = len(symbol_trades)
            print(f"  贡献盈亏: {symbol_pnl:.2f}")
            print(f"  交易次数: {symbol_trade_count}")
        else:
            # 传统回测显示完整信息
            # 资金信息
            cash = result.get('cash', [])
            init_cash = cash[0] if len(cash) > 0 else 0.0
            final_cash = cash[-1] if len(cash) > 0 else 0.0
            print(f"  初始资金: {init_cash:.2f}")
            print(f"  最终现金: {final_cash:.2f}")

            # 持仓信息
            positions = result.get('positions', [])
            if isinstance(positions, np.ndarray) and positions.ndim > 1:
                final_position = positions[-1, 0] if len(positions) > 0 else 0.0
            else:
                final_position = positions[-1] if len(positions) > 0 else 0.0
            print(f"  最终持仓: {final_position:.4f}")

            # 交易数量
            trades = result.get('trades', [])
            print(f"  交易数量: {len(trades)}")

            # 指标
            metrics = result.get('metrics', {})
            print("\n  绩效指标:")
            for metric_key, metric_value in metrics.items():
                if isinstance(metric_value, float):
                    print(f"    {metric_key}: {metric_value:.4f}")
                else:
                    print(f"    {metric_key}: {metric_value}")

    # 打印数据加载失败信息
    if download_failures:
        print("\n" + "=" * 70)
        print("数据加载失败列表")
        print("=" * 70)

        # 按失败类型分组
        no_data_failures = [f for f in download_failures if f.get('failure_type') == 'no_data_available']
        other_failures = [f for f in download_failures if f.get('failure_type') != 'no_data_available']

        if no_data_failures:
            print(f"\n⚠️ 数据源无可用数据 ({len(no_data_failures)} 个):")
            for failure in no_data_failures:
                print(f"  - {failure['symbol']} {failure['timeframe']}: {failure['reason']}")

        if other_failures:
            print(f"\n❌ 其他错误 ({len(other_failures)} 个):")
            for failure in other_failures:
                print(f"  - {failure['symbol']} {failure['timeframe']}: {failure['reason']}")

    # 打印统计摘要
    print("\n" + "=" * 70)
    print("统计摘要")
    print("=" * 70)
    if is_portfolio:
        symbol_count = len([k for k in normal_results.keys() if k != 'portfolio'])
        print(f"  交易对数量: {symbol_count} 个")
        print(f"  初始总资金: {portfolio_metrics.get('initial_equity', 0):.2f} (共享资金池)")
        print(f"  最终总权益: {portfolio_metrics.get('final_equity', 0):.2f}")
    else:
        print(f"  成功回测: {len(normal_results)} 个货币对")
    if download_failures:
        print(f"  加载失败: {len(download_failures)} 个货币对")
        print(f"    - 无可用数据: {len([f for f in download_failures if f.get('failure_type') == 'no_data_available'])} 个")
        print(f"    - 其他错误: {len([f for f in download_failures if f.get('failure_type') != 'no_data_available'])} 个")
    print("=" * 70)

    # 保存结果
    if save_results(results, output_file, output_format):
        print(f"\n结果已保存到: {output_file}")
    else:
        print(f"\n保存结果失败: {output_file}")

    return output_file


def load_results(input_file: str) -> Optional[Dict[str, Any]]:
    """
    加载回测结果
    
    参数：
        input_file: 输入文件路径
        
    返回：
        Optional[Dict[str, Any]]: 加载的结果
    """
    serializer = ResultSerializer()
    return serializer.from_json(input_file)
