# -*- coding: utf-8 -*-
"""
回测结果绘图工具模块

提供回测结果的可视化功能，包括：
- 资金曲线图
- 交易分布图
- 指标汇总图
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional


def _setup_chinese_font():
    """设置matplotlib中文字体"""
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import platform
    
    system = platform.system()
    
    # 尝试查找系统中文字体
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


def plot_results(results: Dict[str, Any], output: Optional[str], show: bool, plot_type: str):
    """
    绘制回测结果图表
    
    参数：
        results: 回测结果
        output: 输出文件路径
        show: 是否显示图表
        plot_type: 图表类型
    """
    from pathlib import Path
    
    # 处理多个交易对的情况
    symbols = list(results.keys())
    
    for i, symbol_key in enumerate(symbols):
        result = results[symbol_key]
        print(f"正在生成 {symbol_key} 的图表...")
        
        # 获取数据
        symbol = result.get('symbol', symbol_key)
        metrics = result.get('metrics', {})
        trades = result.get('trades', [])
        equity_curve = result.get('equity_curve', [])
        
        # 如果没有equity_curve，尝试从trades构建
        if not equity_curve and trades:
            equity_curve = _build_equity_curve_from_trades(trades)
        
        # 为每个交易对生成唯一的输出文件名
        if output and len(symbols) > 1:
            # 如果有多个交易对，在文件名中添加序号
            output_path = Path(output)
            output_base = output_path.stem
            output_ext = output_path.suffix or '.png'
            symbol_output = str(output_path.parent / f"{output_base}_{output_ext}")
        else:
            symbol_output = output
        
        # 根据plot_type绘制
        if plot_type in ['all', 'equity']:
            _plot_equity_curve(symbol, equity_curve, trades, metrics, symbol_output, show)
        
        if plot_type in ['all', 'trades']:
            _plot_trade_distribution(symbol, trades, metrics, symbol_output, show)
        
        if plot_type in ['all', 'metrics']:
            _plot_metrics_summary(symbol, metrics, symbol_output, show)


def _build_equity_curve_from_trades(trades: List[Dict]) -> List[Dict]:
    """从交易记录构建资金曲线"""
    init_cash = 100000.0
    cash = init_cash
    position = 0
    entry_price = 0
    equity_curve = []
    max_equity = init_cash
    
    for i, trade in enumerate(trades):
        price = float(trade.get('price', 0))
        side = trade.get('side', '').upper()
        quantity = float(trade.get('quantity', 0.1))
        
        if side == 'BUY':
            cost = price * quantity
            cash -= cost
            position = quantity
            entry_price = price
        elif side == 'SELL':
            revenue = price * position
            cash += revenue
            position = 0
            entry_price = 0
        
        position_value = position * price if position > 0 else 0
        current_equity = cash + position_value
        
        if current_equity > max_equity:
            max_equity = current_equity
        
        drawdown = max_equity - current_equity
        
        equity_curve.append({
            'timestamp': trade.get('timestamp', i),
            'equity': current_equity,
            'cash': cash,
            'drawdown': drawdown
        })
    
    return equity_curve


def _plot_equity_curve(symbol: str, equity_curve: List[Dict], trades: List[Dict], 
                       metrics: Dict, output: Optional[str], show: bool):
    """绘制资金曲线图"""
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    
    _setup_chinese_font()
    
    if not equity_curve:
        print(f"  警告: {symbol} 没有资金曲线数据")
        return
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    
    # 准备数据
    timestamps = [point.get('timestamp', 0) for point in equity_curve]
    equities = [point.get('equity', 0) for point in equity_curve]
    
    if not timestamps or not equities:
        print(f"  警告: {symbol} 资金曲线数据格式不正确")
        return
    
    # 转换时间戳
    dates = []
    for ts in timestamps:
        if isinstance(ts, (int, float)) and ts > 1e10:
            dates.append(datetime.fromtimestamp(ts / 1000))
        elif isinstance(ts, (int, float)):
            dates.append(datetime.fromtimestamp(ts))
        else:
            dates.append(datetime.now())
    
    # 绘制
    ax.plot(dates, equities, label='总资金权益', color='#2196F3', linewidth=1.5)
    
    # 添加初始资金参考线
    initial_cash = equities[0] if equities else 100000
    ax.axhline(y=initial_cash, color='gray', linestyle='--', alpha=0.7, linewidth=1, label='初始资金')
    
    # 设置标题
    ax.set_title(f'{symbol} 资金权益曲线', fontsize=12, fontweight='bold')
    ax.set_xlabel('时间', fontsize=10)
    ax.set_ylabel('资金权益', fontsize=10)
    ax.legend(loc='best', fontsize=9)
    ax.grid(True, alpha=0.3, linestyle=':')
    
    # 设置x轴日期格式
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    
    # 保存
    if output:
        output_path = output if output.endswith('.png') else f"{output}.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 资金曲线图已保存: {output_path}")
    else:
        # 使用符号名称作为默认文件名
        output_path = f"{symbol}_equity_curve.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 资金曲线图已保存: {output_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


def _plot_trade_distribution(symbol: str, trades: List[Dict], metrics: Dict, 
                             output: Optional[str], show: bool):
    """绘制交易分布图"""
    import matplotlib.pyplot as plt
    
    _setup_chinese_font()
    
    if not trades:
        print(f"  警告: {symbol} 没有交易记录")
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'{symbol} 交易分析', fontsize=16, fontweight='bold')
    
    # 提取盈亏数据
    pnls = []
    directions = []
    
    for trade in trades:
        if isinstance(trade, dict):
            pnl = trade.get('pnl', 0) or trade.get('PnL', 0) or trade.get('profit', 0)
            direction = trade.get('direction', 'long')
            pnls.append(float(pnl))
            directions.append(direction)
    
    if not pnls:
        print(f"  警告: {symbol} 没有有效的盈亏数据")
        plt.close()
        return
    
    # 1. 盈亏分布直方图
    ax1 = axes[0, 0]
    colors = ['green' if p > 0 else 'red' for p in pnls]
    ax1.bar(range(len(pnls)), pnls, color=colors, alpha=0.7)
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax1.set_title('单笔盈亏分布', fontsize=12)
    ax1.set_xlabel('交易序号')
    ax1.set_ylabel('盈亏')
    ax1.grid(True, alpha=0.3)
    
    # 2. 收益率分布
    ax2 = axes[0, 1]
    returns = [(p / abs(pnls[i-1]) * 100) if i > 0 and pnls[i-1] != 0 else 0 for i, p in enumerate(pnls)]
    ax2.hist(returns, bins=20, color='blue', alpha=0.7, edgecolor='black')
    ax2.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax2.set_title('收益率分布', fontsize=12)
    ax2.set_xlabel('收益率 (%)')
    ax2.set_ylabel('频次')
    ax2.grid(True, alpha=0.3)
    
    # 3. 多空对比
    ax3 = axes[1, 0]
    long_count = sum(1 for d in directions if d.lower() in ['long', 'buy', '多单'])
    short_count = sum(1 for d in directions if d.lower() in ['short', 'sell', '空单'])
    
    if long_count > 0 or short_count > 0:
        ax3.bar(['多单', '空单'], [long_count, short_count], color=['green', 'red'], alpha=0.7)
        ax3.set_title('多空交易次数', fontsize=12)
        ax3.set_ylabel('交易次数')
        ax3.grid(True, alpha=0.3, axis='y')
    
    # 4. 累计盈亏
    ax4 = axes[1, 1]
    cumulative_pnl = [sum(pnls[:i+1]) for i in range(len(pnls))]
    ax4.plot(cumulative_pnl, color='blue', linewidth=2)
    ax4.fill_between(range(len(cumulative_pnl)), cumulative_pnl, 0,
                     where=[x > 0 for x in cumulative_pnl], alpha=0.3, color='green')
    ax4.fill_between(range(len(cumulative_pnl)), cumulative_pnl, 0,
                     where=[x <= 0 for x in cumulative_pnl], alpha=0.3, color='red')
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax4.set_title('累计盈亏', fontsize=12)
    ax4.set_xlabel('交易序号')
    ax4.set_ylabel('累计盈亏')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存
    if output:
        # 直接使用传入的输出路径，不添加后缀
        output_path = output if output.endswith('.png') else f"{output}.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 交易分布图已保存: {output_path}")
    else:
        output_path = f"{symbol}_trade_distribution.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 交易分布图已保存: {output_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


def _plot_metrics_summary(symbol: str, metrics: Dict, output: Optional[str], show: bool):
    """绘制指标汇总图"""
    import matplotlib.pyplot as plt
    
    _setup_chinese_font()
    
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.suptitle(f'{symbol} 回测指标汇总', fontsize=16, fontweight='bold')
    
    # 准备指标数据
    metric_names = []
    metric_values = []
    
    key_metrics = {
        'total_return': '总收益率 (%)',
        'total_pnl': '总盈亏',
        'sharpe_ratio': '夏普比率',
        'max_drawdown': '最大回撤 (%)',
        'win_rate': '胜率 (%)',
        'profit_factor': '盈亏比',
        'total_trades': '总交易次数',
        'avg_trade': '平均收益',
        'final_equity': '最终权益'
    }
    
    for key, label in key_metrics.items():
        if key in metrics:
            value = metrics[key]
            if isinstance(value, (int, float)):
                metric_names.append(label)
                metric_values.append(float(value))
    
    if not metric_names:
        ax.text(0.5, 0.5, '无指标数据', ha='center', va='center', transform=ax.transAxes, fontsize=14)
    else:
        # 绘制水平条形图
        colors = ['green' if v > 0 else 'red' if v < 0 else 'gray' for v in metric_values]
        bars = ax.barh(metric_names, metric_values, color=colors, alpha=0.7)
        
        # 在条形上添加数值标签
        for bar, value in zip(bars, metric_values):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2,
                   f'{value:.4f}' if abs(value) < 10 else f'{value:.2f}',
                   ha='left' if width >= 0 else 'right', va='center', fontsize=10)
        
        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax.set_xlabel('数值', fontsize=12)
        ax.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    
    # 保存
    if output:
        # 直接使用传入的输出路径，不添加后缀
        output_path = output if output.endswith('.png') else f"{output}.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 指标汇总图已保存: {output_path}")
    else:
        output_path = f"{symbol}_metrics_summary.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"  ✓ 指标汇总图已保存: {output_path}")
    
    if show:
        plt.show()
    else:
        plt.close()
