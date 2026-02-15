# trading engine 集成文档

## 目录

1. [概述](#概述)
2. [架构设计](#架构设计)
3. [配置说明](#配置说明)
4. [使用方法](#使用方法)
5. [策略开发](#策略开发)
6. [引擎切换](#引擎切换)
7. [故障排除](#故障排除)
8. [API 参考](#api-参考)

---

## 概述

### 什么是 trading engine

[trading engine](https://trading engine.io/) 是一个高性能的算法交易平台，专为量化交易而设计。它采用事件驱动架构，支持多资产类别、复杂订单类型和精细的撮合模拟。

**主要特性：**

- **高性能事件驱动架构**：基于 Rust 核心，提供亚微秒级延迟
- **多资产支持**：支持股票、期货、外汇、加密货币等多种资产类别
- **精细的撮合模拟**：支持限价单、市价单、止损单等多种订单类型
- **灵活的数据管理**：支持 Parquet、CSV 等多种数据格式
- **完整的交易生命周期管理**：从订单生成到成交确认的完整链路

### 为什么集成 trading engine

QuantCell 集成 trading engine 的主要优势：

| 特性 | Legacy 引擎 | trading engine 引擎 |
|------|-------------|---------------------|
| 架构 | 向量化回测 | 事件驱动回测 |
| 延迟 | 毫秒级 | 亚微秒级 |
| 订单类型 | 基础订单 | 复杂订单（限价、止损、冰山等）|
| 多资产支持 | 单资产 | 多资产并行 |
| 撮合精度 | 简化撮合 | 真实撮合模拟 |
| 可扩展性 | 中等 | 高（支持分布式）|

---

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        应用层 (Application)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  回测任务管理  │  │  策略管理    │  │  结果分析            │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                        服务层 (Service)                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                 BacktestService                          │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │  │
│  │  │ 引擎工厂    │  │ 结果适配器   │  │ 数据管理器       │  │  │
│  │  └──────┬──────┘  └─────────────┘  └─────────────────┘  │  │
│  └─────────┼────────────────────────────────────────────────┘  │
└────────────┼────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        引擎层 (Engine)                           │
│  ┌─────────────────────┐      ┌─────────────────────────────┐  │
│  │   Engine    │      │      LegacyEngine           │  │
│  │  ┌───────────────┐  │      │  ┌─────────────────────┐    │  │
│  │  │ BacktestNode  │  │      │  │  BacktestService    │    │  │
│  │  │  ┌─────────┐  │  │      │  │  (backtesting.py)   │    │  │
│  │  │  │ Engine  │  │  │      │  └─────────────────────┘    │  │
│  │  │  └────┬────┘  │  │      └─────────────────────────────┘  │
│  │  │       │       │  │                                         │
│  │  │  ┌────┴────┐  │  │                                         │
│  │  │  │ Trader  │  │  │                                         │
│  │  │  └────┬────┘  │  │                                         │
│  │  │       │       │  │                                         │
│  │  │  ┌────┴────┐  │  │                                         │
│  │  │  │Strategy │  │  │                                         │
│  │  │  └─────────┘  │  │                                         │
│  │  └───────────────┘  │                                         │
│  └─────────────────────┘                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. Engine

trading engine 回测引擎的实现类，封装了 trading engine 的核心功能。

**核心组件：**

- **BacktestNode**：trading engine 的回测执行节点
- **ParquetDataCatalog**：数据目录管理，用于加载历史数据
- **BacktestVenueConfig**：交易场所配置（模拟交易所）
- **BacktestDataConfig**：数据配置（品种、时间范围等）
- **BacktestEngineConfig**：引擎核心配置（策略、日志等）

#### 2. 策略适配器

支持两种策略类型的适配：

- **原生 trading engine 策略**：直接继承 `trading_engine.trading.strategy.Strategy`
- **Legacy 策略包装**：将基于 `StrategyBase` 的 legacy 策略包装为 trading engine 策略

#### 3. 结果适配器

将 trading engine 的回测结果转换为 QuantCell 内部标准格式，包括：

- 交易记录转换
- 持仓记录转换
- 账户信息转换
- 绩效指标计算

---

## 配置说明

### 引擎配置

#### trading engine 引擎配置

```python
# trading engine 引擎配置示例
default_config = {
    # 基础配置
    "engine_type": "default",
    "initial_capital": 100000.0,      # 初始资金
    "start_date": "2023-01-01",       # 回测开始日期
    "end_date": "2023-12-31",         # 回测结束日期
    "symbols": ["BTCUSDT"],           # 交易品种列表
    
    # 数据目录配置
    "catalog_path": "/path/to/catalog",  # Parquet 数据目录路径
    
    # 策略配置
    "strategy_config": {
        "strategy_path": "my_strategy:MyStrategy",  # 模块路径:类名
        "config_path": "my_strategy:MyStrategyConfig",  # 可选，配置类路径
        "params": {                   # 策略参数
            "fast_period": 10,
            "slow_period": 20,
        }
    },
    
    # 交易场所配置（可选）
    "venue_config": {
        "name": "SIM",                # 交易所名称
        "oms_type": "NETTING",        # OMS 类型: NETTING/HEDGING
        "account_type": "MARGIN",     # 账户类型: MARGIN/CASH
        "base_currency": "USDT",      # 基础货币
    },
    
    # 日志配置（可选）
    "log_level": "INFO",              # 日志级别: DEBUG/INFO/WARNING/ERROR
}
```

#### Legacy 引擎配置

```python
# Legacy 引擎配置示例
legacy_config = {
    "engine_type": "legacy",
    "backtest_config": {
        "symbols": ["BTCUSDT"],
        "interval": "1h",
        "start_time": "2023-01-01",
        "end_time": "2023-12-31",
        "initial_cash": 100000.0,
        "commission": 0.001,
    },
    "strategy_config": {
        "strategy_name": "SmaCrossStrategy",
        "params": {
            "fast_period": 10,
            "slow_period": 20,
        }
    }
}
```

### 默认配置

```python
# 默认引擎类型
DEFAULT_ENGINE = EngineType.DEFAULT

# default 引擎默认配置
DEFAULT_CONFIG = {
    "log_level": "INFO",
    "cache": {
        "enabled": True,
        "size_mb": 512,
        "ttl_seconds": 3600,
    },
}
```

### 配置加载

```python
from backtest.config import get_engine_config, EngineType

# 获取默认配置
config = get_engine_config(EngineType.DEFAULT)

# 获取配置并覆盖默认值
custom_config = get_engine_config(
    EngineType.DEFAULT,
    {"log_level": "DEBUG", "cache": {"size_mb": 1024}}
)
```

---

## 使用方法

### 使用 trading engine 引擎执行回测

```python
from backtest.engines import Engine

# 1. 创建引擎配置
config = {
    "initial_capital": 100000.0,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "symbols": ["BTCUSDT"],
    "catalog_path": "/path/to/catalog",
    "strategy_config": {
        "strategy_path": "my_strategy:SmaCrossStrategy",
        "params": {
            "fast_period": 10,
            "slow_period": 20,
        }
    },
    "log_level": "INFO",
}

# 2. 创建引擎实例
engine = Engine(config)

# 3. 初始化引擎
try:
    engine.initialize()
    
    # 4. 执行回测
    results = engine.run_backtest()
    
    # 5. 处理结果
    print(f"总收益率: {results['metrics']['total_return']}%")
    print(f"夏普比率: {results['metrics']['sharpe_ratio']}")
    print(f"交易次数: {results['metrics']['total_trades']}")
    
    # 获取详细结果
    trades = results['trades']
    positions = results['positions']
    equity_curve = results['equity_curve']
    
except Exception as e:
    print(f"回测执行失败: {e}")
finally:
    # 6. 清理资源
    engine.cleanup()
```

### 使用 Legacy 引擎执行回测

```python
from backtest.engines import LegacyEngine

# 1. 创建引擎配置
config = {
    "backtest_config": {
        "symbols": ["BTCUSDT"],
        "interval": "1h",
        "start_time": "2023-01-01",
        "end_time": "2023-12-31",
        "initial_cash": 100000.0,
        "commission": 0.001,
    },
    "strategy_config": {
        "strategy_name": "SmaCrossStrategy",
        "params": {
            "fast_period": 10,
            "slow_period": 20,
        }
    }
}

# 2. 创建引擎实例
engine = LegacyEngine(config)

# 3. 初始化并执行回测
try:
    engine.initialize()
    results = engine.run_backtest()
    
    print(f"任务ID: {results['task_id']}")
    print(f"状态: {results['status']}")
    print(f"成功货币对: {results['successful_currencies']}")
    
except Exception as e:
    print(f"回测执行失败: {e}")
finally:
    engine.cleanup()
```

### 使用 BacktestService 创建引擎

```python
from backtest.service import BacktestService
from backtest.config import EngineType

# 创建服务实例
service = BacktestService()

# 创建引擎配置
engine_config = {
    "engine_type": "default",  # 或 "legacy"
    "initial_capital": 100000.0,
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "symbols": ["BTCUSDT"],
    "catalog_path": "/path/to/catalog",
    "strategy_config": {
        "strategy_path": "my_strategy:MyStrategy",
        "params": {}
    }
}

# 创建引擎
engine = service.create_engine(engine_config)

if engine:
    engine.initialize()
    results = engine.run_backtest()
    engine.cleanup()
```

---

## 策略开发

### 创建原生 trading engine 策略

```python
# my_strategy.py
from trading_engine.trading.strategy import Strategy, StrategyConfig
from trading_engine.model.data import Bar
from trading_engine.model.identifiers import InstrumentId
from trading_engine.model.events import OrderFilled
from trading_engine.model.orders import MarketOrder
from trading_engine.model.position import Position


class SmaCrossConfig(StrategyConfig):
    """SMA 交叉策略配置"""
    fast_period: int = 10
    slow_period: int = 20
    instrument_id: str = "BTCUSDT.SIM"


class SmaCrossStrategy(Strategy):
    """
    简单移动平均线交叉策略
    
    当快线上穿慢线时买入，快线下穿慢线时卖出
    """
    
    def __init__(self, config: SmaCrossConfig):
        super().__init__(config)
        
        # 参数
        self.fast_period = config.fast_period
        self.slow_period = config.slow_period
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        
        # 状态
        self.prices = []
        self.fast_sma = 0.0
        self.slow_sma = 0.0
        self.position = 0
        
    def on_start(self):
        """策略启动时调用"""
        self.log.info(f"策略启动: {self.config.strategy_id}")
        self.log.info(f"快周期: {self.fast_period}, 慢周期: {self.slow_period}")
        
    def on_stop(self):
        """策略停止时调用"""
        self.log.info(f"策略停止: {self.config.strategy_id}")
        
    def on_bar(self, bar: Bar):
        """K线数据回调"""
        # 收集价格数据
        self.prices.append(float(bar.close))
        
        # 等待足够的数据
        if len(self.prices) < self.slow_period:
            return
            
        # 计算 SMA
        self.fast_sma = sum(self.prices[-self.fast_period:]) / self.fast_period
        self.slow_sma = sum(self.prices[-self.slow_period:]) / self.slow_period
        
        # 交易逻辑
        if self.fast_sma > self.slow_sma and self.position <= 0:
            # 金叉买入
            self.buy()
        elif self.fast_sma < self.slow_sma and self.position >= 0:
            # 死叉卖出
            self.sell()
            
    def buy(self):
        """买入"""
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity.from_int(1),
        )
        self.submit_order(order)
        self.position = 1
        self.log.info(f"买入信号 - 价格: {self.prices[-1]}")
        
    def sell(self):
        """卖出"""
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=Quantity.from_int(1),
        )
        self.submit_order(order)
        self.position = -1
        self.log.info(f"卖出信号 - 价格: {self.prices[-1]}")
        
    def on_order_filled(self, event: OrderFilled):
        """订单成交回调"""
        self.log.info(f"订单成交: {event}")
        
    def on_position_opened(self, position: Position):
        """持仓开仓回调"""
        self.log.info(f"持仓开仓: {position}")
        
    def on_position_closed(self, position: Position):
        """持仓平仓回调"""
        self.log.info(f"持仓平仓: {position}")
```

### 使用 Legacy 策略（自动适配）

```python
# legacy_strategy.py
from strategy.core.strategy_base import StrategyBase


class MyLegacyStrategy(StrategyBase):
    """基于 StrategyBase 的 Legacy 策略"""
    
    def __init__(self, params: dict):
        super().__init__(params)
        self.fast_period = params.get("fast_period", 10)
        self.slow_period = params.get("slow_period", 20)
        self.prices = []
        
    def on_init(self):
        """策略初始化"""
        print("策略初始化完成")
        
    def on_bar(self, bar: dict):
        """K线数据回调"""
        self.prices.append(bar["Close"])
        
        if len(self.prices) < self.slow_period:
            return
            
        fast_sma = sum(self.prices[-self.fast_period:]) / self.fast_period
        slow_sma = sum(self.prices[-self.slow_period:]) / self.slow_period
        
        if fast_sma > slow_sma:
            self.buy(bar["symbol"], bar["Close"], 1.0)
        elif fast_sma < slow_sma:
            self.sell(bar["symbol"], bar["Close"], 1.0)
            
    def on_stop(self, bar: dict):
        """策略停止"""
        print("策略停止")
```

### 策略验证

```python
from backtest.adapters.strategy_adapter import (
    validate_default_strategy,
    validate_legacy_strategy,
    detect_strategy_type,
    auto_adapt_strategy,
)

# 验证 trading engine 策略
is_valid = validate_default_strategy(MyDefaultStrategy)

# 验证 Legacy 策略
is_valid = validate_legacy_strategy(MyLegacyStrategy)

# 自动检测策略类型
strategy_type = detect_strategy_type(MyStrategy)  # 返回 'default' 或 'legacy'

# 自动适配策略
adapted_strategy = auto_adapt_strategy(MyLegacyStrategy)
```

---

## 引擎切换

### 运行时切换引擎

```python
from backtest.service import BacktestService

service = BacktestService()

# 使用 trading engine 引擎
default_config = {
    "engine_type": "default",
    # ... 其他配置
}
engine = service.create_engine(default_config)

# 切换到 Legacy 引擎
legacy_config = {
    "engine_type": "legacy",
    # ... 其他配置
}
engine = service.create_engine(legacy_config)
```

### 性能比较

| 指标 | Legacy 引擎 | trading engine 引擎 | 提升 |
|------|-------------|---------------------|------|
| 回测速度（100万条K线）| ~5秒 | ~2秒 | 2.5x |
| 内存占用 | ~500MB | ~300MB | 1.7x |
| 订单延迟模拟 | 简化 | 真实撮合 | - |
| 多资产并行 | 串行 | 并行 | - |
| 复杂订单支持 | 有限 | 完整 | - |

### 选择建议

**使用 trading engine 引擎的场景：**

- 需要高精度的事件驱动回测
- 需要测试复杂的订单类型和策略
- 需要多资产并行回测
- 对回测速度和内存占用有较高要求

**使用 Legacy 引擎的场景：**

- 快速原型验证
- 简单的向量化策略回测
- 需要与现有 legacy 策略兼容
- 不需要复杂的撮合模拟

---

## 故障排除

### 常见问题

#### 1. 数据目录不存在

**错误信息：**
```
ValueError: 数据目录不存在: /path/to/catalog
```

**解决方案：**
```python
from pathlib import Path

# 创建数据目录
catalog_path = Path("/path/to/catalog")
catalog_path.mkdir(parents=True, exist_ok=True)

# 或者使用临时目录
import tempfile
catalog_path = tempfile.mkdtemp()
```

#### 2. 策略配置缺少必需参数

**错误信息：**
```
ValueError: 策略配置缺少必需参数: strategy_path
```

**解决方案：**
```python
config = {
    "strategy_config": {
        "strategy_path": "module:StrategyClass",  # 必需
        "params": {},  # 可选
    }
}
```

#### 3. 引擎未初始化

**错误信息：**
```
RuntimeError: 引擎未初始化，请先调用 initialize()
```

**解决方案：**
```python
engine = Engine(config)
engine.initialize()  # 必须先初始化
results = engine.run_backtest()
```

#### 4. 尚未执行回测

**错误信息：**
```
RuntimeError: 尚未执行回测，请先调用 run_backtest()
```

**解决方案：**
```python
engine.initialize()
engine.run_backtest()  # 先执行回测
results = engine.get_results()  # 然后获取结果
```

#### 5. 策略类加载失败

**错误信息：**
```
StrategyLoadError: 加载 trading engine 策略失败
```

**解决方案：**
```python
# 确保策略文件路径正确
# 确保策略类继承自 trading_engine.trading.strategy.Strategy
# 确保策略类实现了必需的方法（on_start, on_stop）

# 验证策略类
from backtest.adapters.strategy_adapter import validate_default_strategy

try:
    validate_default_strategy(MyStrategy)
except Exception as e:
    print(f"策略验证失败: {e}")
```

### 调试技巧

#### 启用详细日志

```python
config = {
    "log_level": "DEBUG",  # 启用 DEBUG 级别日志
    # ... 其他配置
}
```

#### 获取引擎实例进行调试

```python
engine.initialize()
engine.run_backtest()

# 获取 trading engine 引擎实例
default_engine = engine.get_engine_instance()

# 查询详细数据
orders_df = default_engine.trader.generate_order_fills_report()
positions_df = default_engine.trader.generate_positions_report()
account_df = default_engine.trader.generate_account_report(Venue("SIM"))
```

---

## API 参考

### Engine

基于 trading engine 的高性能回测引擎。

#### 构造函数

```python
Engine(config: Optional[Dict[str, Any]] = None)
```

**参数：**

- `config`：引擎配置字典

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `engine_type` | `EngineType` | 引擎类型，返回 `EngineType.DEFAULT` |
| `config` | `Dict[str, Any]` | 引擎配置 |
| `is_initialized` | `bool` | 引擎是否已初始化 |

#### 方法

##### initialize()

初始化回测引擎。

```python
def initialize(self) -> None
```

**异常：**

- `RuntimeError`：初始化失败
- `ValueError`：配置参数无效

##### run_backtest()

执行回测。

```python
def run_backtest(self) -> Dict[str, Any]
```

**返回：**

包含以下字段的字典：

- `trades`：交易记录列表
- `positions`：持仓记录列表
- `account`：账户信息
- `metrics`：绩效指标
- `equity_curve`：权益曲线

**异常：**

- `RuntimeError`：回测执行失败

##### get_results()

获取回测结果。

```python
def get_results(self) -> Dict[str, Any]
```

**异常：**

- `RuntimeError`：尚未执行回测

##### cleanup()

清理资源。

```python
def cleanup(self) -> None
```

##### get_node()

获取 BacktestNode 实例。

```python
def get_node(self) -> Optional[BacktestNode]
```

##### get_engine_instance()

获取 trading engine 引擎实例。

```python
def get_engine_instance(self) -> Optional[Any]
```

### LegacyEngine

基于 backtesting.py 的传统回测引擎。

#### 构造函数

```python
LegacyEngine(config: Optional[Dict[str, Any]] = None)
```

#### 方法

##### set_strategy_config()

设置策略配置。

```python
def set_strategy_config(self, config: Dict[str, Any]) -> None
```

##### set_backtest_config()

设置回测配置。

```python
def set_backtest_config(self, config: Dict[str, Any]) -> None
```

##### analyze_result()

分析回测结果。

```python
def analyze_result(self, backtest_id: str) -> Dict[str, Any]
```

##### stop_backtest()

终止回测。

```python
def stop_backtest(self, task_id: str) -> Dict[str, Any]
```

### BacktestService

回测服务主类，提供引擎工厂方法和回测管理功能。

#### 方法

##### create_engine()

创建回测引擎。

```python
def create_engine(
    self, 
    config: Optional[Dict[str, Any]] = None
) -> Optional[BacktestEngineBase]
```

**参数：**

- `config`：引擎配置，包含 `engine_type` 字段

**返回：**

- `BacktestEngineBase`：回测引擎实例

##### get_engine()

获取当前使用的回测引擎实例。

```python
def get_engine(self) -> Optional[BacktestEngineBase]
```

### 策略适配器

#### adapt_legacy_strategy()

将 Legacy 策略包装为 trading engine 策略。

```python
def adapt_legacy_strategy(
    legacy_strategy_class: Type[StrategyBase]
) -> Type[Strategy]
```

#### load_default_strategy()

加载原生 trading engine 策略。

```python
def load_default_strategy(
    strategy_path: Union[str, Path],
    strategy_name: Optional[str] = None
) -> Type[Strategy]
```

#### validate_default_strategy()

验证 trading engine 策略。

```python
def validate_default_strategy(strategy_class: Type[Strategy]) -> bool
```

#### auto_adapt_strategy()

自动适配策略。

```python
def auto_adapt_strategy(
    strategy_class: Type,
    params: Optional[Dict[str, Any]] = None
) -> Union[Type[Strategy], Strategy]
```

### 配置函数

#### get_engine_config()

获取引擎配置。

```python
def get_engine_config(
    engine_type: Optional[EngineType] = None,
    custom_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]
```

#### load_engine_config()

从字典加载引擎配置。

```python
def load_engine_config(
    config_dict: Dict[str, Any],
    engine_type_key: str = "engine_type",
) -> Dict[str, Any]
```

#### merge_config()

合并配置字典。

```python
def merge_config(
    base_config: Dict[str, Any],
    override_config: Dict[str, Any],
) -> Dict[str, Any]
```

---

## 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0.0 | 2026-02-15 | 初始版本，集成 trading engine 回测引擎 |

---

## 参考链接

- [trading engine 官方文档](https://docs.trading engine.io/)
- [trading engine GitHub](https://github.com/nautechsystems/advanced_trader)
- [QuantCell 策略架构文档](strategy_architecture.md)
- [QuantCell 回测模块设计文档](backtest_module_design.md)
