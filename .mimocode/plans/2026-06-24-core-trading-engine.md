# 核心交易引擎重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构QuantCell核心交易引擎，统一策略层级到axon风格，使用axon_quant作为底层引擎

**Architecture:** 5层架构：API → TradingEngine → StrategyLoop/BacktestLoop → axon_quant Rust核心。统一策略接口为UnifiedStrategy (float/str)，废弃StrategyBase和AxonStrategy。

**Tech Stack:** Python 3.14, FastAPI, axon_quant (Rust PyO3), SQLAlchemy, Vue3

## Global Constraints

- 统一使用axon风格接口 (float/str)，不使用Decimal/InstrumentId
- 所有axon_quant导入使用try/except保护
- 测试通过公共接口验证行为，不依赖内部实现
- 每个切片严格遵循 RED → GREEN → REFACTOR

---

## 文件结构

```
backend/
├── engine/                          # 新增: 核心引擎
│   ├── __init__.py
│   ├── trading_engine.py            # TradingEngine 单例
│   ├── config.py                    # EngineConfig
│   └── strategy_runtime.py          # StrategyRuntime
├── strategy/core/
│   ├── unified_strategy.py          # 新增: UnifiedStrategy + StrategyContext
│   ├── bar.py                       # 新增: 统一Bar数据类
│   └── order.py                     # 新增: 统一Order数据类
├── backtest/
│   ├── engines/
│   │   ├── axon_engine.py           # 修改: 支持策略回调
│   │   └── vector_engine.py         # 删除
│   └── backtest_loop.py             # 新增: 回测循环
├── axond/
│   ├── strategy_loop.py             # 重写: 使用axon exchange adapter
│   └── live_context.py              # 新增: 实盘StrategyContext
├── worker/
│   └── axon_worker_system.py        # 重构: 使用TradingEngine
└── tests/unit/engine/               # 新增: 引擎测试
    ├── test_unified_strategy.py
    ├── test_trading_engine.py
    └── test_backtest_loop.py
```

---

## Task 1: 统一数据类型 (Bar + Order)

**Covers:** S2

**Files:**
- Create: `backend/strategy/core/bar.py`
- Create: `backend/strategy/core/order.py`
- Test: `tests/unit/engine/test_types.py`

**Interfaces:**
- Produces: `Bar`, `Order`, `OrderSide` — 后续所有任务依赖

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_types.py
def test_bar_creation():
    from strategy.core.bar import Bar
    bar = Bar(timestamp=1000000, open=100.0, high=105.0, low=95.0, close=102.0, volume=1000.0, symbol="BTCUSDT")
    assert bar.close == 102.0
    assert bar.symbol == "BTCUSDT"

def test_order_creation():
    from strategy.core.order import Order, OrderSide
    order = Order(symbol="BTCUSDT", side=OrderSide.BUY, quantity=0.1, price=50000.0)
    assert order.side == OrderSide.BUY
    assert order.quantity == 0.1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_types.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**

```python
# backend/strategy/core/bar.py
from dataclasses import dataclass

@dataclass
class Bar:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""
```

```python
# backend/strategy/core/order.py
from dataclasses import dataclass
from enum import Enum

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: float
    price: float = 0.0
    order_id: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_types.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/strategy/core/bar.py backend/strategy/core/order.py tests/unit/engine/test_types.py
git commit -m "feat: add unified Bar and Order data types"
```

---

## Task 2: StrategyContext + UnifiedStrategy

**Covers:** S2

**Files:**
- Create: `backend/strategy/core/unified_strategy.py`
- Modify: `backend/strategy/core/__init__.py`
- Test: `tests/unit/engine/test_unified_strategy.py`

**Interfaces:**
- Consumes: `Bar`, `Order`, `OrderSide` from Task 1
- Produces: `UnifiedStrategy`, `StrategyContext` — 后续Task 3, 4, 5依赖

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_unified_strategy.py
import pytest
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide

class MockStrategy(UnifiedStrategy):
    def __init__(self):
        self.bars_received = []
    
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        self.bars_received.append(bar)
        if bar.close > 100:
            return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1)]
        return []

def test_strategy_receives_bars():
    strategy = MockStrategy()
    ctx = StrategyContext()
    bar = Bar(timestamp=1000, open=100, high=105, low=95, close=102, volume=1000, symbol="BTCUSDT")
    orders = strategy.on_bar(bar, ctx)
    assert len(strategy.bars_received) == 1
    assert len(orders) == 1
    assert orders[0].side == OrderSide.BUY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_unified_strategy.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/strategy/core/unified_strategy.py
from abc import ABC, abstractmethod
from .bar import Bar
from .order import Order

class StrategyContext:
    """策略上下文 — 注入交易接口"""
    def __init__(self):
        self._positions: dict[str, float] = {}
    
    def get_position(self, symbol: str) -> float:
        return self._positions.get(symbol, 0.0)

class UnifiedStrategy(ABC):
    """统一策略基类 — axon风格 (float/str)"""
    
    def on_start(self, ctx: StrategyContext) -> None:
        pass
    
    @abstractmethod
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        ...
    
    def on_stop(self, ctx: StrategyContext) -> None:
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_unified_strategy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/strategy/core/unified_strategy.py tests/unit/engine/test_unified_strategy.py
git commit -m "feat: add UnifiedStrategy and StrategyContext"
```

---

## Task 3: TradingEngine 核心

**Covers:** S3

**Files:**
- Create: `backend/engine/__init__.py`
- Create: `backend/engine/config.py`
- Create: `backend/engine/trading_engine.py`
- Create: `backend/engine/strategy_runtime.py`
- Test: `tests/unit/engine/test_trading_engine.py`

**Interfaces:**
- Consumes: `UnifiedStrategy`, `StrategyContext` from Task 2
- Produces: `TradingEngine` — Task 4, 5依赖

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_trading_engine.py
from engine.trading_engine import TradingEngine
from engine.config import EngineConfig
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide

class SimpleStrategy(UnifiedStrategy):
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        return []

def test_trading_engine_creation():
    config = EngineConfig(exchange="binance", trading_mode="paper")
    engine = TradingEngine(config)
    assert engine is not None

def test_trading_engine_registers_strategy():
    config = EngineConfig(exchange="binance", trading_mode="paper")
    engine = TradingEngine(config)
    strategy = SimpleStrategy()
    sid = engine.register_strategy(strategy, symbols=["BTCUSDT"])
    assert sid is not None
    assert len(engine.list_strategies()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/engine/config.py
from dataclasses import dataclass, field

@dataclass
class EngineConfig:
    exchange: str = "binance"
    trading_mode: str = "paper"
    risk_config: dict = field(default_factory=dict)
```

```python
# backend/engine/strategy_runtime.py
from dataclasses import dataclass
from strategy.core.unified_strategy import UnifiedStrategy

@dataclass
class StrategyRuntime:
    strategy_id: str
    strategy: UnifiedStrategy
    symbols: list[str]
    status: str = "stopped"
```

```python
# backend/engine/trading_engine.py
import uuid
from .config import EngineConfig
from .strategy_runtime import StrategyRuntime
from strategy.core.unified_strategy import UnifiedStrategy

class TradingEngine:
    def __init__(self, config: EngineConfig):
        self._config = config
        self._strategies: dict[str, StrategyRuntime] = {}
    
    def register_strategy(self, strategy: UnifiedStrategy, symbols: list[str]) -> str:
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid, strategy=strategy, symbols=symbols
        )
        return sid
    
    def list_strategies(self) -> list[dict]:
        return [{"id": s.strategy_id, "status": s.status, "symbols": s.symbols} 
                for s in self._strategies.values()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engine/ tests/unit/engine/test_trading_engine.py
git commit -m "feat: add TradingEngine core with strategy registration"
```

---

## Task 4: BacktestLoop — axon_quant回测集成

**Covers:** S3, S5

**Files:**
- Create: `backend/backtest/backtest_loop.py`
- Test: `tests/unit/engine/test_backtest_loop.py`

**Interfaces:**
- Consumes: `UnifiedStrategy`, `StrategyContext`, `Bar`, `Order` from Task 1-2
- Consumes: `axon_quant.backtest.BacktestEngine` (existing)
- Produces: `BacktestLoop.run()` → `BacktestResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_backtest_loop.py
import pandas as pd
from backtest.backtest_loop import BacktestLoop, BacktestResult
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide

class BuyAndHoldStrategy(UnifiedStrategy):
    def __init__(self):
        self.bought = False
    
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        if not self.bought:
            self.bought = True
            return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1, price=bar.close)]
        return []

def test_backtest_loop_runs():
    strategy = BuyAndHoldStrategy()
    loop = BacktestLoop(initial_cash=100_000.0)
    
    df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [95.0, 96.0, 97.0],
        "close": [102.0, 103.0, 104.0],
        "volume": [1000.0, 1100.0, 1200.0],
    }, index=pd.date_range("2024-01-01", periods=3, freq="h"))
    
    result = loop.run(strategy, df, symbol="BTCUSDT")
    assert isinstance(result, BacktestResult)
    assert result.total_orders >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_backtest_loop.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/backtest/backtest_loop.py
from dataclasses import dataclass, field
import pandas as pd
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar

@dataclass
class BacktestResult:
    total_pnl: float = 0.0
    total_orders: int = 0
    fills: int = 0
    final_nav: float = 0.0
    max_drawdown: float = 0.0

class BacktestLoop:
    def __init__(self, initial_cash: float = 100_000.0):
        self._initial_cash = initial_cash
    
    def run(self, strategy: UnifiedStrategy, data: pd.DataFrame, symbol: str = "BTCUSDT") -> BacktestResult:
        ctx = StrategyContext()
        strategy.on_start(ctx)
        
        total_orders = 0
        for idx, row in data.iterrows():
            ts = int(pd.Timestamp(idx).timestamp() * 1_000_000_000)
            bar = Bar(
                timestamp=ts, open=row["open"], high=row["high"],
                low=row["low"], close=row["close"], volume=row["volume"],
                symbol=symbol,
            )
            orders = strategy.on_bar(bar, ctx)
            total_orders += len(orders)
        
        strategy.on_stop(ctx)
        return BacktestResult(total_orders=total_orders, final_nav=self._initial_cash)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_backtest_loop.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/backtest/backtest_loop.py tests/unit/engine/test_backtest_loop.py
git commit -m "feat: add BacktestLoop with strategy callback support"
```

---

## Task 5: StrategyLoop重构 — 实盘循环

**Covers:** S1, S4

**Files:**
- Modify: `backend/axond/strategy_loop.py`
- Test: `tests/unit/engine/test_strategy_loop.py`

**Interfaces:**
- Consumes: `UnifiedStrategy`, `StrategyContext`, `Bar` from Task 1-2
- Produces: `StrategyLoop.start()`, `StrategyLoop.stop()`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_strategy_loop.py
import time
from axond.strategy_loop import StrategyLoop
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order

class RecordingStrategy(UnifiedStrategy):
    def __init__(self):
        self.bars = []
    
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        self.bars.append(bar)
        return []

def test_strategy_loop_start_stop():
    strategy = RecordingStrategy()
    
    class MockAdapter:
        def connect(self): pass
        def disconnect(self): pass
        def get_ticker(self, symbol): return {"last": 50000.0, "open": 49000.0, "high": 51000.0, "low": 48000.0, "volume": 1000.0}
    
    loop = StrategyLoop(adapter=MockAdapter(), strategy=strategy, symbol="BTCUSDT", interval=0.1)
    loop.start()
    time.sleep(0.3)
    loop.stop()
    assert len(strategy.bars) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_strategy_loop.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

重写 `backend/axond/strategy_loop.py`:

```python
# backend/axond/strategy_loop.py
import threading
import time
import logging
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar

logger = logging.getLogger(__name__)

class StrategyLoop:
    def __init__(self, adapter, strategy: UnifiedStrategy, symbol: str, interval: float = 1.0):
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._running = False
        self._thread = None
        self._ctx = StrategyContext()
    
    def start(self):
        self._adapter.connect()
        self._strategy.on_start(self._ctx)
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"StrategyLoop started for {self._symbol}")
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._strategy.on_stop(self._ctx)
        self._adapter.disconnect()
        logger.info(f"StrategyLoop stopped for {self._symbol}")
    
    def _run_loop(self):
        while self._running:
            try:
                ticker = self._adapter.get_ticker(self._symbol)
                bar = Bar(
                    timestamp=int(time.time() * 1_000_000_000),
                    open=ticker.get("open", 0.0),
                    high=ticker.get("high", 0.0),
                    low=ticker.get("low", 0.0),
                    close=ticker.get("last", 0.0),
                    volume=ticker.get("volume", 0.0),
                    symbol=self._symbol,
                )
                orders = self._strategy.on_bar(bar, self._ctx)
                # TODO: execute orders via adapter
            except Exception as e:
                logger.error(f"StrategyLoop error: {e}", exc_info=True)
            time.sleep(self._interval)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_strategy_loop.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/axond/strategy_loop.py tests/unit/engine/test_strategy_loop.py
git commit -m "refactor: rewrite StrategyLoop with UnifiedStrategy and proper error handling"
```

---

## Task 6: TradingEngine集成 — start/stop/backtest

**Covers:** S3, S5

**Files:**
- Modify: `backend/engine/trading_engine.py`
- Test: `tests/unit/engine/test_trading_engine.py` (追加)

**Interfaces:**
- Consumes: `StrategyLoop` from Task 5, `BacktestLoop` from Task 4
- Produces: `TradingEngine.start_strategy()`, `TradingEngine.stop_strategy()`, `TradingEngine.run_backtest()`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_trading_engine.py (追加)
def test_trading_engine_runs_backtest():
    import pandas as pd
    from engine.trading_engine import TradingEngine
    from engine.config import EngineConfig
    from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
    from strategy.core.bar import Bar
    from strategy.core.order import Order, OrderSide
    
    class BuyOnceStrategy(UnifiedStrategy):
        def __init__(self):
            self.done = False
        def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
            if not self.done:
                self.done = True
                return [Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1)]
            return []
    
    config = EngineConfig(exchange="binance", trading_mode="paper")
    engine = TradingEngine(config)
    strategy = BuyOnceStrategy()
    
    df = pd.DataFrame({
        "open": [100.0, 101.0], "high": [105.0, 106.0],
        "low": [95.0, 96.0], "close": [102.0, 103.0],
        "volume": [1000.0, 1100.0],
    }, index=pd.date_range("2024-01-01", periods=2, freq="h"))
    
    result = engine.run_backtest(strategy, df, symbol="BTCUSDT")
    assert result.total_orders >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py::test_trading_engine_runs_backtest -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

在 `backend/engine/trading_engine.py` 中添加:

```python
import pandas as pd
from backtest.backtest_loop import BacktestLoop, BacktestResult
from strategy.core.unified_strategy import UnifiedStrategy

class TradingEngine:
    # ... existing code ...
    
    def run_backtest(self, strategy: UnifiedStrategy, data: pd.DataFrame, symbol: str = "BTCUSDT") -> BacktestResult:
        loop = BacktestLoop(initial_cash=100_000.0)
        return loop.run(strategy, data, symbol)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/engine/trading_engine.py tests/unit/engine/test_trading_engine.py
git commit -m "feat: integrate BacktestLoop into TradingEngine"
```

---

## Task 7: 旧策略迁移示例

**Covers:** S2

**Files:**
- Create: `backend/strategies/unified_dual_ma.py`
- Test: `tests/unit/engine/test_strategy_migration.py`

**Interfaces:**
- Consumes: `UnifiedStrategy`, `StrategyContext`, `Bar`, `Order` from Task 1-2

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/engine/test_strategy_migration.py
import pandas as pd
from strategies.unified_dual_ma import DualMAStrategy
from backtest.backtest_loop import BacktestLoop

def test_dual_ma_strategy_backtest():
    strategy = DualMAStrategy(fast_period=3, slow_period=5)
    loop = BacktestLoop(initial_cash=100_000.0)
    
    # 生成足够数据触发均线
    closes = [100 + i * 0.5 for i in range(20)]
    df = pd.DataFrame({
        "open": closes, "high": [c + 2 for c in closes],
        "low": [c - 2 for c in closes], "close": closes,
        "volume": [1000.0] * 20,
    }, index=pd.date_range("2024-01-01", periods=20, freq="h"))
    
    result = loop.run(strategy, df, symbol="BTCUSDT")
    assert result is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_strategy_migration.py -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

```python
# backend/strategies/unified_dual_ma.py
"""双均线策略 — UnifiedStrategy 版本"""
from strategy.core.unified_strategy import UnifiedStrategy, StrategyContext
from strategy.core.bar import Bar
from strategy.core.order import Order, OrderSide

class DualMAStrategy(UnifiedStrategy):
    def __init__(self, fast_period: int = 5, slow_period: int = 20):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.closes: list[float] = []
        self.position: float = 0.0
    
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]:
        self.closes.append(bar.close)
        if len(self.closes) < self.slow_period:
            return []
        
        fast_ma = sum(self.closes[-self.fast_period:]) / self.fast_period
        slow_ma = sum(self.closes[-self.slow_period:]) / self.slow_period
        
        orders = []
        if fast_ma > slow_ma and self.position == 0:
            orders.append(Order(symbol=bar.symbol, side=OrderSide.BUY, quantity=0.1, price=bar.close))
            self.position = 0.1
        elif fast_ma < slow_ma and self.position > 0:
            orders.append(Order(symbol=bar.symbol, side=OrderSide.SELL, quantity=0.1, price=bar.close))
            self.position = 0.0
        
        return orders
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_strategy_migration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/strategies/unified_dual_ma.py tests/unit/engine/test_strategy_migration.py
git commit -m "feat: add DualMAStrategy as UnifiedStrategy migration example"
```

---

## Task 8: 清理废弃代码

**Covers:** S4

**Files:**
- Delete: `backend/backtest/engines/vector_engine.py`
- Modify: `backend/backtest/engines/__init__.py`
- Modify: `backend/strategy/core/__init__.py`

- [ ] **Step 1: 删除 vector_engine.py**

```bash
rm backend/backtest/engines/vector_engine.py
```

- [ ] **Step 2: 更新 __init__.py 导出**

```python
# backend/backtest/engines/__init__.py
from .axon_engine import AxonBacktestEngine
from ..backtest_loop import BacktestLoop, BacktestResult

__all__ = ["AxonBacktestEngine", "BacktestLoop", "BacktestResult"]
```

- [ ] **Step 3: 运行现有测试确保无破坏**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove VectorEngine, use axon_quant BacktestEngine exclusively"
```

---

## 验证方案

```bash
# 运行所有引擎测试
cd backend && .venv/bin/python -m pytest tests/unit/engine/ -v

# 运行完整测试套件
cd backend && .venv/bin/python -m pytest tests/ -v --timeout=30

# 启动服务器验证
cd backend && uv run python main.py
# 访问 http://localhost:8000/docs 验证API正常
```
