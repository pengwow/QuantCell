# NautilusTrader 集成文档

## 目录

- [1. 概述](#1-概述)
  - [1.1 NautilusTrader 框架简介](#11-nautilustrader-框架简介)
  - [1.2 集成目标和优势](#12-集成目标和优势)
  - [1.3 架构说明](#13-架构说明)
- [2. 快速开始](#2-快速开始)
  - [2.1 环境要求](#21-环境要求)
  - [2.2 安装依赖](#22-安装依赖)
  - [2.3 运行第一个回测](#23-运行第一个回测)
- [3. 核心组件](#3-核心组件)
  - [3.1 NautilusBacktestEngine](#31-nautilusbacktestengine)
  - [3.2 QuantCellNautilusStrategy](#32-quantcellnautilusstrategy)
  - [3.3 数据适配器](#33-数据适配器)
- [4. 策略开发指南](#4-策略开发指南)
  - [4.1 继承策略基类](#41-继承策略基类)
  - [4.2 实现策略逻辑](#42-实现策略逻辑)
  - [4.3 配置策略参数](#43-配置策略参数)
  - [4.4 示例：SMA 交叉策略](#44-示例sma-交叉策略)
- [5. 数据加载](#5-数据加载)
  - [5.1 从 CSV 加载数据](#51-从-csv-加载数据)
  - [5.2 从 Parquet 加载数据](#52-从-parquet-加载数据)
  - [5.3 从数据库加载数据](#53-从数据库加载数据)
  - [5.4 数据格式要求](#54-数据格式要求)
- [6. CLI 使用](#6-cli-使用)
  - [6.1 命令行参数](#61-命令行参数)
  - [6.2 使用示例](#62-使用示例)
  - [6.3 结果输出](#63-结果输出)
- [7. API 参考](#7-api-参考)
  - [7.1 引擎类 API](#71-引擎类-api)
  - [7.2 策略基类 API](#72-策略基类-api)
  - [7.3 数据适配器 API](#73-数据适配器-api)
- [8. 测试](#8-测试)
  - [8.1 运行单元测试](#81-运行单元测试)
  - [8.2 运行集成测试](#82-运行集成测试)
- [9. 故障排除](#9-故障排除)
  - [9.1 常见问题](#91-常见问题)
  - [9.2 解决方案](#92-解决方案)

---

## 1. 概述

### 1.1 NautilusTrader 框架简介

[NautilusTrader](https://nautilustrader.io/docs/) 是一个高性能的算法交易平台，专为量化交易和回测设计。它采用事件驱动架构，具有以下特点：

- **高性能**：使用 Rust 编写核心引擎，Python 提供灵活的策略接口
- **类型安全**：全面的类型注解支持
- **事件驱动**：基于事件的处理机制，模拟真实交易环境
- **模块化设计**：易于扩展和定制
- **丰富的数据支持**：支持多种数据格式和来源

### 1.2 集成目标和优势

QuantCell 项目集成 NautilusTrader 的主要目标：

1. **统一策略框架**：为项目提供标准化的策略开发接口
2. **高性能回测**：利用 NautilusTrader 的高性能引擎进行回测
3. **灵活的数据接入**：支持 CSV、Parquet、数据库等多种数据源
4. **标准化结果输出**：统一的回测结果格式，便于分析和比较

集成优势：

- 无需从零构建回测引擎
- 利用成熟的交易执行逻辑
- 支持复杂的订单类型和风控规则
- 提供详细的交易报告和绩效分析

### 1.3 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                    QuantCell 项目架构                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐      ┌──────────────────────────────┐ │
│  │   策略层         │      │   SMA 交叉策略               │ │
│  │   (Strategies)   │      │   自定义策略...              │ │
│  └────────┬─────────┘      └──────────────────────────────┘ │
│           │                                                 │
│  ┌────────▼──────────────────────────────────────────────┐  │
│  │           QuantCellNautilusStrategy                   │  │
│  │              (策略基类封装)                            │  │
│  └────────┬───────────────────────────────────────────────┘  │
│           │                                                  │
│  ┌────────▼──────────────────────────────────────────────┐  │
│  │           NautilusBacktestEngine                      │  │
│  │              (回测引擎封装)                            │  │
│  └────────┬───────────────────────────────────────────────┘  │
│           │                                                  │
│  ┌────────▼──────────────────────────────────────────────┐  │
│  │           NautilusTrader BacktestEngine               │  │
│  │              (核心回测引擎)                            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 快速开始

### 2.1 环境要求

- Python 3.10+
- 内存：至少 4GB RAM（推荐 8GB+）
- 操作系统：Linux/macOS/Windows

### 2.2 安装依赖

使用 `uv` 安装 NautilusTrader 依赖：

```bash
cd backend
uv add nautilus-trader
```

或者手动更新 `pyproject.toml`：

```toml
[project]
dependencies = [
    "nautilus-trader>=1.200.0",
]
```

然后同步依赖：

```bash
uv sync
```

### 2.3 运行第一个回测

以下是一个完整的回测示例：

```python
from decimal import Decimal
from pathlib import Path

from nautilus_trader.model import Venue
from nautilus_trader.model.data import BarType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Price, Quantity

from backend.backtest.engines.nautilus_engine import NautilusBacktestEngine
from backend.strategies.sma_cross_nautilus import (
    SmaCrossNautilusConfig,
    SmaCrossNautilusStrategy,
)


def run_first_backtest():
    # 1. 创建引擎配置
    engine_config = {
        "trader_id": "BACKTEST-001",
        "log_level": "INFO",
        "initial_capital": 100000.0,
    }
    
    # 2. 初始化引擎
    engine = NautilusBacktestEngine(engine_config)
    engine.initialize()
    
    # 3. 添加交易所
    venue = engine.add_venue(
        venue_name="SIM",
        starting_capital=100000.0,
        base_currency="USD",
    )
    
    # 4. 创建交易品种
    instrument = CurrencyPair(
        instrument_id=InstrumentId.from_str("EURUSD.SIM"),
        raw_symbol="EURUSD",
        base_currency=Currency.from_str("EUR"),
        quote_currency=Currency.from_str("USD"),
        price_precision=5,
        size_precision=0,
        price_increment=Price(1e-5, 5),
        size_increment=Quantity(1, 0),
        lot_size=None,
        max_quantity=Quantity(1e9, 0),
        min_quantity=Quantity(1, 0),
        max_notional=None,
        min_notional=None,
        max_price=Price(1e9, 5),
        min_price=Price(0, 5),
        margin_init=Decimal("0"),
        margin_maint=Decimal("0"),
        maker_fee=Decimal("0.0001"),
        taker_fee=Decimal("0.0001"),
        ts_event=0,
        ts_init=0,
    )
    engine.add_instrument(instrument)
    
    # 5. 加载数据
    bar_type = BarType.from_str("EURUSD.SIM-1-MINUTE-LAST-EXTERNAL")
    engine.load_data_from_csv(
        csv_path="data/eurusd_1min.csv",
        bar_type=bar_type,
        instrument=instrument,
    )
    
    # 6. 创建策略
    strategy_config = SmaCrossNautilusConfig(
        instrument_id=instrument.id,
        bar_type=bar_type,
        trade_size=Decimal("100000"),
        fast_period=10,
        slow_period=20,
    )
    strategy = SmaCrossNautilusStrategy(strategy_config)
    engine.add_strategy(strategy)
    
    # 7. 运行回测
    results = engine.run_backtest()
    
    # 8. 输出结果
    print(f"总收益率: {results['metrics']['total_return']}%")
    print(f"胜率: {results['metrics']['win_rate']}%")
    print(f"总交易次数: {results['metrics']['total_trades']}")
    
    # 9. 清理资源
    engine.cleanup()


if __name__ == "__main__":
    run_first_backtest()
```

---

## 3. 核心组件

### 3.1 NautilusBacktestEngine

`NautilusBacktestEngine` 是 QuantCell 对 NautilusTrader `BacktestEngine` 的封装类，提供简化的回测接口。

**主要功能**：

- 引擎初始化和配置
- 交易所管理
- 交易品种管理
- 数据加载（CSV/Parquet）
- 策略管理
- 回测执行
- 结果处理

**基本使用流程**：

```python
from backend.backtest.engines.nautilus_engine import NautilusBacktestEngine

# 1. 创建引擎实例
engine = NautilusBacktestEngine(config)

# 2. 初始化引擎
engine.initialize()

# 3. 添加交易所
engine.add_venue("SIM", starting_capital=100000.0)

# 4. 添加交易品种
engine.add_instrument(instrument)

# 5. 加载数据
engine.load_data_from_csv("data.csv", bar_type, instrument)

# 6. 添加策略
engine.add_strategy(strategy)

# 7. 运行回测
results = engine.run_backtest()

# 8. 清理资源
engine.cleanup()
```

### 3.2 QuantCellNautilusStrategy

`QuantCellNautilusStrategy` 是 QuantCell 项目的 NautilusTrader 策略基类，封装了常用的交易操作。

**主要特性**：

- 统一的生命周期管理（`on_start`, `on_bar`, `on_stop`）
- 简化的交易接口（`buy`, `sell`, `close_position`）
- 持仓状态查询（`is_flat`, `is_long`, `is_short`）
- 彩色日志输出

**配置类**：

```python
from backend.backtest.strategies.base import QuantCellNautilusConfig

config = QuantCellNautilusConfig(
    instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
    bar_type=BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL"),
    trade_size=Decimal("0.1"),
    log_level="INFO",
)
```

### 3.3 数据适配器

数据适配器负责将外部数据转换为 NautilusTrader 的 `Bar` 对象。

**支持的格式**：

- CSV 文件
- Parquet 文件
- 数据库（通过扩展）

**数据转换流程**：

```
外部数据 -> pandas DataFrame -> BarDataWrangler -> List[Bar] -> 引擎
```

---

## 4. 策略开发指南

### 4.1 继承策略基类

创建自定义策略需要继承 `QuantCellNautilusStrategy`：

```python
from backend.backtest.strategies.base import (
    QuantCellNautilusConfig,
    QuantCellNautilusStrategy,
)


class MyStrategyConfig(QuantCellNautilusConfig, frozen=True):
    """自定义策略配置"""
    param1: int = 10
    param2: float = 0.5


class MyStrategy(QuantCellNautilusStrategy):
    """自定义策略实现"""
    
    def __init__(self, config: MyStrategyConfig) -> None:
        super().__init__(config)
        self.config = config
        # 初始化自定义属性
        
    def _on_bar_impl(self, bar: Bar) -> None:
        """实现交易逻辑"""
        pass
```

### 4.2 实现策略逻辑

策略的核心逻辑在 `_on_bar_impl` 方法中实现：

```python
def _on_bar_impl(self, bar: Bar) -> None:
    """
    K线数据处理的具体实现
    
    Args:
        bar: K线数据对象，包含:
            - open: 开盘价
            - high: 最高价
            - low: 最低价
            - close: 收盘价
            - volume: 成交量
            - ts_event: 时间戳
    """
    # 1. 更新数据缓存
    self.close_prices.append(float(bar.close))
    
    # 2. 计算指标
    indicators = self.calculate_indicators(bar)
    
    # 3. 生成信号
    signals = self.generate_signals(indicators)
    
    # 4. 执行交易
    if signals["entry_long"] and self.is_flat():
        self.buy()
    elif signals["exit_long"] and self.is_long():
        self.sell()
```

### 4.3 配置策略参数

策略参数通过配置类定义：

```python
from decimal import Decimal
from nautilus_trader.config import StrategyConfig


class MyStrategyConfig(QuantCellNautilusConfig, frozen=True):
    """
    策略配置类
    
    Parameters
    ----------
    instrument_id : InstrumentId
        交易品种ID
    bar_type : BarType
        K线类型
    trade_size : Decimal
        交易数量
    fast_period : int
        快线周期
    slow_period : int
        慢线周期
    """
    fast_period: int = 10
    slow_period: int = 20
    trade_size: Decimal = Decimal("0.1")
```

### 4.4 示例：SMA 交叉策略

以下是完整的 SMA 交叉策略实现：

```python
from collections import deque
from decimal import Decimal

import numpy as np
from nautilus_trader.common.enums import LogColor
from nautilus_trader.model.data import Bar

from backend.backtest.strategies.base import QuantCellNautilusConfig, QuantCellNautilusStrategy


class SmaCrossNautilusConfig(QuantCellNautilusConfig, frozen=True):
    """SMA 交叉策略配置"""
    fast_period: int = 10
    slow_period: int = 20
    trade_size: Decimal = Decimal("0.1")


class SmaCrossNautilusStrategy(QuantCellNautilusStrategy):
    """
    SMA 交叉策略
    
    策略逻辑：
    1. 计算快线和慢线的 SMA
    2. 金叉（快线上穿慢线）时买入
    3. 死叉（快线下穿慢线）时卖出
    """
    
    def __init__(self, config: SmaCrossNautilusConfig) -> None:
        super().__init__(config)
        self.fast_period = config.fast_period
        self.slow_period = config.slow_period
        
        # 数据缓存
        max_period = max(self.fast_period, self.slow_period)
        self.close_prices: deque[float] = deque(maxlen=max_period * 2)
        
        # 上一次 SMA 值
        self._last_fast_sma: float | None = None
        self._last_slow_sma: float | None = None
    
    def _on_bar_impl(self, bar: Bar) -> None:
        # 收集收盘价
        close_price = float(bar.close)
        self.close_prices.append(close_price)
        
        # 检查数据是否足够
        if len(self.close_prices) < self.slow_period:
            return
        
        # 计算 SMA
        prices = np.array(self.close_prices)
        fast_sma = np.mean(prices[-self.fast_period:])
        slow_sma = np.mean(prices[-self.slow_period:])
        
        # 检测交叉信号
        if self._last_fast_sma is not None and self._last_slow_sma is not None:
            # 金叉
            if fast_sma > slow_sma and self._last_fast_sma <= self._last_slow_sma:
                if self.is_flat():
                    self.buy()
            # 死叉
            elif fast_sma < slow_sma and self._last_fast_sma >= self._last_slow_sma:
                if self.is_long():
                    self.sell()
        
        # 更新 SMA 值
        self._last_fast_sma = fast_sma
        self._last_slow_sma = slow_sma
```

---

## 5. 数据加载

### 5.1 从 CSV 加载数据

```python
from nautilus_trader.model.data import BarType

# 定义 BarType
bar_type = BarType.from_str("EURUSD.SIM-1-MINUTE-LAST-EXTERNAL")

# 加载 CSV 数据
bars = engine.load_data_from_csv(
    csv_path="data/eurusd_1min.csv",
    bar_type=bar_type,
    instrument=instrument,
    timestamp_column="timestamp",      # 时间戳列名
    timestamp_format="%Y-%m-%d %H:%M:%S",  # 时间戳格式
    columns_mapping={                  # 列名映射（可选）
        "open_price": "open",
        "close_price": "close",
    },
    sep=";",                          # 分隔符
    decimal=".",                      # 小数点符号
)
```

### 5.2 从 Parquet 加载数据

```python
# 加载 Parquet 数据
bars = engine.load_data_from_parquet(
    parquet_path="data/eurusd_1min.parquet",
    bar_type=bar_type,
    instrument=instrument,
    timestamp_column="timestamp",
)
```

### 5.3 从数据库加载数据

目前需要通过自定义方式实现：

```python
import pandas as pd
from nautilus_trader.persistence.wranglers import BarDataWrangler

# 从数据库读取数据
df = pd.read_sql("SELECT * FROM bars WHERE symbol = 'EURUSD'", db_connection)

# 转换数据
wrangler = BarDataWrangler(bar_type, instrument)
bars = wrangler.process(df)

# 添加到引擎
engine.add_data(bars)
```

### 5.4 数据格式要求

**必需列**：

| 列名 | 类型 | 说明 |
|------|------|------|
| timestamp | datetime | 时间戳 |
| open | float | 开盘价 |
| high | float | 最高价 |
| low | float | 最低价 |
| close | float | 收盘价 |
| volume | float | 成交量（可选） |

**CSV 示例**：

```csv
timestamp,open,high,low,close,volume
2023-01-01 09:00:00,1.08500,1.08550,1.08450,1.08520,1000
2023-01-01 09:01:00,1.08520,1.08580,1.08500,1.08560,1200
```

---

## 6. CLI 使用

### 6.1 命令行参数

```bash
python -m backend.backtest.cli.nautilus_backtest \
    --strategy sma_cross \
    --symbol EURUSD \
    --data-path data/eurusd_1min.csv \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --initial-capital 100000 \
    --output results/
```

**参数说明**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| --strategy | str | 是 | 策略名称 |
| --symbol | str | 是 | 交易品种 |
| --data-path | str | 是 | 数据文件路径 |
| --start-date | str | 否 | 回测开始日期 |
| --end-date | str | 否 | 回测结束日期 |
| --initial-capital | float | 否 | 初始资金 |
| --output | str | 否 | 结果输出目录 |

### 6.2 使用示例

**运行 SMA 交叉策略回测**：

```bash
cd backend
uv run python -m backend.backtest.cli.nautilus_backtest \
    --strategy sma_cross_nautilus \
    --symbol EURUSD \
    --data-path data/eurusd_1min.csv \
    --start-date 2023-01-01 \
    --end-date 2023-06-30
```

### 6.3 结果输出

回测结果包含以下文件：

```
results/
├── backtest_report.json      # 回测报告
├── trades.csv                # 交易记录
├── equity_curve.csv          # 权益曲线
├── metrics.json              # 绩效指标
└── charts/
    ├── equity_curve.png      # 权益曲线图
    └── drawdown.png          # 回撤图
```

**回测结果结构**：

```python
{
    "trades": [...],           # 交易记录列表
    "positions": [...],        # 持仓记录列表
    "account": {...},          # 账户信息
    "equity_curve": [...],     # 权益曲线数据
    "metrics": {               # 绩效指标
        "total_return": 15.5,
        "sharpe_ratio": 1.2,
        "max_drawdown": 5.3,
        "win_rate": 55.0,
        "profit_factor": 1.5,
        "total_trades": 100,
    }
}
```

---

## 7. API 参考

### 7.1 引擎类 API

#### NautilusBacktestEngine

```python
class NautilusBacktestEngine(BacktestEngineBase):
    """
    NautilusTrader 回测引擎封装类
    
    Attributes:
        engine_type: 引擎类型（EVENT_DRIVEN）
        engine: 底层 BacktestEngine 实例
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化引擎
        
        Args:
            config: 引擎配置字典
                - trader_id: 交易者ID
                - log_level: 日志级别
                - initial_capital: 初始资金
        """
    
    def initialize(self) -> None:
        """初始化回测引擎"""
    
    def add_venue(
        self,
        venue_name: str,
        oms_type: OmsType = OmsType.NETTING,
        account_type: AccountType = AccountType.MARGIN,
        starting_capital: float = 100000.0,
        base_currency: str = "USD",
        default_leverage: Decimal = Decimal(1),
    ) -> Venue:
        """
        添加交易所
        
        Args:
            venue_name: 交易所名称
            starting_capital: 初始资金
            base_currency: 基础货币
        
        Returns:
            Venue: 交易所标识符
        """
    
    def add_instrument(self, instrument: Instrument) -> None:
        """
        添加交易品种
        
        Args:
            instrument: 交易品种定义对象
        """
    
    def load_data_from_csv(
        self,
        csv_path: Union[str, Path],
        bar_type: BarType,
        instrument: Instrument,
        timestamp_column: str = "timestamp",
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
        columns_mapping: Optional[Dict[str, str]] = None,
        sep: str = ";",
        decimal: str = ".",
    ) -> List[Bar]:
        """
        从 CSV 文件加载数据
        
        Returns:
            List[Bar]: K线数据列表
        """
    
    def add_strategy(self, strategy: Strategy) -> None:
        """
        添加策略
        
        Args:
            strategy: 策略实例
        """
    
    def run_backtest(self) -> Dict[str, Any]:
        """
        运行回测
        
        Returns:
            Dict[str, Any]: 回测结果
        """
    
    def cleanup(self) -> None:
        """清理引擎资源"""
```

### 7.2 策略基类 API

#### QuantCellNautilusStrategy

```python
class QuantCellNautilusStrategy(Strategy):
    """
    QuantCell NautilusTrader 策略基类
    
    子类需要实现:
    - _on_bar_impl: K线数据处理逻辑
    """
    
    def __init__(self, config: QuantCellNautilusConfig) -> None:
        """
        初始化策略
        
        Args:
            config: 策略配置对象
        """
    
    def on_start(self) -> None:
        """
        策略启动时调用
        子类重写时需要调用 super().on_start()
        """
    
    @abstractmethod
    def _on_bar_impl(self, bar: Bar) -> None:
        """
        K线数据处理的具体实现（子类必须实现）
        
        Args:
            bar: K线数据对象
        """
    
    def on_stop(self) -> None:
        """
        策略停止时调用
        子类重写时需要调用 super().on_stop()
        """
    
    def buy(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """
        买入下单
        
        Args:
            quantity: 交易数量，默认使用 config.trade_size
            price: 订单价格（限价单需要）
            order_type: 订单类型
            time_in_force: 订单有效时间
        """
    
    def sell(
        self,
        quantity: Decimal | None = None,
        price: Decimal | None = None,
        order_type: OrderType = OrderType.MARKET,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> None:
        """卖出下单"""
    
    def close_position(self, position: Position | None = None) -> None:
        """
        平仓
        
        Args:
            position: 要平仓的持仓，None 表示平掉所有持仓
        """
    
    def get_position(self, instrument_id: InstrumentId | None = None) -> Position | None:
        """获取持仓信息"""
    
    def get_position_size(self, instrument_id: InstrumentId | None = None) -> Decimal:
        """获取持仓数量"""
    
    def is_flat(self, instrument_id: InstrumentId | None = None) -> bool:
        """检查是否空仓"""
    
    def is_long(self, instrument_id: InstrumentId | None = None) -> bool:
        """检查是否持有多头"""
    
    def is_short(self, instrument_id: InstrumentId | None = None) -> bool:
        """检查是否持有空头"""
```

### 7.3 数据适配器 API

#### BarDataWrangler

```python
from nautilus_trader.persistence.wranglers import BarDataWrangler

wrangler = BarDataWrangler(bar_type, instrument)
bars = wrangler.process(df)
```

**DataFrame 格式要求**：

```python
df = pd.DataFrame({
    "timestamp": pd.to_datetime([...]),  # 索引或列
    "open": [...],
    "high": [...],
    "low": [...],
    "close": [...],
    "volume": [...],  # 可选
})
```

---

## 8. 测试

### 8.1 运行单元测试

```bash
cd backend
uv run pytest tests/unit/backtest/engines/test_nautilus_engine.py -v
```

### 8.2 运行集成测试

```bash
cd backend
uv run pytest tests/integration/backtest/test_nautilus_integration.py -v
```

**测试覆盖内容**：

- 引擎初始化和清理
- 交易所和品种管理
- 数据加载（CSV/Parquet）
- 策略执行
- 结果计算

---

## 9. 故障排除

### 9.1 常见问题

#### Q1: 引擎初始化失败

**错误信息**：
```
RuntimeError: 引擎初始化失败: ...
```

**可能原因**：
- 配置参数无效
- 依赖未正确安装
- 内存不足

#### Q2: 数据加载失败

**错误信息**：
```
ValueError: CSV 文件缺少必需的列: ...
```

**可能原因**：
- CSV 列名不匹配
- 数据格式不正确
- 缺少必需的列（open, high, low, close）

#### Q3: 策略未执行交易

**可能原因**：
- 数据未正确加载
- 策略信号逻辑有误
- 持仓检查条件不正确

#### Q4: 内存溢出

**可能原因**：
- 加载的数据量过大
- 未调用 cleanup() 释放资源

### 9.2 解决方案

#### 引擎初始化问题

```python
# 检查配置
config = {
    "trader_id": "BACKTEST-001",  # 确保是字符串
    "log_level": "INFO",          # DEBUG, INFO, WARNING, ERROR
    "initial_capital": 100000.0,  # 浮点数
}

# 验证依赖
import nautilus_trader
print(nautilus_trader.__version__)
```

#### 数据格式问题

```python
# 检查 CSV 格式
df = pd.read_csv("data.csv")
print(df.columns.tolist())  # 确保包含 open, high, low, close
print(df.head())            # 检查数据内容

# 使用列名映射
columns_mapping = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
}
```

#### 内存优化

```python
# 分块加载大数据
chunksize = 10000
for chunk in pd.read_csv("large_file.csv", chunksize=chunksize):
    # 处理每个块
    pass

# 及时清理资源
engine.cleanup()
import gc
gc.collect()
```

#### 调试技巧

```python
# 启用调试日志
config = {"log_level": "DEBUG"}

# 添加断点
import pdb; pdb.set_trace()

# 检查策略状态
print(f"持仓状态: {strategy.is_flat()}")
print(f"K线数量: {strategy.bars_processed}")
```

---

## 参考资源

- [NautilusTrader 官方文档](https://nautilustrader.io/docs/)
- [NautilusTrader GitHub](https://github.com/nautechsystems/nautilus_trader)
- [QuantCell 项目仓库](https://github.com/your-org/quantcell)

---

*文档版本: 1.0.0*  
*最后更新: 2026-02-23*
