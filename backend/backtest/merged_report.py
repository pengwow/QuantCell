# -*- coding: utf-8 -*-
"""
多交易对回测结果合并报告生成器

将多个交易对的回测结果合并为一个综合报告，包括：
- 合并的资金曲线（显示整体组合表现）
- 汇总交易分析
- 综合绩效指标
- 多交易对比分析
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.gridspec import GridSpec
import platform


def _setup_chinese_font():
    """设置matplotlib中文字体"""
    system = platform.system()
    
    chinese_fonts = {
        'Darwin': ['/System/Library/Fonts/PingFang.ttc',
                   '/System/Library/Fonts/STHeiti Light.ttc',
                   '/Library/Fonts/Arial Unicode.ttf'],
        'Linux': ['/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
                  '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'],
        'Windows': ['C:/Windows/Fonts/simhei.ttf',
                    'C:/Windows/Fonts/simsun.ttc',
                    'C:/Windows/Fonts/msyh.ttc']
    }
    
    font_found = False
    for font_path in chinese_fonts.get(system, []):
        if os.path.exists(font_path):
            try:
                font_prop = fm.FontProperties(fname=font_path)
                plt.rcParams['font.family'] = font_prop.get_name()
                plt.rcParams['axes.unicode_minus'] = False
                font_found = True
                break
            except:
                continue
    
    if not font_found:
        try:
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial Unicode MS', 'SimHei', 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
        except:
            pass
    
    return font_found


class MergedBacktestReport:
    """合并回测报告生成器"""
    
    def __init__(self, results_file: str):
        """
        初始化合并报告生成器
        
        参数：
            results_file: 回测结果JSON文件路径
        """
        self.results_file = results_file
        self.results = self._load_results()
        self.merged_data = None
        self.symbol_data = {}
        
    def _load_results(self) -> Dict[str, Any]:
        """加载回测结果"""
        with open(self.results_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def process_data(self) -> Dict[str, Any]:
        """
        处理并合并多交易对数据

        支持两种格式：
        1. 传统格式：每个交易对独立有cash数据
        2. 投资组合格式：portfolio包含equity_curve，各交易对共享资金池

        返回：
            Dict: 合并后的数据
        """
        print("=" * 70)
        print("处理多交易对回测数据")
        print("=" * 70)

        # 检查是否是投资组合回测结果
        is_portfolio = 'portfolio' in self.results

        if is_portfolio:
            return self._process_portfolio_data()
        else:
            return self._process_traditional_data()

    def _process_portfolio_data(self) -> Dict[str, Any]:
        """处理投资组合回测结果格式"""
        portfolio = self.results['portfolio']
        equity_curve = portfolio.get('equity_curve', [])
        trades = portfolio.get('trades', [])
        metrics = portfolio.get('metrics', {})

        if not equity_curve:
            raise ValueError("投资组合数据中没有权益曲线")

        print(f"\n处理投资组合数据:")
        print(f"  权益曲线点数: {len(equity_curve)}")

        # 从equity_curve提取资金曲线和时间戳
        cash_curve = []
        timestamps = []

        for point in equity_curve:
            if isinstance(point, dict):
                cash_curve.append(point.get('equity', 0))
                timestamps.append(point.get('datetime', ''))
            else:
                cash_curve.append(point)
                timestamps.append('')

        cash_curve = np.array(cash_curve)

        # 获取投资组合的整体指标（与回测结果输出一致）
        initial_equity = metrics.get('initial_equity', cash_curve[0] if len(cash_curve) > 0 else 100000.0)
        final_equity = metrics.get('final_equity', cash_curve[-1] if len(cash_curve) > 0 else 100000.0)
        total_pnl = metrics.get('total_pnl', final_equity - initial_equity)
        total_return = metrics.get('total_return', (total_pnl / initial_equity * 100) if initial_equity > 0 else 0)
        total_trades = metrics.get('total_trades', len(trades))
        win_rate = metrics.get('win_rate', 0)
        max_drawdown = metrics.get('max_drawdown', 0)
        sharpe_ratio = metrics.get('sharpe_ratio', 0)

        # 处理各交易对数据（用于显示）
        for symbol_key, result in self.results.items():
            if symbol_key.startswith('_') or symbol_key == 'portfolio':
                continue

            print(f"\n处理交易对: {symbol_key}")

            # 从该交易对的结果中获取交易记录（与result_analysis.py保持一致）
            symbol_trades = result.get('trades', [])

            # 对于投资组合回测，各交易对不显示独立的资金曲线
            # 而是显示该交易对贡献的盈亏
            symbol_metrics = result.get('metrics', {})
            symbol_pnl = symbol_metrics.get('total_pnl', 0)
            # 统一统计口径：统计所有交易（与portfolio的total_trades一致）
            symbol_trade_count = len(symbol_trades)

            self.symbol_data[symbol_key] = {
                'cash': [],  # 投资组合中各交易对没有独立的cash曲线
                'cash_curve': np.array([]),
                'timestamps': [],
                'trades': symbol_trades,
                'orders': [],
                'metrics': symbol_metrics,
                'init_cash': 0,  # 不显示独立初始资金
                'final_cash': symbol_pnl,  # 显示贡献的盈亏
                'trade_count': symbol_trade_count,
                'pnl_contribution': symbol_pnl  # 贡献的盈亏
            }

            print(f"  交易次数: {symbol_trade_count}")
            print(f"  贡献盈亏: {symbol_pnl:.2f}")

        # 使用portfolio的metrics作为合并指标（确保与回测结果输出一致）
        merged_metrics = {
            'total_return': total_return,
            'total_pnl': total_pnl,
            'final_equity': final_equity,
            'initial_equity': initial_equity,
            'win_rate': win_rate,
            'profit_factor': 0,  # 可以从metrics获取或计算
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'avg_trade': total_pnl / total_trades if total_trades > 0 else 0
        }

        self.merged_data = {
            'merged_cash': cash_curve.tolist(),
            'merged_timestamps': timestamps,
            'merged_metrics': merged_metrics,
            'all_trades': trades,
            'symbol_count': len(self.symbol_data),
            'is_portfolio': True  # 标记为投资组合格式
        }

        print(f"\n✓ 投资组合数据处理完成")
        print(f"  交易对数量: {len(self.symbol_data)}")
        print(f"  总交易次数: {total_trades}")
        print(f"  初始权益: {initial_equity:.2f}")
        print(f"  最终权益: {final_equity:.2f}")
        print(f"  总收益率: {total_return:.2f}%")

        return self.merged_data

    def _process_traditional_data(self) -> Dict[str, Any]:
        """处理传统回测结果格式"""
        # 提取每个交易对的数据
        symbol_cash_curves = {}
        symbol_timestamps = {}

        for symbol_key, result in self.results.items():
            if symbol_key.startswith('_'):
                continue

            print(f"\n处理交易对: {symbol_key}")

            cash = result.get('cash', [])
            trades = result.get('trades', [])
            orders = result.get('orders', [])
            metrics = result.get('metrics', {})
            data_str = result.get('data', '')

            if not cash:
                print(f"  警告: {symbol_key} 没有资金数据")
                continue

            # 从data字段提取时间戳
            timestamps = self._extract_timestamps(data_str, len(cash))

            # 构建资金曲线
            cash_curve = np.array(cash)
            symbol_cash_curves[symbol_key] = cash_curve
            symbol_timestamps[symbol_key] = timestamps

            # 存储单个交易对的数据
            self.symbol_data[symbol_key] = {
                'cash': cash,
                'cash_curve': cash_curve,
                'timestamps': timestamps,
                'trades': trades,
                'orders': orders,
                'metrics': metrics,
                'init_cash': cash[0] if cash else 100000.0,
                'final_cash': cash[-1] if cash else 100000.0,
                'trade_count': len(trades) if trades else len(orders) // 2 if orders else 0
            }

            print(f"  初始资金: {self.symbol_data[symbol_key]['init_cash']:.2f}")
            print(f"  最终资金: {self.symbol_data[symbol_key]['final_cash']:.2f}")
            print(f"  交易次数: {self.symbol_data[symbol_key]['trade_count']}")
            print(f"  时间范围: {timestamps[0] if timestamps else 'N/A'} ~ {timestamps[-1] if timestamps else 'N/A'}")

        # 计算合并资金曲线
        num_symbols = len(symbol_cash_curves)
        if num_symbols == 0:
            raise ValueError("没有有效的交易对数据")
        
        # 使用第一个交易对的时间戳作为基准
        first_symbol = list(symbol_timestamps.keys())[0]
        base_timestamps = symbol_timestamps[first_symbol]
        
        # 计算合并资金曲线（按时间点对齐）
        merged_cash = []
        merged_timestamps = []
        
        for i, ts in enumerate(base_timestamps):
            total_value = 0.0
            valid_count = 0
            
            for symbol_key in symbol_cash_curves.keys():
                curve = symbol_cash_curves[symbol_key]
                if i < len(curve):
                    total_value += curve[i]
                    valid_count += 1
            
            if valid_count > 0:
                merged_cash.append(total_value / valid_count)
                merged_timestamps.append(ts)
        
        # 计算合并指标
        merged_metrics = self._calculate_merged_metrics()
        
        # 汇总所有交易
        all_trades = []
        for symbol_key, data in self.symbol_data.items():
            trades = data.get('trades', [])
            if trades:
                for trade in trades:
                    trade_copy = trade.copy() if isinstance(trade, dict) else {}
                    trade_copy['symbol'] = symbol_key
                    all_trades.append(trade_copy)
        
        self.merged_data = {
            'merged_cash': merged_cash,
            'merged_timestamps': merged_timestamps,
            'merged_metrics': merged_metrics,
            'all_trades': all_trades,
            'symbol_count': num_symbols,
            'symbol_data': self.symbol_data
        }
        
        print(f"\n{'=' * 70}")
        print(f"数据合并完成")
        print(f"  交易对数量: {num_symbols}")
        print(f"  合并资金曲线长度: {len(merged_cash)}")
        print(f"  总交易次数: {len(all_trades)}")
        print(f"  时间范围: {merged_timestamps[0] if merged_timestamps else 'N/A'} ~ {merged_timestamps[-1] if merged_timestamps else 'N/A'}")
        print(f"{'=' * 70}\n")
        
        return self.merged_data
    
    def _extract_timestamps(self, data_str: str, expected_length: int) -> List[datetime]:
        """
        从data字段提取时间戳
        
        参数：
            data_str: data字段的字符串内容
            expected_length: 期望的时间戳数量
            
        返回：
            List[datetime]: 时间戳列表
        """
        if not data_str:
            return self._generate_default_timestamps(expected_length)
        
        timestamps = []
        start_date = None
        end_date = None
        
        try:
            # 解析data字符串中的起始和结束时间戳
            # 格式包含: "2023-12-31 16:00:00 ... 2024-12-30 16:00:00"
            lines = data_str.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                # 跳过空行和表头行
                if not line or line.startswith('timestamp') or 'Open' in line or '...' in line:
                    continue
                
                # 尝试解析时间戳 - 查找以20开头的行（年份）
                if line.startswith('20'):
                    try:
                        # 提取前19个字符作为时间戳 (YYYY-MM-DD HH:MM:SS)
                        if len(line) >= 19:
                            ts_str = line[:19]
                            dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                            timestamps.append(dt)
                            
                            # 记录第一个和最后一个有效时间戳
                            if start_date is None:
                                start_date = dt
                            end_date = dt
                    except (ValueError, IndexError):
                        continue
        except Exception as e:
            print(f"  警告: 解析时间戳失败: {e}")
        
        # 如果成功获取了起始和结束时间，生成完整的时间序列
        if start_date and end_date and len(timestamps) >= 2:
            # 根据数据点数量和起止时间计算时间间隔
            time_diff = end_date - start_date
            total_minutes = time_diff.total_seconds() / 60
            
            if expected_length > 1:
                interval_minutes = total_minutes / (expected_length - 1)
            else:
                interval_minutes = 15  # 默认15分钟
            
            # 生成完整的时间序列
            from datetime import timedelta
            full_timestamps = []
            current_date = start_date
            for i in range(expected_length):
                full_timestamps.append(current_date)
                current_date = current_date + timedelta(minutes=interval_minutes)
            
            return full_timestamps
        
        # 如果解析失败，使用默认序列
        print(f"  警告: 时间戳解析不完整 ({len(timestamps)} vs {expected_length})，使用默认序列")
        return self._generate_default_timestamps(expected_length)
    
    def _generate_default_timestamps(self, expected_length: int) -> List[datetime]:
        """生成默认时间序列（15分钟间隔）"""
        from datetime import timedelta
        start_date = datetime(2023, 12, 31, 16, 0, 0)
        timestamps = []
        current_date = start_date
        for i in range(expected_length):
            timestamps.append(current_date)
            current_date = current_date + timedelta(minutes=15)
        return timestamps
    
    def _calculate_merged_metrics(self) -> Dict[str, float]:
        """计算合并后的绩效指标"""
        if not self.symbol_data:
            return {}
        
        # 从合并资金曲线计算指标
        merged_cash = self.merged_data.get('merged_cash', []) if self.merged_data else []
        
        if not merged_cash:
            # 如果没有合并曲线，从各个交易对聚合
            total_init = sum(d['init_cash'] for d in self.symbol_data.values())
            total_final = sum(d['final_cash'] for d in self.symbol_data.values())
            total_pnl = total_final - total_init
            total_return = (total_pnl / total_init * 100) if total_init > 0 else 0
        else:
            total_init = merged_cash[0]
            total_final = merged_cash[-1]
            total_pnl = total_final - total_init
            total_return = (total_pnl / total_init * 100) if total_init > 0 else 0
        
        # 聚合所有交易
        all_pnls = []
        for data in self.symbol_data.values():
            trades = data.get('trades', [])
            if trades:
                for trade in trades:
                    if isinstance(trade, dict):
                        pnl = trade.get('pnl', 0) or trade.get('PnL', 0) or trade.get('profit', 0)
                        all_pnls.append(float(pnl))
        
        # 计算胜率
        winning_trades = sum(1 for p in all_pnls if p > 0)
        total_trades = len(all_pnls)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # 计算盈亏比
        total_profit = sum(p for p in all_pnls if p > 0)
        total_loss = abs(sum(p for p in all_pnls if p < 0))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
        
        # 计算平均收益
        avg_trade = sum(all_pnls) / len(all_pnls) if all_pnls else 0
        
        # 从合并资金曲线计算夏普比率和最大回撤
        sharpe_ratio = 0.0
        max_drawdown = 0.0
        
        if merged_cash and len(merged_cash) > 1:
            # 计算收益率序列
            returns = []
            for i in range(1, len(merged_cash)):
                if merged_cash[i-1] != 0:
                    ret = (merged_cash[i] - merged_cash[i-1]) / merged_cash[i-1]
                    returns.append(ret)
            
            if returns:
                # 夏普比率 (简化计算，假设无风险利率为0)
                avg_return = np.mean(returns)
                std_return = np.std(returns)
                sharpe_ratio = (avg_return / std_return * np.sqrt(252)) if std_return > 0 else 0
            
            # 最大回撤
            peak = merged_cash[0]
            for value in merged_cash:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100 if peak > 0 else 0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        return {
            'total_return': total_return,
            'total_pnl': total_pnl,
            'final_equity': total_final,
            'initial_equity': total_init,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': total_trades,
            'avg_trade': avg_trade
        }
    
    def generate_report(self, output_dir: Optional[str] = None, show: bool = False) -> str:
        """
        生成合并回测报告
        
        参数：
            output_dir: 输出目录，默认为结果文件所在目录
            show: 是否显示图表
            
        返回：
            str: 生成的报告文件路径
        """
        if self.merged_data is None:
            self.process_data()
        
        # 设置输出目录
        if output_dir is None:
            output_dir = os.path.dirname(self.results_file)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成文件名
        base_name = Path(self.results_file).stem
        output_path = os.path.join(output_dir, f"{base_name}_merged_report.png")
        
        print("=" * 70)
        print("生成合并回测报告")
        print("=" * 70)
        
        # 设置中文字体
        _setup_chinese_font()
        
        # 创建图表
        fig = plt.figure(figsize=(16, 12))
        gs = GridSpec(3, 2, figure=fig, height_ratios=[2, 1, 1], hspace=0.3, wspace=0.3)
        
        # 1. 合并资金曲线图（大图，左上）
        ax1 = fig.add_subplot(gs[0, :])
        self._plot_merged_equity_curve(ax1)
        
        # 2. 交易分布图（中左）
        ax2 = fig.add_subplot(gs[1, 0])
        self._plot_trade_distribution(ax2)
        
        # 3. 各交易对收益对比（中右）
        ax3 = fig.add_subplot(gs[1, 1])
        self._plot_symbol_comparison(ax3)
        
        # 4. 累计盈亏图（下左）
        ax4 = fig.add_subplot(gs[2, 0])
        self._plot_cumulative_pnl(ax4)
        
        # 5. 综合指标面板（下右）
        ax5 = fig.add_subplot(gs[2, 1])
        self._plot_metrics_panel(ax5)
        
        # 添加总标题
        if self.merged_data:
            fig.suptitle(
                f'多交易对回测综合报告\n'
                f'({self.merged_data.get("symbol_count", 0)} 个交易对 | '
                f'总交易 {self.merged_data.get("merged_metrics", {}).get("total_trades", 0)} 次 | '
                f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")})',
                fontsize=14, fontweight='bold', y=0.98
            )
        
        plt.tight_layout(rect=(0, 0, 1, 0.96))
        
        # 保存图表
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"\n✓ 合并报告已保存: {output_path}")
        
        # 同时生成一个详细的指标汇总文本报告
        text_report_path = os.path.join(output_dir, f"{base_name}_merged_summary.txt")
        self._generate_text_report(text_report_path)
        print(f"✓ 文本报告已保存: {text_report_path}")
        
        if show:
            plt.show()
        else:
            plt.close()
        
        return output_path
    
    def _plot_merged_equity_curve(self, ax):
        """绘制合并资金曲线（时间折线图）"""
        if not self.merged_data:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            return
        merged_cash = self.merged_data.get('merged_cash', [])
        merged_timestamps = self.merged_data.get('merged_timestamps', [])
        
        if not merged_cash:
            ax.text(0.5, 0.5, '无资金曲线数据', ha='center', va='center', transform=ax.transAxes)
            return
        
        # 如果没有时间戳，使用索引
        if not merged_timestamps or len(merged_timestamps) != len(merged_cash):
            x = range(len(merged_cash))
            ax.plot(x, merged_cash, linewidth=2, color='#2196F3', label='组合资金权益')
            ax.set_xlabel('时间步长', fontsize=10)
        else:
            # 使用时间戳绘制时间折线图
            import matplotlib.dates as mdates
            
            ax.plot(merged_timestamps, merged_cash, linewidth=2, color='#2196F3', label='组合资金权益')
            
            # 设置x轴日期格式
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
            ax.set_xlabel('时间', fontsize=10)
        
        # 添加初始资金参考线
        initial_cash = merged_cash[0]
        ax.axhline(y=initial_cash, color='gray', linestyle='--', alpha=0.7, linewidth=1, label='初始资金')
        
        # 填充盈亏区域
        x_fill = merged_timestamps if merged_timestamps and len(merged_timestamps) == len(merged_cash) else range(len(merged_cash))
        ax.fill_between(x_fill, merged_cash, initial_cash,
                        where=[c >= initial_cash for c in merged_cash],
                        alpha=0.3, color='green', interpolate=True)
        ax.fill_between(x_fill, merged_cash, initial_cash,
                        where=[c < initial_cash for c in merged_cash],
                        alpha=0.3, color='red', interpolate=True)
        
        # 设置标题和标签
        ax.set_title('组合资金权益曲线（所有交易对合并）', fontsize=12, fontweight='bold')
        ax.set_ylabel('资金权益', fontsize=10)
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, alpha=0.3, linestyle=':')
        
        # 添加最终收益标注
        final_cash = merged_cash[-1]
        pnl = final_cash - initial_cash
        pnl_pct = (pnl / initial_cash * 100) if initial_cash > 0 else 0
        color = 'green' if pnl >= 0 else 'red'
        ax.text(0.02, 0.98, f'最终收益: {pnl:+.2f} ({pnl_pct:+.2f}%)',
                transform=ax.transAxes, fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor=color, alpha=0.3))
    
    def _plot_trade_distribution(self, ax):
        """绘制交易分布图"""
        if not self.merged_data:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            return
        all_trades = self.merged_data.get('all_trades', [])
        
        if not all_trades:
            ax.text(0.5, 0.5, '无交易数据', ha='center', va='center', transform=ax.transAxes)
            return
        
        # 提取盈亏数据
        pnls = []
        for trade in all_trades:
            if isinstance(trade, dict):
                pnl = trade.get('pnl', 0) or trade.get('PnL', 0) or trade.get('profit', 0)
                pnls.append(float(pnl))
        
        if not pnls:
            ax.text(0.5, 0.5, '无有效盈亏数据', ha='center', va='center', transform=ax.transAxes)
            return
        
        # 绘制盈亏分布
        colors = ['green' if p > 0 else 'red' for p in pnls]
        ax.bar(range(len(pnls)), pnls, color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        ax.set_title('单笔交易盈亏分布（所有交易对）', fontsize=11, fontweight='bold')
        ax.set_xlabel('交易序号', fontsize=9)
        ax.set_ylabel('盈亏', fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')
        
        # 添加统计信息
        win_count = sum(1 for p in pnls if p > 0)
        loss_count = sum(1 for p in pnls if p < 0)
        ax.text(0.98, 0.98, f'盈利: {win_count} 笔\n亏损: {loss_count} 笔',
                transform=ax.transAxes, fontsize=9, verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.5))
    
    def _plot_symbol_comparison(self, ax):
        """绘制各交易对收益对比"""
        if not self.symbol_data:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            return
        symbol_returns = []
        symbol_names = []
        colors = []
        
        for symbol_key, data in self.symbol_data.items():
            init = data['init_cash']
            final = data['final_cash']
            ret = ((final - init) / init * 100) if init > 0 else 0
            
            symbol_returns.append(ret)
            symbol_names.append(symbol_key.replace('_', '\n'))
            colors.append('green' if ret >= 0 else 'red')
        
        if not symbol_returns:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            return
        
        bars = ax.bar(symbol_names, symbol_returns, color=colors, alpha=0.7)
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        ax.set_title('各交易对收益率对比', fontsize=11, fontweight='bold')
        ax.set_ylabel('收益率 (%)', fontsize=9)
        ax.grid(True, alpha=0.3, axis='y')
        
        # 在条形上添加数值标签
        for bar, value in zip(bars, symbol_returns):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{value:.2f}%',
                   ha='center', va='bottom' if height >= 0 else 'top', fontsize=8)
    
    def _plot_cumulative_pnl(self, ax):
        """绘制累计盈亏图"""
        if not self.merged_data:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            return
        all_trades = self.merged_data.get('all_trades', [])
        
        if not all_trades:
            ax.text(0.5, 0.5, '无交易数据', ha='center', va='center', transform=ax.transAxes)
            return
        
        # 提取盈亏数据
        pnls = []
        for trade in all_trades:
            if isinstance(trade, dict):
                pnl = trade.get('pnl', 0) or trade.get('PnL', 0) or trade.get('profit', 0)
                pnls.append(float(pnl))
        
        if not pnls:
            ax.text(0.5, 0.5, '无有效盈亏数据', ha='center', va='center', transform=ax.transAxes)
            return
        
        # 计算累计盈亏
        cumulative = [sum(pnls[:i+1]) for i in range(len(pnls))]
        
        ax.plot(cumulative, color='#2196F3', linewidth=2)
        ax.fill_between(range(len(cumulative)), cumulative, 0,
                        where=[x > 0 for x in cumulative], alpha=0.3, color='green')
        ax.fill_between(range(len(cumulative)), cumulative, 0,
                        where=[x <= 0 for x in cumulative], alpha=0.3, color='red')
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
        ax.set_title('累计盈亏走势', fontsize=11, fontweight='bold')
        ax.set_xlabel('交易序号', fontsize=9)
        ax.set_ylabel('累计盈亏', fontsize=9)
        ax.grid(True, alpha=0.3)
    
    def _plot_metrics_panel(self, ax):
        """绘制综合指标面板"""
        if not self.merged_data:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            return
        metrics = self.merged_data.get('merged_metrics', {})
        
        # 准备显示数据
        display_metrics = [
            ('总收益率', f"{metrics.get('total_return', 0):.2f}%"),
            ('总盈亏', f"{metrics.get('total_pnl', 0):.2f}"),
            ('最终权益', f"{metrics.get('final_equity', 0):.2f}"),
            ('胜率', f"{metrics.get('win_rate', 0):.2f}%"),
            ('盈亏比', f"{metrics.get('profit_factor', 0):.2f}"),
            ('夏普比率', f"{metrics.get('sharpe_ratio', 0):.2f}"),
            ('最大回撤', f"{metrics.get('max_drawdown', 0):.2f}%"),
            ('总交易次数', f"{metrics.get('total_trades', 0)}"),
            ('平均收益', f"{metrics.get('avg_trade', 0):.2f}")
        ]
        
        ax.axis('off')
        ax.set_title('综合绩效指标', fontsize=11, fontweight='bold', pad=10)
        
        # 创建表格
        table_data = [[name, value] for name, value in display_metrics]
        
        table = ax.table(
            cellText=table_data,
            colLabels=['指标', '数值'],
            cellLoc='center',
            loc='center',
            colWidths=[0.5, 0.5]
        )
        
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1, 1.5)
        
        # 设置表头样式
        for i in range(2):
            table[(0, i)].set_facecolor('#2196F3')
            table[(0, i)].set_text_props(weight='bold', color='white')
        
        # 设置交替行颜色
        for i in range(1, len(display_metrics) + 1):
            for j in range(2):
                if i % 2 == 0:
                    table[(i, j)].set_facecolor('#f0f0f0')
    
    def _generate_text_report(self, output_path: str):
        """生成文本格式的报告"""
        if not self.merged_data:
            return
        metrics = self.merged_data.get('merged_metrics', {})
        is_portfolio = self.merged_data.get('is_portfolio', False)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            if is_portfolio:
                f.write("投资组合回测综合报告（多交易对共享资金池）\n")
            else:
                f.write("多交易对回测综合报告\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"数据来源: {self.results_file}\n")
            f.write(f"交易对数量: {self.merged_data['symbol_count']}\n\n")

            f.write("-" * 70 + "\n")
            f.write("综合绩效指标\n")
            f.write("-" * 70 + "\n")
            f.write(f"总收益率:     {metrics.get('total_return', 0):>12.2f}%\n")
            f.write(f"总盈亏:       {metrics.get('total_pnl', 0):>12.2f}\n")
            f.write(f"初始权益:     {metrics.get('initial_equity', 0):>12.2f}\n")
            f.write(f"最终权益:     {metrics.get('final_equity', 0):>12.2f}\n")
            f.write(f"胜率:         {metrics.get('win_rate', 0):>12.2f}%\n")
            f.write(f"盈亏比:       {metrics.get('profit_factor', 0):>12.2f}\n")
            f.write(f"夏普比率:     {metrics.get('sharpe_ratio', 0):>12.2f}\n")
            f.write(f"最大回撤:     {metrics.get('max_drawdown', 0):>12.2f}%\n")
            f.write(f"总交易次数:   {metrics.get('total_trades', 0):>12}\n")
            f.write(f"平均收益:     {metrics.get('avg_trade', 0):>12.2f}\n\n")

            f.write("-" * 70 + "\n")
            if is_portfolio:
                f.write("各交易对贡献盈亏\n")
            else:
                f.write("各交易对详细数据\n")
            f.write("-" * 70 + "\n")

            for symbol_key, data in self.symbol_data.items():
                if is_portfolio:
                    # 投资组合格式：显示贡献的盈亏
                    pnl = data.get('pnl_contribution', 0)
                    f.write(f"\n{symbol_key}:\n")
                    f.write(f"  贡献盈亏:   {pnl:>12.2f}\n")
                    f.write(f"  交易次数:   {data['trade_count']:>12}\n")
                else:
                    # 传统格式：显示独立的资金曲线
                    init = data['init_cash']
                    final = data['final_cash']
                    ret = ((final - init) / init * 100) if init > 0 else 0

                    f.write(f"\n{symbol_key}:\n")
                    f.write(f"  初始资金:   {init:>12.2f}\n")
                    f.write(f"  最终资金:   {final:>12.2f}\n")
                    f.write(f"  收益率:     {ret:>12.2f}%\n")
                    f.write(f"  交易次数:   {data['trade_count']:>12}\n")

            f.write("\n" + "=" * 70 + "\n")
            f.write("报告生成完成\n")
            f.write("=" * 70 + "\n")


def generate_merged_report(results_file: str, output_dir: Optional[str] = None, show: bool = False) -> str:
    """
    生成多交易对合并回测报告的便捷函数
    
    参数：
        results_file: 回测结果JSON文件路径
        output_dir: 输出目录，默认为结果文件所在目录
        show: 是否显示图表
        
    返回：
        str: 生成的报告文件路径
    
    示例：
        # 生成合并报告
        report_path = generate_merged_report(
            '/path/to/backtest_results.json',
            output_dir='/path/to/output'
        )
    """
    report = MergedBacktestReport(results_file)
    return report.generate_report(output_dir=output_dir, show=show)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python merged_report.py <results_file> [output_dir]")
        print("示例: python merged_report.py backtest_results.json ./reports")
        sys.exit(1)
    
    results_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(results_file):
        print(f"错误: 文件不存在: {results_file}")
        sys.exit(1)
    
    try:
        report_path = generate_merged_report(results_file, output_dir)
        print(f"\n报告生成成功: {report_path}")
    except Exception as e:
        print(f"生成报告时出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
