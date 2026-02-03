# SMA 交叉策略文档

## 1. 概述

该模块实现了基于简单移动平均线（SMA）交叉的策略核心，使用新的策略架构，与回测引擎无关。

## 2. 功能介绍

- 当短期移动平均线上穿长期移动平均线时生成买入信号
- 当短期移动平均线下穿长期移动平均线时生成卖出信号
- 支持自定义短期和长期移动平均线周期
- 与回测引擎解耦，可在不同回测引擎上运行

## 3. 设计原则

- 策略逻辑与回测引擎分离，便于扩展和维护
- 遵循 StrategyCore 抽象类定义的接口规范
- 提供清晰的指标计算和信号生成逻辑
- 支持与其他策略模块的互操作性

## 4. 架构流程图

```
┌─────────────────────────┐      ┌─────────────────┐      ┌───────────────────────┐
│                         │      │                 │      │                       │
│  SmaCrossCore           │──────▶ StrategyAdapter │──────▶ BacktestingPyAdapter │
│  (SMA 交叉策略核心)      │      │                 │      │                       │
└─────────────────────────┘      └─────────────────┘      └───────────────────────┘
                                      │
                                      ▼
                             ┌───────────────────────┐
                             │                       │
                             │   VectorBTAdapter     │
                             │                       │
                             └───────────────────────┘
```

## 5. 策略核心详解

### 5.1 SmaCrossCore 类

基于SMA交叉的策略核心，是StrategyCore抽象类的具体实现。

#### 继承关系

```
StrategyCore ← SmaCrossCore
```

#### 策略参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| n1 | int | 10 | 短期移动平均线周期 |
| n2 | int | 20 | 长期移动平均线周期 |
| initial_capital | float | 10000 | 初始资金 |

#### 核心方法

##### 5.1.1 calculate_indicators(data)

计算短期和长期SMA指标。

**参数**：
- `data`: K线数据DataFrame，必须包含Close列
  - `Close`: 收盘价序列

**返回值**：
- `Dict[str, pd.Series]`: 包含SMA指标的字典
  - `sma1`: 短期移动平均线序列
  - `sma2`: 长期移动平均线序列

**异常**：
- `KeyError`: 当数据中缺少Close列时

##### 5.1.2 generate_signals(indicators)

根据SMA交叉生成交易信号。

**参数**：
- `indicators`: 包含SMA指标的字典
  - `sma1`: 短期移动平均线序列
  - `sma2`: 长期移动平均线序列

**返回值**：
- `Dict[str, pd.Series]`: 包含交易信号的字典
  - `entries`: 买入信号序列，True表示买入
  - `exits`: 卖出信号序列，True表示卖出
  - `long_entries`: 多头买入信号（与entries相同）
  - `long_exits`: 多头卖出信号（与exits相同）
  - `short_entries`: 空头买入信号（默认不使用）
  - `short_exits`: 空头卖出信号（默认不使用）

**异常**：
- `KeyError`: 当indicators中缺少sma1或sma2时

##### 5.1.3 generate_stop_loss_take_profit(data, signals, indicators)

生成止损止盈信号。

**参数**：
- `data`: K线数据DataFrame
- `signals`: 交易信号字典
- `indicators`: 指标字典

**返回值**：
- `Dict[str, pd.Series]`: 包含止损止盈信号的字典
  - `stop_loss`: 止损信号序列
  - `take_profit`: 止盈信号序列

##### 5.1.4 calculate_position_size(data, signals, indicators, capital)

计算仓位大小。

**参数**：
- `data`: K线数据DataFrame
- `signals`: 交易信号字典
- `indicators`: 指标字典
- `capital`: 可用资金

**返回值**：
- `pd.Series`: 仓位大小序列

## 6. 使用示例

### 6.1 基本使用

```python
# 1. 导入必要的模块
import pandas as pd
from backtest.strategies.sma_cross_core import SmaCrossCore
from backtest.strategies.core import StrategyRunner

# 2. 准备测试数据
data = pd.read_csv('ohlc_data.csv', index_col='datetime', parse_dates=True)

# 3. 创建策略核心实例
strategy_params = {
    'n1': 10,  # 短期 SMA 周期
    'n2': 20   # 长期 SMA 周期
}
strategy_core = SmaCrossCore(strategy_params)

# 4. 创建策略运行器
runner = StrategyRunner(strategy_core, engine="backtesting.py")

# 5. 运行回测
results = runner.run(
    data, 
    cash=10000, 
    commission=0.001,
    exclusive_orders=True
)

# 6. 切换回测引擎并再次运行
runner.switch_engine("vectorbt")
vectorbt_results = runner.run(
    data, 
    init_cash=10000, 
    fees=0.001,
    freq=data.index.freq
)
```

### 6.2 在多个引擎上并行运行

```python
# 在多个引擎上并行运行
results_dict = runner.run_on_multiple_engines(
    data, 
    engines=["backtesting.py", "vectorbt"]
)

# 处理回测结果
for engine, result in results_dict.items():
    print(f"\n{engine} 回测结果:")
    if engine == "backtesting.py":
        print(f"总收益率: {result.get('Return [%]', 0):.2f}%")
        print(f"交易次数: {result.get('# Trades', 0)}")
        print(f"最大回撤: {result.get('Max. Drawdown [%]', 0):.2f}%")
    else:
        print(f"总收益率: {result.stats().get('Total Return [%]', 0):.2f}%")
        print(f"交易次数: {result.stats().get('Total Trades', 0)}")
        print(f"最大回撤: {result.stats().get('Max Drawdown [%]', 0):.2f}%")
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

## 7. 策略逻辑详解

### 7.1 指标计算

SMA 交叉策略使用两个移动平均线：短期移动平均线（sma1）和长期移动平均线（sma2）。

计算公式：
- `sma1 = Close.rolling(window=n1).mean()`
- `sma2 = Close.rolling(window=n2).mean()`

### 7.2 信号生成

当短期移动平均线上穿长期移动平均线时生成买入信号：
- `entries = (sma1 > sma2) & (sma1.shift(1) <= sma2.shift(1))`

当短期移动平均线下穿长期移动平均线时生成卖出信号：
- `exits = (sma1 < sma2) & (sma1.shift(1) >= sma2.shift(1))`

### 7.3 多头和空头信号

SMA 交叉策略默认只生成多头信号，但可以扩展为支持空头信号：
- 多头买入信号：短期均线上穿长期均线
- 多头卖出信号：短期均线下穿长期均线
- 空头买入信号：短期均线下穿长期均线（默认不使用）
- 空头卖出信号：短期均线上穿长期均线（默认不使用）

## 8. 性能优化

### 8.1 缓存机制

策略核心内置了指标计算结果缓存机制，可以避免重复计算相同指标，提高回测效率。

### 8.2 并行处理

策略运行器支持在多个回测引擎或多个数据上并行运行策略，可以充分利用多核CPU资源，提高回测速度。

## 9. 扩展指南

### 9.1 自定义止损止盈

要实现自定义止损止盈逻辑，可以重写 `generate_stop_loss_take_profit` 方法：

```python
class CustomSmaCrossStrategy(SmaCrossCore):
    def generate_stop_loss_take_profit(self, data, signals, indicators):
        # 获取参数
        stop_loss_pct = self.params.get('stop_loss_pct', 0.02)
        take_profit_pct = self.params.get('take_profit_pct', 0.05)
        
        # 实现自定义止损止盈逻辑
        # ...
        
        return {
            'stop_loss': stop_loss_signals,
            'take_profit': take_profit_signals
        }
```

### 9.2 自定义仓位管理

要实现自定义仓位管理逻辑，可以重写 `calculate_position_size` 方法：

```python
class CustomSmaCrossStrategy(SmaCrossCore):
    def calculate_position_size(self, data, signals, indicators, capital):
        # 实现自定义仓位管理逻辑
        # ...
        
        return position_sizes
```

## 10. 最佳实践

1. **参数优化**：根据不同市场环境调整短期和长期移动平均线周期
2. **结合其他指标**：可以结合 RSI、MACD 等指标过滤信号，提高策略胜率
3. **风险控制**：实现适当的止损止盈逻辑，控制单笔交易风险
4. **回测验证**：在多个时间周期和市场环境下回测策略，验证其稳定性
5. **实盘验证**：在小资金实盘环境下验证策略，确认其实际效果

## 11. 常见问题

### 11.1 如何选择合适的移动平均线周期？

- 短期周期：通常选择 5、10、20 等较小的周期
- 长期周期：通常选择 50、100、200 等较大的周期
- 建议根据不同市场和时间周期进行回测优化，找到适合的参数组合

### 11.2 如何处理假信号？

- 结合其他指标过滤信号，如 RSI、MACD 等
- 使用更长周期的移动平均线确认趋势
- 增加信号过滤条件，如要求信号持续多个周期

### 11.3 如何提高策略胜率？

- 优化移动平均线周期参数
- 结合其他技术指标
- 实现适当的止损止盈逻辑
- 在趋势明显的市场环境下使用

## 12. 版本历史

- v1.0：初始版本，实现基本的 SMA 交叉策略
- v1.1：扩展支持多头和空头信号
- v1.2：添加了默认的止损止盈和仓位管理逻辑
- v1.3：优化了信号生成逻辑，减少假信号
