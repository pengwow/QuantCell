#!/usr/bin/env python3
"""
Backtrader 回测适配器

将Backtrader框架的回测结果转换为统一格式
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
from rich.console import Console

console = Console()


class BacktraderAdapter(BaseBacktestAdapter):
    """
    Backtrader框架回测适配器
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.name = "Backtrader"
    
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
        执行Backtrader回测
        """
        try:
            import backtrader as bt
        except ImportError:
            print("警告: 未安装backtrader，使用模拟回测")
            return self._simulate_backtest(strategy_class, strategy_params, data, 
                                          initial_capital, commission, slippage)
        
        # 创建Backtrader策略包装器
        bt_strategy = self._create_bt_strategy(strategy_class, strategy_params)
        
        # 创建cerebro引擎
        cerebro = bt.Cerebro()
        cerebro.addstrategy(bt_strategy)
        
        # 添加数据
        bt_data = bt.feeds.PandasData(dataname=data)
        cerebro.adddata(bt_data)
        
        # 设置初始资金
        cerebro.broker.setcash(initial_capital)
        cerebro.broker.setcommission(commission=commission)
        
        # 添加分析器
        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        
        # 运行回测
        results = cerebro.run()
        strat = results[0]
        
        # 提取结果
        return self._extract_results(strat, data, initial_capital)
    
    def _create_bt_strategy(self, strategy_class: type, strategy_params: Dict[str, Any]):
        """
        创建Backtrader策略包装器
        """
        import backtrader as bt
        
        class BtStrategyWrapper(bt.Strategy):
            params = (
                ('strategy_class', strategy_class),
                ('strategy_params', strategy_params),
            )

            def __init__(self):
                # 创建QuantCell策略实例
                self.qc_strategy = self.p.strategy_class(self.p.strategy_params)

                # 计算指标
                self.fast_ma = bt.indicators.SMA(self.data.close, period=10)
                self.slow_ma = bt.indicators.SMA(self.data.close, period=30)
                self.crossover = bt.indicators.CrossOver(self.fast_ma, self.slow_ma)

                # 【调试输出】初始化计数器
                self.buy_count = 0
                self.sell_count = 0

            def next(self):
                # 【调试输出】打印前5根K线的数据
                if len(self) <= 5:
                    print(f"\n[Backtrader调试] K线 {len(self)}:")
                    print(f"[Backtrader调试]   日期: {self.data.datetime.date(0)}")
                    print(f"[Backtrader调试]   Close: {self.data.close[0]:.2f}")
                    print(f"[Backtrader调试]   fast_ma: {self.fast_ma[0]:.2f}")
                    print(f"[Backtrader调试]   slow_ma: {self.slow_ma[0]:.2f}")
                    print(f"[Backtrader调试]   crossover: {self.crossover[0]}")

                # 根据信号执行交易
                if self.crossover > 0:  # 金叉买入
                    if not self.position:
                        self.buy()
                        self.buy_count += 1
                        # 【调试输出】打印第一笔买入
                        if self.buy_count == 1:
                            print(f"\n[Backtrader调试] 第1笔买入:")
                            print(f"[Backtrader调试]   日期: {self.data.datetime.date(0)}")
                            print(f"[Backtrader调试]   价格: {self.data.close[0]:.2f}")
                            print(f"[Backtrader调试]   fast_ma: {self.fast_ma[0]:.2f}")
                            print(f"[Backtrader调试]   slow_ma: {self.slow_ma[0]:.2f}")
                elif self.crossover < 0:  # 死叉卖出
                    if self.position:
                        self.sell()
                        self.sell_count += 1

            def stop(self):
                # 【调试输出】打印交易统计
                print(f"\n[Backtrader调试] 交易统计:")
                print(f"[Backtrader调试]   买入次数: {self.buy_count}")
                print(f"[Backtrader调试]   卖出次数: {self.sell_count}")
        
        return BtStrategyWrapper
    
    def _extract_results(self, strat, data: pd.DataFrame, initial_capital: float) -> BacktestResult:
        """从Backtrader结果中提取数据"""
        # 获取分析结果
        sharpe = strat.analyzers.sharpe.get_analysis()
        drawdown = strat.analyzers.drawdown.get_analysis()
        trades = strat.analyzers.trades.get_analysis()
        returns = strat.analyzers.returns.get_analysis()

        # 提取交易记录
        trade_records = []
        # 从分析器获取交易信息
        # Backtrader的_trades是一个字典: {data: [trade_list]}
        if hasattr(strat, '_trades') and strat._trades:
            for data_obj, trade_list in strat._trades.items():
                if isinstance(trade_list, list):
                    for trade in trade_list:
                        # 检查trade对象是否有isclosed属性
                        if hasattr(trade, 'isclosed') and trade.isclosed:
                            record = TradeRecord(
                                entry_time=trade.dtopen,
                                exit_time=trade.dtclose,
                                entry_price=trade.price,
                                exit_price=trade.price,  # 简化处理
                                size=trade.size,
                                side='long' if trade.size > 0 else 'short',
                                pnl=trade.pnlcomm,
                                pnl_pct=(trade.pnlcomm / (trade.price * abs(trade.size))) if trade.price and trade.size else 0,
                                status='closed'
                            )
                            trade_records.append(record)

        # 如果没有提取到交易记录，但分析器显示有交易，发出警告
        total_trades_from_analyzer = trades.get('total', {}).get('total', 0)
        if not trade_records and total_trades_from_analyzer > 0:
            console.print(f"[yellow]警告: 无法获取详细交易记录，但分析器显示有 {total_trades_from_analyzer} 笔交易[/yellow]")
        
        # 计算统计指标
        final_value = strat.broker.getvalue()
        total_return = final_value - initial_capital
        total_return_pct = (total_return / initial_capital) * 100
        
        total_trades = trades.get('total', {}).get('total', 0)
        winning_trades = trades.get('won', {}).get('total', 0)
        losing_trades = trades.get('lost', {}).get('total', 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        max_drawdown_pct = drawdown.get('max', {}).get('drawdown', 0) or 0
        sharpe_ratio = sharpe.get('sharperatio', 0) or 0
        
        # 构建权益曲线
        equity_curve = pd.DataFrame({
            'timestamp': data.index,
            'equity': [initial_capital] * len(data),  # 简化处理
        })
        
        return BacktestResult(
            start_date=data.index[0],
            end_date=data.index[-1],
            initial_capital=initial_capital,
            final_capital=final_value,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_profit=0,
            avg_loss=0,
            profit_factor=0,
            max_drawdown=0,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=0,
            trades=trade_records,
            equity_curve=equity_curve,
            raw_result={'strat': strat}
        )
    
    def _simulate_backtest(self, strategy_class: type, strategy_params: Dict[str, Any],
                          data: pd.DataFrame, initial_capital: float,
                          commission: float, slippage: float) -> BacktestResult:
        """模拟回测（当backtrader不可用时）"""
        print("使用模拟回测...")
        
        # 简化的SMA交叉策略模拟
        fast_period = strategy_params.get('fast', 10)
        slow_period = strategy_params.get('slow', 30)
        
        sma_fast = data['Close'].rolling(window=fast_period).mean()
        sma_slow = data['Close'].rolling(window=slow_period).mean()
        
        # 生成信号
        signals = pd.Series(0, index=data.index)
        signals[sma_fast > sma_slow] = 1  # 买入
        signals[sma_fast < sma_slow] = -1  # 卖出
        
        # 简化的回测模拟
        capital = initial_capital
        position = 0
        trades = []
        
        for i, (timestamp, row) in enumerate(data.iterrows()):
            if i < slow_period:
                continue
                
            price = row['Close']
            signal = signals.iloc[i]
            prev_signal = signals.iloc[i-1] if i > 0 else 0
            
            # 买入信号
            if signal == 1 and prev_signal != 1 and position == 0:
                position = capital / price * (1 - commission)
                capital = 0
                
            # 卖出信号
            elif signal == -1 and prev_signal != -1 and position > 0:
                capital = position * price * (1 - commission)
                position = 0
        
        # 计算最终价值
        final_price = data['Close'].iloc[-1]
        final_capital = capital + (position * final_price if position > 0 else 0)
        
        return BacktestResult(
            start_date=data.index[0],
            end_date=data.index[-1],
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=final_capital - initial_capital,
            total_return_pct=((final_capital - initial_capital) / initial_capital) * 100,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            avg_profit=0,
            avg_loss=0,
            profit_factor=0,
            max_drawdown=0,
            max_drawdown_pct=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            trades=[],
            equity_curve=pd.DataFrame(),
            raw_result={}
        )
    
    def validate_strategy(self, strategy_class: type) -> tuple[bool, str]:
        """
        验证策略类是否有效
        """
        try:
            import backtrader as bt
            
            if issubclass(strategy_class, bt.Strategy):
                return True, ""
            
            # 也接受QuantCell策略，会进行包装
            return True, "将使用包装器适配QuantCell策略"
            
        except ImportError:
            return True, "Backtrader未安装，将使用模拟回测"
        except Exception as e:
            return False, f"验证失败: {e}"
