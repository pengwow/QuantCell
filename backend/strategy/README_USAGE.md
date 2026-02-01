# QUANTCELL 统一策略引擎 - 使用示例

本示例展示如何使用 QUANTCELL 统一策略引擎（Numba JIT 版本）。

## 快速开始

### 1. 安装依赖

```bash
pip install numpy pandas numba loguru
```

### 2. 使用 Numba 函数

```python
import numpy as np
from core.numba_functions import simulate_orders, signals_to_orders

# 测试订单模拟
price = np.random.rand(100, 2) * 1000.0
size = np.random.choice([0, 0.01, -0.01], size=(100, 2), p=[0.95, 0.025, 0.025])
direction = np.where(size > 0, 1, 0).astype(np.int32)

cash, positions = simulate_orders(
    price=price,
    size=size,
    direction=direction,
    fees=0.001,
    slippage=0.0001,
    init_cash=100000.0
)

print(f"最终现金: {cash[0]:.2f}")
print(f"最终持仓: {positions[-1, 0]:.4f}")
```

### 3. 使用 VectorEngine

```python
from core import VectorEngine

# 创建向量引擎
engine = VectorEngine()

# 准备测试数据
n_steps = 1000
n_assets = 3
np.random.seed(42)
price = np.random.rand(n_steps, n_assets) * 1000.0
entries = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])
exits = np.random.choice([False, True], size=(n_steps, n_assets), p=[0.99, 0.01])

# 运行回测
result = engine.run_backtest(
    price=price,
    entries=entries,
    exits=exits,
    init_cash=100000.0,
    fees=0.001,
    slippage=0.0001
)

# 查看结果
print("回测结果:")
for key, value in result['metrics'].items():
    print(f"  {key}: {value}")
```

### 4. 使用 GridTradingStrategy

```python
from strategies import GridTradingStrategy

# 创建策略参数
params = {
    'grid_count': 10,
    'auto_range_pct': 0.1,
    'position_size': 0.01,
    'initial_capital': 10000,
    'enable_stop_loss': False,
    'stop_loss_pct': 0.2,
    'enable_take_profit': False,
    'take_profit_pct': 0.3
}

# 创建策略实例
strategy = GridTradingStrategy(params)

# 初始化策略
strategy.on_init()

# 测试 K 线回调
test_bar = {
    'datetime': pd.Timestamp('2024-01-01'),
    'open': 50000.0,
    'high': 50100.0,
    'low': 49900.0,
    'close': 50000.0,
    'volume': 1000.0
}
strategy.on_bar(test_bar)

# 测试订单回调
test_order = {
    'order_id': 'test_order_001',
    'status': 'filled',
    'symbol': 'BTCUSDT',
    'direction': 'long',
    'price': 50000.0,
    'volume': 0.01
}
strategy.on_order(test_order)

# 测试成交回调
test_trade = {
    'symbol': 'BTCUSDT',
    'direction': 'long',
    'price': 50000.0,
    'volume': 0.01
}
strategy.on_trade(test_trade)

# 测试资金费率回调
strategy.on_funding_rate(0.0001, 50000.0)
```

### 5. 使用 VectorBacktestAdapter

```python
import pandas as pd
import numpy as np
from strategies import GridTradingStrategy
from adapters import VectorBacktestAdapter

# 生成测试数据
np.random.seed(42)
n_steps = 500
dates = pd.date_range('2024-01-01', periods=n_steps, freq='H')

# 生成价格数据（模拟 BTC/USDT）
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

# 创建策略
params = {
    'grid_count': 10,
    'auto_range_pct': 0.1,
    'position_size': 0.01,
    'initial_capital': 10000
}
strategy = GridTradingStrategy(params)

# 创建适配器
adapter = VectorBacktestAdapter(strategy)

# 运行回测
data_dict = {'BTCUSDT': data}
results = adapter.run_backtest(
    data=data_dict,
    init_cash=100000.0,
    fees=0.001,
    slippage=0.0001
)

# 查看结果
for symbol, result in results.items():
    print(f"\n交易对: {symbol}")
    print(f"  最终现金: {result['cash'][0]:.2f}")
    print(f"  最终持仓: {result['positions'][-1, 0]:.4f}")
    print(f"   交易数量: {len(result['trades'])}")
    print("\n  绩效指标:")
    for key, value in result['metrics'].items():
        print(f"    {key}: {value}")
```

### 6. 使用加密货币工具

```python
from trading_modules import CryptoUtils, PerpetualContract

# 创建工具实例
utils = CryptoUtils(price_precision=8, size_precision=3)

# 价格四舍五入
price = 50000.12345678
rounded_price = utils.round_price(price)
print(f"原始价格: {price}")
print(f"四舍五入: {rounded_price}")

# 数量向下取整
size = 0.012345678
rounded_size = utils.round_size(size)
print(f"原始数量: {size}")
print(f"向下取整: {rounded_size}")

# 计算名义价值
notional = utils.calculate_notional(price, size)
print(f"名义价值: {notional}")

# 计算盈亏
entry_price = 50000.0
exit_price = 50500.0
pnl = utils.calculate_pnl(entry_price, exit_price, size, 'long')
print(f"盈亏: {pnl}")

# 创建永续合约
contract = PerpetualContract('BTCUSDT', funding_interval=8)

# 计算资金费率
index_price = 50000.0
mark_price = 50100.0
funding_rate = contract.calculate_funding_rate(index_price, mark_price)
print(f"资金费率: {funding_rate:.6f}")

# 计算资金费支付
position_size = 1.0
funding_payment = contract.calculate_funding_payment(position_size, funding_rate)
print(f"资金费支付: {funding_payment}")
```

## 完整示例

### 示例 1: 简单的网格交易策略

```python
import pandas as pd
import numpy as np
from strategies import GridTradingStrategy
from adapters import VectorBacktestAdapter

# 生成测试数据
np.random.seed(42)
n_steps = 1000
dates = pd.date_range('2024-01-01', periods=n_steps, freq='H')

# 生成价格数据（模拟 BTC/USDT）
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

# 创建策略
params = {
    'grid_count': 10,
    'auto_range_pct': 0.1,
    'position_size': 0.01,
    'initial_capital': 10000
}
strategy = GridTradingStrategy(params)

# 创建适配器
adapter = VectorBacktestAdapter(strategy)

# 运行回测
data_dict = {'BTCUSDT': data}
results = adapter.run_backtest(
    data=data_dict,
    init_cash=100000.0,
    fees=0.001,
    slippage=0.0001
)

# 查看结果
for symbol, result in results.items():
    print(f"\n交易对: {symbol}")
    print(f"  最终现金: {result['cash'][0]:.2f}")
    print(f"  最终持仓: {result['positions'][-1, 0]:.4f}")
    print(f"   交易数量: {len(result['trades'])}")
    print("\n  绩效指标:")
    for key, value in result['metrics'].items():
        print(f"    {key}: {value}")

# 获取权益曲线
equity_curve = adapter.get_equity_curve('BTCUSDT')
print(f"\n权益曲线长度: {len(equity_curve)}")
print(f"权益范围: [{equity_curve.min():.2f}, {equity_curve.max():.2f}]")

# 获取交易记录
trades = adapter.get_trades('BTCUSDT')
print(f"\n交易记录数量: {len(trades)}")
if len(trades) > 0:
    print(f"第一笔交易价格: {trades.iloc[0]['price']:.2f}")

# 获取回测摘要
summary = adapter.get_summary()
print(f"\n回测摘要:")
for key, value in summary.items():
    print(f"  {key}: {value}")
```

## 性能优化

### Numba JIT 编译

Numba 使用 JIT（Just-In-Time）编译技术，可以显著提升性能：

- **@njit(cache=True)**: 首次编译后缓存，后续调用更快
- **@njit(cache=True, fastmath=True)**: 启用快速数学运算优化
- **自动类型推断**: Numba 会自动推断函数参数和返回值的类型

### 性能对比

| 实现 | 相对性能 | 说明 |
|------|----------|------|
| 纯 Python | 1x | 基准 |
| Numba JIT | 50-100x | 显著提升 |
| Cython 编译 | 10-50x | 较好提升 |

### 最佳实践

1. **使用缓存**: 所有 Numba 函数都启用了缓存
2. **快速数学**: 数值计算函数启用了快速数学
3. **避免 Python 对象**: 在 JIT 函数中避免使用字典、列表等
4. **使用 NumPy 数组**: 优先使用 NumPy 数组而非 Python 列表

## 目录结构

```
backend/
├── strategy/                          # 策略引擎核心
│   ├── core/                          # 核心引擎模块
│   │   ├── __init__.py
│   │   ├── strategy_base.py          # 统一策略基类
│   │   ├── event_engine.py          # 事件引擎
│   │   ├── vector_engine.py         # 向量引擎（使用 Numba）
│   │   └── numba_functions.py      # Numba JIT 编译函数
│   ├── trading_modules/                # 交易模块（加密货币、股票等）
│   │   ├── __init__.py
│   │   └── perpetual_contract.py  # 永续合约支持
│   ├── adapters/                      # 适配器模块
│   │   ├── __init__.py
│   │   └── vector_adapter.py        # 向量回测适配器
│   └── test_complete.py               # 完整测试套件
└── strategies/                         # 策略实现目录
    ├── __init__.py
    ├── grid_trading_v2.py      # 网格交易策略
    ├── grid_trading.py
    ├── grid_trading_core.py
    ├── MACD_Demo_Strategy.py
    ├── TestSmaCrossFlow.py
    ├── multi_timeframe_strategy.py
    └── new_strategy.py
```

## 常见问题

### Q1: Numba 函数导入失败

**问题**: `ModuleNotFoundError: No module named 'core.numba_functions'`

**解决**: 确保在正确的目录下运行 Python，并且 `core/__init__.py` 正确导出了 Numba 函数。

### Q2: 类型推断错误

**问题**: `numba.core.errors.TypingError: Failed in nopython mode pipeline`

**解决**: 
1. 避免在 JIT 函数中使用 Python 字典
2. 使用明确的 NumPy 数组类型
3. 确保所有数组操作都在 nopython 模式下有效

### Q3: 策略导入失败

**问题**: `ModuleNotFoundError: No module named 'strategies.grid_trading_v2'`

**解决**: 
1. 确保 `strategies/__init__.py` 正确导出了策略类
2. 检查文件名是否正确
3. 清除 Python 缓存：`rm -rf __pycache__`

## 下一步

1. **编写更多策略**: 基于统一策略基类编写更多策略
2. **优化性能**: 进一步优化 Numba 函数性能
3. **添加测试**: 为所有模块添加单元测试
4. **完善文档**: 编写详细的 API 文档

## 总结

QUANTCELL 统一策略引擎使用 Numba JIT 编译技术，提供了高性能的向量化回测功能。通过重新组织目录结构，将加密货币相关代码整合到 `trading_modules/` 目录，将策略实现放在 `strategies/` 目录，使项目结构更加清晰。

### 关键特性

- **Numba JIT 编译**: 50-100x 性能提升
- **统一接口**: 策略一次编写，同时支持回测和实盘
- **清晰结构**: 
  - `trading_modules/` - 交易模块（加密货币、股票等）
  - `strategies/` - 策略实现（每个策略一个独立模块）
- **加密货币支持**: 完整的永续合约和高精度工具类
- **高性能**: 向量化回测引擎，支持多资产并行回测

### 目录命名说明

- **`trading_modules/`**: 交易模块目录，包含各种交易工具和支持模块
  - `perpetual_contract.py` - 永续合约支持
  - 未来可以添加：`stock_futures.py`（股票期货）、`options.py`（期权）等

- **`strategies/`**: 策略实现目录，每个策略都是一个独立的模块
  - `grid_trading_v2.py` - 网格交易策略
  - `MACD_Demo_Strategy.py` - MACD 策略
  - `TestSmaCrossFlow.py` - 均线交叉策略
  - 未来可以添加更多策略模块
