# QUANTCELL 统一策略引擎

## 架构概述

QUANTCELL 统一策略引擎是一个高性能、跨平台的量化交易策略框架，支持回测和实盘两种模式。

### 核心特性

1. **统一接口**：策略代码一次编写，同时支持回测和实盘
2. **双模式执行**：
   - 回测模式：使用 Cython 编译的向量化引擎（借鉴 VectorBT）
   - 实盘模式：使用事件驱动引擎（借鉴 VNPY）
3. **跨平台编译**：Cython 编译核心计算代码，支持 Windows/Linux/macOS
4. **加密货币原生支持**：永续合约、资金费率、高精度小数（8 位精度）
5. **高性能**：Cython 编译比纯 Python 快 10-100 倍

## 模块结构

```
backend/strategy/
├── core/                    # 核心引擎模块
│   ├── __init__.py
│   ├── strategy_base.py     # 统一策略基类
│   ├── event_engine.py       # 事件引擎（实盘用）
│   └── vector_engine.py      # 向量引擎（回测用）
├── crypto/                  # 加密货币支持
│   ├── __init__.py
│   └── perpetual_contract.py # 永续合约
├── cython/                 # Cython 编译模块
│   ├── __init__.py
│   ├── portfolio_sim.pyx     # 投资组合模拟
│   ├── signal_convert.pyx     # 信号转换
│   ├── metrics_calc.pyx      # 指标计算
│   └── funding_calc.pyx       # 资金费率计算
├── adapters/                # 适配器模块
│   ├── __init__.py
│   └── vector_adapter.py    # 向量回测适配器
├── strategies/               # 策略实现
│   ├── __init__.py
│   └── grid_trading_v2.py # 网格交易策略
└── __init__.py
```

## 快速开始

### 1. 编译 Cython 模块

```bash
cd backend/strategy/cython
python setup.py build_ext --inplace
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
- NumPy 向量化操作
- Cython 编译核心函数
- 支持多资产并行回测

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

| 维度 | 纯 Python | Cython | 提升 |
|------|----------|---------|------|
| 订单模拟 | 1x | 10-100x | 显著 |
| 信号转换 | 1x | 5-50x | 显著 |
| 指标计算 | 1x | 10-100x | 显著 |
| 内存占用 | 高 | 低 | 显著 |

## 跨平台支持

### Windows
```bash
python setup.py build_ext --inplace
```

### Linux/macOS
```bash
python setup.py build_ext --inplace --define=CYTHON_TRACE=0
```

### 预编译支持

提供预编译的 `.so`（Linux/macOS）和 `.pyd`（Windows）文件，用户无需自行编译。

## 下一步

1. **实现实盘适配器**：将 UnifiedStrategyBase 适配到事件引擎
2. **实现网关模块**：支持多种交易所（Binance, OKX, Bybit 等）
3. **编写更多示例策略**：展示新架构的各种用法
4. **编写单元测试**：确保代码质量和稳定性
5. **性能优化**：进一步优化 Cython 代码

## 技术栈

- **Python 3.8+**
- **NumPy**: 数值计算
- **Pandas**: 数据处理
- **Cython 3.0+**: 性能优化
- **Loguru**: 日志记录

## 参考项目

- **VNPY**: 事件驱动架构、实盘交易
- **VectorBT**: 向量化回测、高性能计算
- **WorldQuant Alpha101**: Alpha 因子策略

## 许可证

MIT License
