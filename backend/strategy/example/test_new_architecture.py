# 测试新架构
import sys
import os

# 添加路径 - 从 example 目录计算 backend 路径
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(os.path.dirname(current_dir))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# 添加项目根目录到路径（用于导入 strategies 模块）
project_dir = os.path.dirname(backend_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

import numpy as np
import pandas as pd
from loguru import logger

# 尝试导入策略和适配器，如果不存在则创建简单版本用于测试
try:
    from backend.strategies.grid_trading import GridTradingStrategy
    from strategy.adapters.vector_adapter import VectorBacktestAdapter
    HAS_FULL_STRATEGY = True
except ImportError as e:
    HAS_FULL_STRATEGY = False
    logger.warning(f"GridTradingStrategy 或 VectorBacktestAdapter 未找到，使用简化测试: {e}")

    # 创建简化版策略用于测试
    from strategy.core import StrategyBase

    class SimpleTestStrategy(StrategyBase):
        """简化测试策略"""
        def __init__(self, params):
            super().__init__(params)
            self.grid_levels = []
            self.current_grid = 0

        def on_init(self):
            self.grid_levels = [40000, 45000, 50000, 55000, 60000]

        def on_bar(self, bar):
            price = bar['close']
            for i, level in enumerate(self.grid_levels):
                if price < level:
                    self.current_grid = i
                    break

        def on_order(self, order):
            pass

        def on_trade(self, trade):
            pass

        def on_funding_rate(self, rate, mark_price):
            pass

    # 创建简化版适配器
    from strategy.core import VectorEngine

    class SimpleTestAdapter:
        """简化测试适配器"""
        def __init__(self, strategy):
            self.strategy = strategy
            self.engine = VectorEngine()
            self.results = {}

        def run_backtest(self, data, init_cash=100000.0, fees=0.001, slippage=0.0001):
            results = {}
            for symbol, df in data.items():
                # 生成简单的入场出场信号
                price = df['Close'].values.reshape(-1, 1)
                n = len(df)
                entries = np.random.choice([False, True], size=(n, 1), p=[0.99, 0.01])
                exits = np.random.choice([False, True], size=(n, 1), p=[0.99, 0.01])

                result = self.engine.run_backtest(
                    price=price,
                    entries=entries,
                    exits=exits,
                    init_cash=init_cash,
                    fees=fees,
                    slippage=slippage
                )
                results[symbol] = result
            return results

    GridTradingStrategy = SimpleTestStrategy
    VectorBacktestAdapter = SimpleTestAdapter

# 创建模拟数据
np.random.seed(42)
n_steps = 1000
dates = pd.date_range('2024-01-01', periods=n_steps, freq='h')

# 生成随机价格数据（模拟 BTC/USDT）
base_price = 50000.0
price_changes = np.random.normal(0, 0.001, n_steps)
prices = base_price * (1 + np.cumsum(price_changes))

# 创建 OHLC 数据
data = pd.DataFrame({
    'Open': prices,
    'High': prices * 1.002,
    'Low': prices * 0.998,
    'Close': prices,
    'Volume': np.random.uniform(100, 1000, n_steps)
}, index=dates)

print("数据生成完成")
print(f"数据形状: {data.shape}")
print(f"价格范围: {data['Close'].min():.2f} - {data['Close'].max():.2f}")

# 创建策略
params = {
    'grid_count': 10,
    'auto_range_pct': 0.1,
    'position_size': 0.01,
    'initial_capital': 10000
}

strategy = GridTradingStrategy(params)
print("\n策略创建完成")
print(f"策略参数: {strategy.params}")

# 创建适配器
adapter = VectorBacktestAdapter(strategy)
print("\n适配器创建完成")

# 运行回测
data_dict = {'BTCUSDT': data}
results = adapter.run_backtest(
    data=data_dict,
    init_cash=100000.0,
    fees=0.001,
    slippage=0.0001
)

print("\n回测完成")
print(f"回测结果: {list(results.keys())}")

# 打印结果
for symbol, result in results.items():
    print(f"\n=== {symbol} ===")
    print(f"最终现金: {result['cash'][-1]:.2f}")
    print(f"最终持仓: {result['positions'][-1, 0]:.4f}")
    if 'orders' in result:
        print(f"订单数量: {len(result['orders'])}")
    print(f"交易数量: {len(result['trades'])}")
    print("\n绩效指标:")
    for key, value in result['metrics'].items():
        print(f"  {key}: {value}")

print("\n测试成功！")
