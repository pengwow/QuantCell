# QUANTCELL 统一策略引擎

## 架构概述

QUANTCELL 统一策略引擎是一个高性能、跨平台的量化交易策略框架，支持回测和实盘两种模式。

### 核心特性

1. **统一接口**：策略代码一次编写，同时支持回测和实盘
2. **双模式执行**：
   - 回测模式：使用 Numba JIT 编译的向量化引擎（替代 Cython）
   - 实盘模式：使用事件驱动引擎（借鉴 VNPY）
3. **跨平台编译**：Numba JIT 编译核心计算代码，支持 Windows/Linux/macOS
4. **加密货币原生支持**：永续合约、资金费率、高精度小数（8 位精度）
5. **高性能**：Numba JIT 编译比纯 Python 快 10-100 倍，环境依赖更简单

## 模块结构

```
backend/strategy/
├── core/                          # 核心引擎模块
│   ├── __init__.py
│   ├── strategy_base.py          # 统一策略基类
│   ├── event_engine.py          # 事件引擎（实盘用）
│   ├── vector_engine.py         # 向量引擎（回测用）
│   └── numba_functions.py      # Numba JIT 编译函数
├── crypto/                        # 加密货币支持
│   ├── __init__.py
│   └── perpetual_contract.py # 永续合约
├── cython/                       # Cython 编译模块（已废弃）
│   ├── portfolio_sim.pyx         # 投资组合模拟
│   ├── signal_convert.pyx         # 信号转换
│   ├── metrics_calc.pyx          # 指标计算
│   ├── funding_calc.pyx           # 资金费率计算
│   ├── setup.py                 # 编译配置
│   └── pyproject.toml           # 项目配置
├── adapters/                      # 适配器模块
│   ├── __init__.py
│   └── vector_adapter.py        # 向量回测适配器
├── strategies/                     # 策略实现
│   ├── __init__.py
│   └── grid_trading_v2.py # 网格交易策略
├── benchmark_performance.py         # 性能基准测试
└── README_NEW_ARCHITECTURE.md  # 架构文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install numpy pandas numba loguru
```

### 2. 使用新架构编写策略

```python
from backend.strategy import UnifiedStrategyBase

class MyStrategy(UnifiedStrategyBase):
    def on_init(self):
        self.write_log("策略初始化")
    
    def on_bar(self, bar):
        # 获取当前价格
        current_price = bar['close']
        
        # 简单的均线策略
        if current_price > self.sma_20:
            self.buy('BTCUSDT', current_price, 0.01)
        elif current_price < self.sma_20:
            self.sell('BTCUSDT', current_price, 0.01)
    
    def on_order(self, order):
        self.write_log(f"订单状态: {order['status']}")
    
    def on_trade(self, trade):
        self.write_log(f"成交: {trade['price']}")
```

### 3. 运行回测

```python
import pandas as pd
from backend.strategy import GridTradingStrategy, VectorBacktestAdapter

# 加载数据
data = pd.read_csv('btcusdt_1h.csv')
data_dict = {'BTCUSDT': data}

# 创建策略
params = {
    'grid_count': 10,
    'auto_range_pct': 0.1,
    'position_size': 1.0,
    'initial_capital': 10000
}
strategy = GridTradingStrategy(params)

# 创建适配器
adapter = VectorBacktestAdapter(strategy)

# 运行回测
results = adapter.run_backtest(
    data=data_dict,
    init_cash=100000.0,
    fees=0.001,
    slippage=0.0001
)

# 查看结果
print(results['BTCUSDT']['metrics'])
```

### 4. 参数优化

```python
# 定义参数范围
param_ranges = {
    'grid_count': [5, 10, 15, 20],
    'auto_range_pct': [0.05, 0.1, 0.15, 0.2]
}

# 运行参数优化
best_result = adapter.optimize_parameters(
    data=data_dict,
    param_ranges=param_ranges,
    metric='sharpe_ratio'
)

print(f"最优参数: {best_result['params']}")
print(f"最优分数: {best_result['score']}")
```

### 5. 性能基准测试

```bash
cd backend/strategy
python benchmark_performance.py
```

## 核心模块说明

### UnifiedStrategyBase（统一策略基类）

提供统一的策略接口，支持回测和实盘两种模式。

**主要方法**：
- `on_init()`: 策略初始化回调
- `on_bar(bar)`: K线数据回调
- `on_tick(tick)`: Tick 数据回调（实盘模式）
- `on_order(order)`: 订单状态更新回调
- `on_trade(trade)`: 成交回调
- `on_funding_rate(funding_rate, mark_price)`: 资金费率回调（永续合约）

**交易方法**：
- `buy(symbol, price, volume)`: 买入
- `sell(symbol, price, volume)`: 卖出
- `long(symbol, price, volume)`: 开多
- `short(symbol, price, volume)`: 开空
- `cover(symbol, price, volume)`: 平多
- `close_short(symbol, price, volume)`: 平空

### EventEngine（事件引擎）

事件驱动架构，用于实盘模式。

**主要方法**：
- `register(event_type, handler)`: 注册事件处理器
- `unregister(event_type, handler)`: 注销事件处理器
- `put(event_type, data)`: 推送事件
- `start()`: 启动事件引擎
- `stop()`: 停止事件引擎

**事件类型**：
- `EventType.TICK`: Tick 数据
- `EventType.BAR`: K线数据
- `EventType.ORDER`: 订单状态更新
- `EventType.TRADE`: 成交
- `EventType.POSITION`: 持仓更新
- `EventType.ACCOUNT`: 账户更新
- `EventType.FUNDING_RATE`: 资金费率（永续合约）

### VectorEngine（向量引擎）

向量化回测引擎，用于回测模式的高性能计算。

**主要方法**：
- `run_backtest(price, entries, exits, init_cash, fees, slippage)`: 运行向量回测

**性能优化**：
- Numba JIT 编译核心函数
- NumPy 向量化操作
- 支持多资产并行回测

### numba_functions.py（Numba JIT 编译函数）

包含所有使用 Numba JIT 编译的高性能函数。

**主要函数**：
- `simulate_orders()`: 订单模拟（@njit(cache=True, fastmath=True)）
- `signals_to_orders()`: 信号转换（@njit(cache=True, fastmath=True)）
- `calculate_metrics()`: 指标计算（@njit(cache=True, fastmath=True)）
- `calculate_funding_rate()`: 资金费率计算（@njit(cache=True, fastmath=True)）
- `calculate_funding_payment()`: 资金费支付计算（@njit(cache=True, fastmath=True)）
- `calculate_trades()`: 交易记录计算（@njit(cache=True, fastmath=True)）

**Numba 优势**：
- **环境简化**：只需要 `pip install numba`，无需复杂的编译配置
- **跨平台**：自动适配 Windows/Linux/macOS
- **缓存机制**：`@njit(cache=True)` 首次编译后缓存，后续调用更快
- **快速数学**：`fastmath=True` 优化数学运算

### PerpetualContract（永续合约）

永续合约支持，包括资金费率计算。

**主要方法**：
- `calculate_funding_rate(index_price, mark_price)`: 计算资金费率
- `calculate_funding_payment(position_size, funding_rate)`: 计算资金费支付
- `should_rebalance(current_time, last_funding_time)`: 判断是否需要调仓

**资金费率公式**：
```
funding_rate = (mark_price - index_price) / index_price
funding_rate = max(min(funding_rate, 0.75%), -0.75%)
```

### CryptoUtils（加密货币工具）

高精度小数工具类。

**主要方法**：
- `round_price(price)`: 价格四舍五入（8 位精度）
- `round_size(size)`: 数量向下取整（3 位精度）
- `calculate_notional(price, size)`: 计算名义价值
- `calculate_pnl(entry_price, exit_price, size, direction)`: 计算盈亏

### VectorBacktestAdapter（向量回测适配器）

将 UnifiedStrategyBase 适配到 VectorEngine。

**主要方法**：
- `run_backtest(data, init_cash, fees, slippage)`: 运行向量回测
- `optimize_parameters(data, param_ranges, metric)`: 参数优化
- `get_equity_curve(symbol)`: 获取权益曲线
- `get_trades(symbol)`: 获取交易记录
- `get_summary()`: 获取回测摘要

## 示例策略

### GridTradingStrategy（网格交易策略）

在设定的价格区间内，将资金分成若干等分，在价格下跌时分批买入，在价格上涨时分批卖出。

**参数**：
- `grid_count`: 网格数量，默认为 10
- `price_range`: 价格区间，格式为 [下限, 上限]，默认为 None（自动计算）
- `auto_range_pct`: 自动计算价格区间的百分比，默认为 0.1（10%）
- `position_size`: 每个网格的仓位大小，默认为 1.0
- `initial_capital`: 初始资金，默认为 10000
- `enable_stop_loss`: 是否启用止损，默认为 False
- `stop_loss_pct`: 止损百分比，默认为 0.2（20%）
- `enable_take_profit`: 是否启用止盈，默认为 False
- `take_profit_pct`: 止盈百分比，默认为 0.3（30%）

## 性能对比

| 维度 | 纯 Python | Numba JIT | Cython | 提升 |
|------|----------|-------------|---------|------|
| 订单模拟 | 1x | 50-100x | 10-50x | 显著 |
| 信号转换 | 1x | 20-50x | 5-20x | 显著 |
| 指标计算 | 1x | 30-100x | 10-50x | 显著 |
| 内存占用 | 高 | 低 | 低 | 显著 |
| 环境依赖 | 无 | numba | 编译工具链 | 简化 |

## 架构调整说明

### 从 Cython 迁移到 Numba 的原因

1. **环境简化**：
   - Cython：需要 C++ 编译器、Python 开发头文件、复杂的编译配置
   - Numba：只需要 `pip install numba`，自动 JIT 编译

2. **跨平台支持**：
   - Cython：需要针对不同平台配置编译选项（Windows/Linux/macOS）
   - Numba：自动适配所有平台，无需额外配置

3. **开发效率**：
   - Cython：修改代码后需要重新编译，调试复杂
   - Numba：首次运行时自动编译，后续使用缓存，开发体验更好

4. **性能相当**：
   - Numba JIT 编译的性能与 Cython 相当，甚至在某些场景下更快
   - 使用 `@njit(cache=True, fastmath=True)` 可以获得接近 C 的性能

### Numba 最佳实践

1. **使用缓存**：
   ```python
   @njit(cache=True)
   def my_function(x):
       return x * 2
   ```

2. **启用快速数学**：
   ```python
   @njit(cache=True, fastmath=True)
   def my_function(x):
       return np.sqrt(x)
   ```

3. **指定类型签名**（可选）：
   ```python
   from numba import float64, int32
   
   @njit(cache=True, fastmath=True)
   def my_function(x: float64) -> float64:
       return x * 2
   ```

4. **避免 Python 对象**：
   - 在 JIT 编译函数中避免使用 Python 字典、列表等
   - 使用 NumPy 数组和基本类型

## 性能基准测试

运行基准测试脚本：

```bash
cd backend/strategy
python benchmark_performance.py
```

测试参数：
- `n_steps`: 时间步数（默认 10000）
- `n_assets`: 资产数量（默认 10）
- `n_runs`: 运行次数（默认 10）

测试内容：
- Python 实现的性能
- Numba JIT 编译的性能
- Cython 编译的性能（如果可用）

## 下一步

### 短期（1-2 周）
1. **编写更多示例策略**：展示新架构的各种用法
2. **创建单元测试**：确保代码质量和稳定性
3. **集成到现有系统**：更新 service.py 和 routes.py

### 中期（2-4 周）
1. **实现实盘适配器**：将 UnifiedStrategyBase 适配到事件引擎
2. **实现网关模块**：支持多种交易所（Binance, OKX, Bybit 等）
3. **性能优化**：进一步优化 Numba 代码

### 长期（持续）
1. **文档完善**：编写详细的 API 文档
2. **社区支持**：收集用户反馈，持续改进
3. **功能扩展**：添加更多技术指标和策略模板

## 技术栈

- **Python 3.8+**
- **NumPy**: 数值计算
- **Pandas**: 数据处理
- **Numba 0.60+**: JIT 编译（替代 Cython）
- **Loguru**: 日志记录

## 参考项目

- **VNPY**: 事件驱动架构、实盘交易
- **VectorBT**: 向量化回测、高性能计算
- **WorldQuant Alpha101**: Alpha 因子策略

## 许可证

MIT License
