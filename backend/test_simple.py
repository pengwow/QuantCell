# 测试新架构
import sys
import os

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import numpy as np
import pandas as pd
from strategies.grid_trading_v2 import GridTradingStrategy
from adapters.vector_adapter import VectorBacktestAdapter

# 创建模拟数据
np.random.seed(42)
n_steps = 1000
dates = pd.date_range('2024-01-01', periods=n_steps, freq='H')

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
    print(f"最终现金: {result['cash'][0]:.2f}")
    print(f"最终持仓: {result['positions'][-1, 0]:.4f}")
    print(f"订单数量: {len(result['orders'])}")
    print(f"交易数量: {len(result['trades'])}")
    print("\n绩效指标:")
    for key, value in result['metrics'].items():
        print(f"  {key}: {value}")

print("\n测试成功！")
