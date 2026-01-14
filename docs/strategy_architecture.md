# 策略架构设计文档

## 1. 概述

该模块实现了策略逻辑与回测引擎的分离，通过适配器模式支持多种回测引擎（如backtesting.py和vectorbt）。

## 2. 主要功能

1. **策略核心（StrategyCore）**：定义策略的核心逻辑，包括指标计算、信号生成、止损止盈和仓位管理
2. **策略适配器（StrategyAdapter）**：连接策略核心和具体回测引擎的桥梁
3. **策略运行器（StrategyRunner）**：统一管理不同回测引擎的策略运行

## 3. 设计原则

- **抽象与实现分离**：策略逻辑与回测引擎实现分离，便于扩展和维护
- **适配器模式**：通过适配器模式支持多种回测引擎，新增引擎只需添加适配器
- **可扩展性**：提供丰富的钩子函数，便于策略定制和扩展
- **高性能**：内置缓存机制和并行处理支持，提高回测效率

## 4. 架构流程图

```
┌─────────────────┐      ┌─────────────────┐      ┌───────────────────────┐
│                 │      │                 │      │                       │
│  StrategyCore   │──────▶ StrategyAdapter │──────▶ BacktestingPyAdapter │
│                 │      │                 │      │                       │
└─────────────────┘      └─────────────────┘      └───────────────────────┘
                                      │
                                      ▼
                             ┌───────────────────────┐
                             │                       │
                             │   VectorBTAdapter     │
                             │                       │
                             └───────────────────────┘
```

## 5. 核心类详解

### 5.1 StrategyCore

策略核心抽象类，定义策略的核心逻辑，与回测引擎无关，仅包含策略的计算和信号生成逻辑。

#### 主要方法：

- `calculate_indicators(data)`：计算策略所需的指标
- `generate_signals(indicators)`：根据指标生成交易信号
- `generate_stop_loss_take_profit(data, signals, indicators)`：生成止损止盈信号
- `calculate_position_size(data, signals, indicators, capital)`：计算仓位大小
- `run(data)`：完整运行策略，计算指标并生成信号
- `run_multiple(data_dict)`：运行多资产策略

#### 钩子函数：

- `preprocess_data(data)`：数据预处理钩子
- `filter_signals(data, signals, indicators)`：信号过滤钩子
- `generate_long_signals(indicators)`：生成多头信号
- `generate_short_signals(indicators)`：生成空头信号
- `postprocess_signals(data, signals, indicators)`：信号后处理钩子

### 5.2 StrategyAdapter

策略适配器抽象类，定义回测引擎的适配接口，连接策略核心和具体回测引擎。

#### 主要方法：

- `run_backtest(data, **kwargs)`：运行回测

### 5.3 BacktestingPyAdapter

backtesting.py 适配器，将策略核心适配到 backtesting.py 回测引擎。

### 5.4 VectorBTAdapter

vectorbt 适配器，将策略核心适配到 vectorbt 回测引擎。

### 5.5 StrategyRunner

策略运行器，统一管理不同回测引擎的策略运行。

#### 主要方法：

- `run(data, **kwargs)`：运行策略回测
- `run_on_multiple_engines(data, engines, max_workers=None, **kwargs)`：在多个回测引擎上并行运行策略
- `run_on_multiple_data(data_dict, max_workers=None, **kwargs)`：在多个数据上并行运行策略
- `switch_engine(engine)`：切换回测引擎

## 6. 使用示例

### 6.1 基本使用

```python
# 1. 创建策略核心
strategy_core = RSIStrategy(params={'rsi_period': 14, 'oversold': 30, 'overbought': 70})

# 2. 创建策略运行器
runner = StrategyRunner(strategy_core, engine="backtesting.py")

# 3. 运行回测
results = runner.run(data, cash=10000, commission=0.001)

# 4. 切换回测引擎
runner.switch_engine("vectorbt")
vectorbt_results = runner.run(data, init_cash=10000, fees=0.001)
```

### 6.2 并行运行

```python
# 在多个引擎上并行运行
results_dict = runner.run_on_multiple_engines(data, engines=["backtesting.py", "vectorbt"])

# 在多个数据上并行运行
data_dict = {
    'BTCUSDT': btc_data,
    'ETHUSDT': eth_data
}
results_dict = runner.run_on_multiple_data(data_dict)
```

### 6.3 启用缓存

```python
# 启用缓存
runner.enable_cache()

# 获取缓存统计信息
cache_stats = runner.get_cache_stats()
print(f"缓存命中次数: {cache_stats['hits']}")
print(f"缓存未命中次数: {cache_stats['misses']}")
print(f"缓存命中率: {cache_stats['hit_rate']:.2f}%")
```

## 7. 性能优化

### 7.1 缓存机制

策略核心内置了指标计算结果缓存机制，可以避免重复计算相同指标，提高回测效率。

### 7.2 并行处理

策略运行器支持在多个回测引擎或多个数据上并行运行策略，可以充分利用多核CPU资源，提高回测速度。

## 8. 扩展指南

### 8.1 添加新的策略

要添加新的策略，只需继承 StrategyCore 抽象类，并实现以下方法：

```python
class NewStrategy(StrategyCore):
    def calculate_indicators(self, data):
        # 计算指标逻辑
        pass
    
    def generate_signals(self, indicators):
        # 生成信号逻辑
        pass
```

### 8.2 添加新的回测引擎支持

要添加新的回测引擎支持，只需继承 StrategyAdapter 抽象类，并实现 run_backtest 方法：

```python
class NewEngineAdapter(StrategyAdapter):
    def run_backtest(self, data, **kwargs):
        # 运行回测逻辑
        pass
```

然后在 StrategyRunner._get_adapter 方法中添加对新适配器的支持。

## 9. 最佳实践

1. **策略逻辑与回测引擎分离**：将策略逻辑与回测引擎分离，便于在不同引擎上测试和比较策略
2. **使用钩子函数扩展**：使用策略核心提供的钩子函数扩展策略功能，避免修改核心代码
3. **启用缓存**：对于计算密集型策略，启用缓存可以显著提高回测效率
4. **并行运行**：对于多资产或多参数测试，使用并行运行可以提高回测速度
5. **标准化结果**：使用统一的结果格式，便于比较不同策略和引擎的回测结果

## 10. 常见问题

### 10.1 如何选择回测引擎？

- **backtesting.py**：适合事件驱动的回测，支持复杂的交易逻辑和可视化
- **vectorbt**：适合向量化回测，速度快，适合大规模参数优化

### 10.2 如何处理多资产策略？

使用 StrategyCore.run_multiple 方法可以处理多资产策略，或者使用 StrategyRunner.run_on_multiple_data 方法在多个数据上并行运行策略。

### 10.3 如何实现自定义指标？

使用 StrategyCore.register_indicator 方法注册自定义指标，然后在 calculate_indicators 方法中使用 calculate_custom_indicator 方法计算自定义指标。

## 11. 版本历史

- v1.0：初始版本，支持基本的策略回测功能
- v1.1：添加了缓存机制和并行处理支持
- v1.2：扩展了策略接口，支持多头和空头信号
- v1.3：添加了更多钩子函数，提高了策略的可扩展性
- v1.4：优化了回测结果比较功能，添加了更多可视化选项
