#!/usr/bin/env python3
"""
QuantCell SMA交叉策略回测演示

基于 NautilusTrader 框架的简单移动平均线交叉策略回测
- 当价格上穿SMA时买入
- 当价格下穿SMA时卖出
- 支持参数优化

重构自: Backtrader demo_backtest.py
"""

import datetime
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import deque
from dataclasses import dataclass

import pandas as pd
import numpy as np
from loguru import logger

# 添加 backend 目录到 Python 路径
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from strategy.core.strategy_base import StrategyBase


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class Bar:
    """K线数据类"""
    datetime: datetime.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'datetime': self.datetime,
            'Open': self.open,
            'High': self.high,
            'Low': self.low,
            'Close': self.close,
            'Volume': self.volume,
        }


@dataclass
class Order:
    """订单类"""
    order_id: str
    direction: str  # 'buy' or 'sell'
    price: float
    size: float
    status: str = 'pending'
    timestamp: Optional[datetime.datetime] = None


@dataclass
class Trade:
    """交易记录类"""
    trade_id: str
    direction: str
    entry_price: float
    exit_price: Optional[float] = None
    size: float = 0.0
    pnl: float = 0.0
    entry_time: Optional[datetime.datetime] = None
    exit_time: Optional[datetime.datetime] = None


# =============================================================================
# 策略实现
# =============================================================================

class SMACrossStrategy(StrategyBase):
    """
    SMA交叉策略
    
    基于简单移动平均线(SMA)的交叉产生交易信号
    - 当价格上穿SMA时产生买入信号
    - 当价格下穿SMA时产生卖出信号
    """
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        初始化策略
        
        Args:
            params: 策略参数字典
                - maperiod: SMA周期 (默认: 15)
                - stake: 交易数量 (默认: 10)
                - printlog: 是否打印日志 (默认: False)
        """
        if params is None:
            params = {}
        
        # 设置默认参数
        default_params = {
            'maperiod': 15,
            'stake': 10,
            'printlog': False,
        }
        default_params.update(params)
        
        super().__init__(default_params)
        
        # 策略参数
        self.maperiod = self.params.get('maperiod', 15)
        self.stake = self.params.get('stake', 10)
        self.printlog = self.params.get('printlog', False)
        
        # 状态变量
        self.price_history: deque = deque(maxlen=self.maperiod + 10)
        self.sma_value: Optional[float] = None
        self.prev_sma: Optional[float] = None
        self.order: Optional[Order] = None
        self.buyprice: Optional[float] = None
        self.buycomm: float = 0.0
        self.bar_executed: int = 0
        
        # 持仓状态（独立于父类的positions）
        self._has_position: bool = False
        
        # 交易统计
        self.trades: List[Trade] = []
        self.total_pnl: float = 0.0
        self.winning_trades: int = 0
        self.total_trades: int = 0
        
    def on_init(self):
        """策略初始化"""
        self.log(f"SMA交叉策略初始化 - 周期: {self.maperiod}")
        self.price_history.clear()
        
    def log(self, txt: str, dt: datetime.datetime = None, doprint: bool = False):
        """日志记录"""
        if self.printlog or doprint:
            dt = dt or datetime.datetime.now()
            logger.info(f"{dt.isoformat()}, {txt}")
    
    def calculate_sma(self, period: int) -> Optional[float]:
        """
        计算简单移动平均线
        
        Args:
            period: 计算周期
            
        Returns:
            SMA值，数据不足时返回None
        """
        if len(self.price_history) < period:
            return None
        return sum(list(self.price_history)[-period:]) / period
    
    def on_bar(self, bar: Dict[str, Any]):
        """
        K线数据回调
        
        Args:
            bar: K线数据字典
        """
        # 获取收盘价
        close_price = bar.get('Close', bar.get('close'))
        dt = bar.get('datetime')
        
        if close_price is None:
            return
        
        # 记录价格历史
        self.price_history.append(float(close_price))
        
        # 记录收盘价
        self.log(f"Close, {close_price:.2f}", dt)
        
        # 检查是否有待处理订单
        if self.order is not None:
            return
        
        # 计算SMA
        self.prev_sma = self.sma_value
        self.sma_value = self.calculate_sma(self.maperiod)
        
        if self.sma_value is None:
            return
        
        # 检查是否持仓
        symbol = bar.get('symbol', 'DEFAULT')
        if not self._has_position:
            # 未持仓，检查买入信号
            if close_price > self.sma_value:
                self.log(f"BUY CREATE, {close_price:.2f}", dt)
                order_id = self.buy(symbol, close_price, self.stake)
                self.order = Order(
                    order_id=order_id,
                    direction='buy',
                    price=close_price,
                    size=self.stake,
                    status='pending',
                    timestamp=dt
                )
        else:
            # 已持仓，检查卖出信号
            if close_price < self.sma_value:
                self.log(f"SELL CREATE, {close_price:.2f}", dt)
                order_id = self.sell(symbol, close_price, self.stake)
                self.order = Order(
                    order_id=order_id,
                    direction='sell',
                    price=close_price,
                    size=self.stake,
                    status='pending',
                    timestamp=dt
                )
    
    def notify_position(self, has_position: bool):
        """更新持仓状态"""
        self._has_position = has_position
    
    def on_order(self, order: Dict[str, Any]):
        """
        订单状态更新回调
        
        Args:
            order: 订单数据
        """
        if order['status'] == 'completed':
            if order['direction'] == 'buy':
                self.log(
                    f"BUY EXECUTED, Price: {order['price']:.2f}, "
                    f"Cost: {order['price'] * order['volume']:.2f}, "
                    f"Comm {self.buycomm:.2f}"
                )
                self.buyprice = order['price']
                self.bar_executed = len(self.price_history)
                self._has_position = True  # 更新持仓状态
            else:  # sell
                self.log(
                    f"SELL EXECUTED, Price: {order['price']:.2f}, "
                    f"Cost: {order['price'] * order['volume']:.2f}, "
                    f"Comm {self.buycomm:.2f}"
                )
                
                # 计算盈亏
                if self.buyprice:
                    pnl = (order['price'] - self.buyprice) * order['volume']
                    self.total_pnl += pnl
                    self.total_trades += 1
                    if pnl > 0:
                        self.winning_trades += 1
                    self.log(f"OPERATION PROFIT, GROSS {pnl:.2f}")
                
                self._has_position = False  # 更新持仓状态
            
            self.order = None
    
    def on_stop(self, bar: Dict[str, Any]):
        """
        回测结束回调
        
        Args:
            bar: 最后一根K线数据
        """
        close_price = bar.get('Close', bar.get('close'))
        
        # 计算最终权益（简化计算）
        final_value = 1000.0 + self.total_pnl
        
        self.log(
            f"(MA Period {self.maperiod:2d}) Ending Value {final_value:.2f}",
            doprint=True
        )
        
        # 输出统计
        if self.total_trades > 0:
            win_rate = self.winning_trades / self.total_trades * 100
            self.log(f"总交易次数: {self.total_trades}, 胜率: {win_rate:.1f}%", doprint=True)


# =============================================================================
# 回测引擎
# =============================================================================

class SimpleBacktestEngine:
    """简单回测引擎"""
    
    def __init__(self, initial_cash: float = 1000.0, commission: float = 0.0):
        """
        初始化回测引擎
        
        Args:
            initial_cash: 初始资金
            commission: 手续费率
        """
        self.initial_cash = initial_cash
        self.commission = commission
        self.cash = initial_cash
        self.value = initial_cash
        self.positions: Dict[str, Dict[str, Any]] = {}
        
    def reset(self):
        """重置引擎状态"""
        self.cash = self.initial_cash
        self.value = self.initial_cash
        self.positions = {}
        
    def execute_order(self, order: Order, current_price: float) -> bool:
        """
        执行订单
        
        Args:
            order: 订单对象
            current_price: 当前价格
            
        Returns:
            是否执行成功
        """
        cost = order.price * order.size * (1 + self.commission)
        
        if order.direction == 'buy':
            if self.cash >= cost:
                self.cash -= cost
                symbol = 'DEFAULT'
                if symbol not in self.positions:
                    self.positions[symbol] = {'size': 0, 'avg_price': 0}
                
                pos = self.positions[symbol]
                total_cost = pos['avg_price'] * pos['size'] + order.price * order.size
                pos['size'] += order.size
                if pos['size'] > 0:
                    pos['avg_price'] = total_cost / pos['size']
                
                order.status = 'completed'
                return True
        else:  # sell
            symbol = 'DEFAULT'
            if symbol in self.positions and self.positions[symbol]['size'] >= order.size:
                pos = self.positions[symbol]
                revenue = order.price * order.size * (1 - self.commission)
                self.cash += revenue
                pos['size'] -= order.size
                
                if pos['size'] <= 0:
                    del self.positions[symbol]
                
                order.status = 'completed'
                return True
        
        order.status = 'rejected'
        return False
    
    def get_position_value(self, current_price: float) -> float:
        """获取持仓价值"""
        position_value = 0.0
        for symbol, pos in self.positions.items():
            position_value += pos['size'] * current_price
        return position_value
    
    def get_total_value(self, current_price: float) -> float:
        """获取总权益"""
        return self.cash + self.get_position_value(current_price)


# =============================================================================
# 数据加载
# =============================================================================

def load_csv_data(filepath: str) -> List[Bar]:
    """
    加载CSV数据文件
    
    Args:
        filepath: 数据文件路径
        
    Returns:
        K线数据列表
    """
    if not os.path.exists(filepath):
        # 生成模拟数据用于测试
        logger.info(f"数据文件不存在: {filepath}，生成模拟数据")
        return generate_mock_data()
    
    df = pd.read_csv(filepath, parse_dates=['Date'])
    
    bars = []
    for _, row in df.iterrows():
        bar = Bar(
            datetime=row['Date'],
            open=row['Open'],
            high=row['High'],
            low=row['Low'],
            close=row['Close'],
            volume=row.get('Volume', 0)
        )
        bars.append(bar)
    
    return bars


def generate_mock_data(n_bars: int = 252) -> List[Bar]:
    """
    生成模拟K线数据
    
    Args:
        n_bars: K线数量（默认252个交易日，约1年）
        
    Returns:
        K线数据列表
    """
    np.random.seed(42)
    
    # 生成随机价格序列
    returns = np.random.normal(0.0005, 0.02, n_bars)
    prices = 100 * np.exp(np.cumsum(returns))
    
    # 生成日期序列
    start_date = datetime.datetime(2000, 1, 1)
    dates = [start_date + datetime.timedelta(days=i) for i in range(n_bars)]
    
    bars = []
    for i, price in enumerate(prices):
        # 生成OHLC
        volatility = price * 0.01
        open_price = price + np.random.normal(0, volatility * 0.3)
        high_price = max(open_price, price) + np.random.uniform(0, volatility * 0.5)
        low_price = min(open_price, price) - np.random.uniform(0, volatility * 0.5)
        close_price = price
        volume = np.random.randint(1000000, 10000000)
        
        bar = Bar(
            datetime=dates[i],
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=volume
        )
        bars.append(bar)
    
    return bars


# =============================================================================
# 回测运行
# =============================================================================

def run_backtest(
    strategy_class,
    params: Dict[str, Any],
    bars: List[Bar],
    initial_cash: float = 1000.0,
    commission: float = 0.0
) -> Dict[str, Any]:
    """
    运行回测
    
    Args:
        strategy_class: 策略类
        params: 策略参数
        bars: K线数据列表
        initial_cash: 初始资金
        commission: 手续费率
        
    Returns:
        回测结果字典
    """
    # 创建策略实例
    strategy = strategy_class(params)
    
    # 创建回测引擎
    engine = SimpleBacktestEngine(initial_cash, commission)
    
    # 初始化策略
    strategy.on_init()
    
    # 遍历K线数据
    for i, bar in enumerate(bars):
        bar_dict = bar.to_dict()
        bar_dict['symbol'] = 'DEFAULT'
        
        # 策略处理K线
        strategy.on_bar(bar_dict)
        
        # 处理待执行订单
        if strategy.order and strategy.order.status == 'pending':
            success = engine.execute_order(strategy.order, bar.close)
            
            # 通知策略订单状态
            order_dict = {
                'order_id': strategy.order.order_id,
                'direction': strategy.order.direction,
                'price': strategy.order.price,
                'volume': strategy.order.size,
                'status': strategy.order.status,
            }
            strategy.on_order(order_dict)
        
        # 更新权益
        current_value = engine.get_total_value(bar.close)
    
    # 回测结束 - 强制平仓
    if bars:
        # 如果还有持仓，强制平仓
        if strategy._has_position:
            final_price = bars[-1].close
            pnl = (final_price - strategy.buyprice) * strategy.stake if strategy.buyprice else 0
            strategy.total_pnl += pnl
            strategy.total_trades += 1
            if pnl > 0:
                strategy.winning_trades += 1
            strategy._has_position = False
        
        strategy.on_stop(bars[-1].to_dict())
    
    # 计算最终权益
    final_value = initial_cash + strategy.total_pnl
    total_return = (final_value - initial_cash) / initial_cash * 100
    
    # 返回结果
    return {
        'params': params,
        'final_value': final_value,
        'total_return': total_return,
        'trades': strategy.total_trades,
        'win_rate': strategy.winning_trades / strategy.total_trades * 100 if strategy.total_trades > 0 else 0,
    }


def optimize_parameters(
    strategy_class,
    param_ranges: Dict[str, range],
    bars: List[Bar],
    initial_cash: float = 1000.0
) -> List[Dict[str, Any]]:
    """
    参数优化
    
    Args:
        strategy_class: 策略类
        param_ranges: 参数范围字典
        bars: K线数据列表
        initial_cash: 初始资金
        
    Returns:
        优化结果列表
    """
    results = []
    
    # 获取参数范围
    maperiod_range = param_ranges.get('maperiod', range(10, 31))
    
    for maperiod in maperiod_range:
        params = {'maperiod': maperiod, 'printlog': False}
        
        logger.info(f"测试参数: maperiod={maperiod}")
        
        result = run_backtest(
            strategy_class,
            params,
            bars,
            initial_cash=initial_cash,
            commission=0.0
        )
        
        results.append(result)
        logger.info(f"  最终权益: {result['final_value']:.2f}, 收益率: {result['total_return']:.2f}%")
    
    # 按收益率排序
    results.sort(key=lambda x: x['total_return'], reverse=True)
    
    return results


def generate_backtest_report(result: Dict[str, Any], bars: List[Bar]):
    """
    生成回测分析报告（参考 NautilusTrader 格式）
    
    Args:
        result: 回测结果字典
        bars: K线数据列表
    """
    from datetime import datetime
    
    # 计算基础统计指标
    initial_cash = 1000.0
    final_value = result['final_value']
    total_return = result['total_return']
    total_trades = result['trades']
    win_rate = result['win_rate']
    
    # 计算年化收益率
    if len(bars) > 1:
        start_date = bars[0].datetime
        end_date = bars[-1].datetime
        days = (end_date - start_date).days
        years = days / 365.25 if days > 0 else 1
        annual_return = ((final_value / initial_cash) ** (1/years) - 1) * 100 if years > 0 else 0
    else:
        annual_return = 0
    
    # 计算价格统计
    closes = [bar.close for bar in bars]
    prices_mean = np.mean(closes)
    prices_std = np.std(closes)
    prices_min = min(closes)
    prices_max = max(closes)
    
    # 计算最大回撤（简化计算）
    peak = initial_cash
    max_drawdown = 0.0
    current_value = initial_cash
    
    # 报告标题
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "QUANTCELL BACKTEST ANALYSIS REPORT" + " " * 24 + "║")
    print("╠" + "═" * 78 + "╣")
    
    # 基本信息
    print("║  基本信息" + " " * 68 + "║")
    print("╟" + "─" * 78 + "╢")
    print(f"║  策略名称:     SMA Cross Strategy" + " " * 43 + "║")
    print(f"║  回测周期:     {bars[0].datetime.strftime('%Y-%m-%d')} 至 {bars[-1].datetime.strftime('%Y-%m-%d')}" + " " * 35 + "║")
    print(f"║  数据条数:     {len(bars)} bars" + " " * 52 + "║")
    print(f"║  生成时间:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}" + " " * 46 + "║")
    
    # 策略参数
    print("╠" + "═" * 78 + "╣")
    print("║  策略参数" + " " * 68 + "║")
    print("╟" + "─" * 78 + "╢")
    params = result['params']
    print(f"║  SMA周期:      {params.get('maperiod', 15)}" + " " * 60 + "║")
    print(f"║  仓位大小:     {params.get('stake', 10)}" + " " * 60 + "║")
    print(f"║  初始资金:     ${initial_cash:,.2f}" + " " * 54 + "║")
    print(f"║  手续费率:     0.00%" + " " * 56 + "║")
    
    # 绩效指标
    print("╠" + "═" * 78 + "╣")
    print("║  绩效指标" + " " * 68 + "║")
    print("╟" + "─" * 78 + "╢")
    print(f"║  最终权益:     ${final_value:>15,.2f}" + " " * 42 + "║")
    print(f"║  总收益率:     {total_return:>15.2f}%" + " " * 42 + "║")
    print(f"║  年化收益率:   {annual_return:>15.2f}%" + " " * 42 + "║")
    print(f"║  总交易次数:   {total_trades:>15}" + " " * 44 + "║")
    print(f"║  胜率:         {win_rate:>15.1f}%" + " " * 42 + "║")
    
    # 交易统计
    if total_trades > 0:
        print("╠" + "═" * 78 + "╣")
        print("║  交易统计" + " " * 68 + "║")
        print("╟" + "─" * 78 + "╢")
        winning_trades = int(total_trades * win_rate / 100)
        losing_trades = total_trades - winning_trades
        print(f"║  盈利交易:     {winning_trades:>15}" + " " * 44 + "║")
        print(f"║  亏损交易:     {losing_trades:>15}" + " " * 44 + "║")
    
    # 市场数据概览
    print("╠" + "═" * 78 + "╣")
    print("║  市场数据概览" + " " * 64 + "║")
    print("╟" + "─" * 78 + "╢")
    print(f"║  平均收盘价:   ${prices_mean:>15.2f}" + " " * 42 + "║")
    print(f"║  收盘价标准差: ${prices_std:>15.2f}" + " " * 42 + "║")
    print(f"║  最低价:       ${prices_min:>15.2f}" + " " * 42 + "║")
    print(f"║  最高价:       ${prices_max:>15.2f}" + " " * 42 + "║")
    print(f"║  价格区间:     ${prices_max - prices_min:>15.2f}" + " " * 42 + "║")
    
    # 报告底部
    print("╚" + "═" * 78 + "╝")
    
    # 关键洞察
    print("\n【关键洞察】")
    if total_return > 0:
        print(f"  ✓ 策略在回测期间实现了 {total_return:.2f}% 的正收益")
    else:
        print(f"  ✗ 策略在回测期间产生了 {total_return:.2f}% 的亏损")
    
    if total_trades > 0:
        if win_rate > 50:
            print(f"  ✓ 胜率为 {win_rate:.1f}%，超过50%的盈亏平衡线")
        else:
            print(f"  ✗ 胜率为 {win_rate:.1f}%，低于50%的盈亏平衡线")
    else:
        print(f"  ! 回测期间未产生任何交易信号")
    
    print(f"  • 年化收益率为 {annual_return:.2f}%")
    print(f"  • 价格波动范围为 ${prices_max - prices_min:.2f}")


# =============================================================================
# 主函数
# =============================================================================

def main():
    """主函数"""
    # 配置日志
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    
    print("=" * 70)
    print("QuantCell SMA交叉策略回测")
    print("=" * 70)
    
    # 数据文件路径
    modpath = os.path.dirname(os.path.abspath(sys.argv[0]))
    datapath = os.path.join(modpath, '../../datas/orcl-1995-2014.txt')
    
    # 加载数据
    print("\n加载数据...")
    bars = load_csv_data(datapath)
    print(f"加载了 {len(bars)} 根K线")
    print(f"日期范围: {bars[0].datetime.date()} 到 {bars[-1].datetime.date()}")
    
    # 参数优化
    print("\n" + "=" * 70)
    print("参数优化 (MA周期: 10-30)")
    print("=" * 70)
    
    results = optimize_parameters(
        SMACrossStrategy,
        {'maperiod': range(10, 31)},
        bars,
        initial_cash=1000.0
    )
    
    # 输出最优结果
    print("\n" + "=" * 70)
    print("优化结果 (前5名)")
    print("=" * 70)
    print(f"{'排名':<6}{'MA周期':<10}{'最终权益':<15}{'收益率':<12}{'交易次数':<10}{'胜率':<10}")
    print("-" * 70)
    
    for i, result in enumerate(results[:5], 1):
        print(
            f"{i:<6}"
            f"{result['params']['maperiod']:<10}"
            f"{result['final_value']:<15.2f}"
            f"{result['total_return']:<12.2f}%"
            f"{result['trades']:<10}"
            f"{result['win_rate']:<10.1f}%"
        )
    
    # 使用最优参数运行详细回测
    best_params = results[0]['params']
    best_params['printlog'] = True
    
    print("\n" + "=" * 70)
    print(f"最优参数详细回测 (MA周期: {best_params['maperiod']})")
    print("=" * 70)
    
    result = run_backtest(
        SMACrossStrategy,
        best_params,
        bars,
        initial_cash=1000.0,
        commission=0.0
    )
    
    # 生成并输出分析报告
    print("\n")
    generate_backtest_report(result, bars)
    
    print("\n" + "=" * 70)
    print("回测完成")
    print("=" * 70)


if __name__ == '__main__':
    main()
