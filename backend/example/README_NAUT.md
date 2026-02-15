# NautilusTrader ETHUSDT 回测示例

基于 NautilusTrader 的事件驱动回测示例，使用 ETHUSDT 数据文件。

## 数据文件

**路径**: `/Users/liupeng/workspace/quant/QuantCell/backend/data/ETHUSDT.csv`

**格式**: OHLCV K线数据
- 字段: timestamp, open, high, low, close, volume, symbol
- 时间戳: Unix 毫秒时间戳
- 周期: 15分钟K线

## 文件说明

### 策略文件 (strategies/)

#### 1. sma_cross_strategy.py
SMA 交叉策略实现
- 快速 SMA (默认10周期) 上穿慢速 SMA (默认20周期) 时买入
- 快速 SMA 下穿慢速 SMA 时卖出

#### 2. ema_cross_strategy.py
EMA 交叉策略实现
- 快速 EMA (默认12周期) 上穿慢速 EMA (默认26周期) 时买入
- 快速 EMA 下穿慢速 EMA 时卖出
- 包含止损逻辑 (默认2%)

### 回测示例文件

#### 1. demo_nautilus_eth_basic.py
基础回测示例
- 展示最基本的回测流程
- 使用 SMA 交叉策略
- 初始资金: 100,000 USDT
- 交易数量: 0.1 ETH

**运行**:
```bash
python demo_nautilus_eth_basic.py
```

#### 2. demo_nautilus_eth_ema.py
EMA 策略回测示例
- 使用 EMA 交叉策略
- 包含止损逻辑
- 展示更复杂的策略实现

**运行**:
```bash
python demo_nautilus_eth_ema.py
```

#### 3. demo_nautilus_eth_analysis.py
回测结果分析示例
- 详细的绩效指标计算
- 交易统计分析
- 结果导出功能

**运行**:
```bash
python demo_nautilus_eth_analysis.py
```

## 回测流程

### 1. 数据加载
```python
import pandas as pd

# 读取 CSV
df = pd.read_csv("/Users/liupeng/workspace/quant/QuantCell/backend/data/ETHUSDT.csv")

# 转换时间戳
df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
```

### 2. 创建交易品种
```python
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model import InstrumentId, Symbol, Venue

instrument = CryptoPerpetual(
    instrument_id=InstrumentId(Symbol("ETHUSDT"), Venue("BINANCE")),
    # ... 其他参数
)
```

### 3. 数据转换
```python
from nautilus_trader.persistence.wranglers import BarDataWrangler
from nautilus_trader.model.data import BarType, BarSpecification

bar_type = BarType(
    instrument_id=instrument.id,
    bar_spec=BarSpecification(step=15, aggregation=BarAggregation.MINUTE, price_type=PriceType.LAST),
)

wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
bars = wrangler.process(df)
```

### 4. 创建回测引擎
```python
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.config import BacktestEngineConfig

config = BacktestEngineConfig(trader_id=TraderId("BACKTEST-001"))
engine = BacktestEngine(config=config)
```

### 5. 添加场所和数据
```python
engine.add_venue(Venue("BINANCE"), account_type=AccountType.MARGIN, ...)
engine.add_instrument(instrument)
engine.add_data(bars)
```

### 6. 添加策略
```python
from strategies.sma_cross_strategy import SMACrossStrategy

strategy = SMACrossStrategy(instrument=instrument, fast_period=10, slow_period=20)
engine.add_strategy(strategy)
```

### 7. 运行回测
```python
engine.run()
```

### 8. 获取结果
```python
# 账户报告
account_report = engine.trader.generate_account_report(Venue("BINANCE"))

# 成交记录
fills_report = engine.trader.generate_order_fills_report()

# 持仓报告
positions_report = engine.trader.generate_positions_report()
```

## 策略开发指南

### 创建自定义策略

```python
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import Bar

class MyStrategy(Strategy):
    def __init__(self, instrument, ...):
        super().__init__()
        self.instrument = instrument
        # ...
        
    def on_start(self):
        """策略启动时调用"""
        pass
        
    def on_bar(self, bar: Bar):
        """处理每个 Bar 数据"""
        # 获取当前持仓
        position = self.portfolio.position(bar.bar_type.instrument_id)
        
        # 交易逻辑
        if ...:
            order = self.order_factory.market(...)
            self.submit_order(order)
            
    def on_stop(self):
        """策略停止时调用"""
        pass
```

## 依赖

- nautilus_trader
- pandas
- numpy

## 注意事项

1. 数据时间戳需要转换为 datetime 格式
2. 交易品种需要正确定义精度和限制
3. 策略中需要检查指标是否初始化完成
4. 回测完成后需要调用 `engine.dispose()` 释放资源

## 参考文档

- [NautilusTrader 官方文档](https://nautilustrader.io/docs/latest/)
- [BacktestEngine API](https://nautilustrader.io/docs/latest/api_reference/backtest)
- [数据加载指南](https://nautilustrader.io/docs/latest/concepts/data)
