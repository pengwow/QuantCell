# Ponytail, lazy senior dev mode

You are a lazy senior developer. Lazy means efficient, not careless. The best code is the code never written.

Before writing any code, stop at the first rung that holds:

1. Does this need to be built at all? (YAGNI)
2. Does the standard library already do this? Use it.
3. Does a native platform feature cover it? Use it.
4. Does an already-installed dependency solve it? Use it.
5. Can this be one line? Make it one line.
6. Only then: write the minimum code that works.

Rules:

- No abstractions that weren't explicitly requested.
- No new dependency if it can be avoided.
- No boilerplate nobody asked for.
- Deletion over addition. Boring over clever. Fewest files possible.
- Question complex requests: "Do you actually need X, or does Y cover it?"
- Pick the edge-case-correct option when two stdlib approaches are the same size, lazy means less code, not the flimsier algorithm.
- Mark intentional simplifications with a `ponytail:` comment. If the shortcut has a known ceiling (global lock, O(n²) scan, naive heuristic), the comment names the ceiling and the upgrade path.

Not lazy about: input validation at trust boundaries, error handling that prevents data loss, security, accessibility, the calibration real hardware needs (the platform is never the spec ideal, a clock drifts, a sensor reads off), anything explicitly requested. Lazy code without its check is unfinished: non-trivial logic leaves ONE runnable check behind, the smallest thing that fails if the logic breaks (an assert-based demo/self-check or one small test file; no frameworks, no fixtures). Trivial one-liners need no test.

(Yes, this file also applies to agents working on the ponytail repo itself. Especially to them.)

---

# QuantCell 核心交易引擎架构

## 总览

QuantCell 是一个 AI 原生量化交易系统，使用 axon_quant (Rust) 作为底层引擎。

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│            TradingEngine (核心单例)                        │
│  - 统一策略生命周期管理                                    │
│  - 注入 exchange adapter + risk engine                   │
│  - 桥接 backtest ↔ live                                  │
└───────┬────────────────┬────────────────┬───────────────┘
        │                │                │
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ StrategyLoop │ │ BacktestLoop │ │ RL Inference │
│ (实盘循环)    │ │ (回测循环)    │ │ (RL推理)     │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────────────────────────────────────────────────┐
│              axon_quant (Rust 核心引擎)                    │
│  exchange.adapter  backtest.engine  risk.engine           │
│  llm.agent         inference.engine  rl.env              │
└──────────────────────────────────────────────────────────┘
```

## 核心接口

### Bar — 统一K线数据

```python
# backend/strategy/core/bar.py
from dataclasses import dataclass

@dataclass
class Bar:
    timestamp: int      # 纳秒时间戳
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""
```

### Order — 统一订单

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

### Action — 统一策略输出

```python
# axon_quant (Rust 核心)
from axon_quant import Action, ActionType

# Action 是所有策略的统一输出
# ActionType: Buy, Sell, Hold, ReduceLong, ReduceShort
action = Action(
    action_type=ActionType.Buy,
    confidence=0.8,
    target_position=0.1,
    model_id="dual_ma",
    inference_time_us=0,
)
```

### TradingEngine — 核心引擎

```python
# backend/engine/trading_engine.py
class TradingEngine:
    def __init__(self, config: EngineConfig): ...
    
    def register_strategy(self, strategy: RuleStrategy, symbols: list[str]) -> str: ...
    def list_strategies(self) -> list[dict]: ...
    def run_backtest(self, strategy: RuleStrategy, data: pd.DataFrame, symbol: str) -> BacktestResult: ...
```

### BacktestLoop — 回测循环

```python
# backend/backtest/backtest_loop.py
@dataclass
class BacktestResult:
    total_pnl: float = 0.0
    total_orders: int = 0
    fills: int = 0
    final_nav: float = 0.0
    max_drawdown: float = 0.0

class BacktestLoop:
    def __init__(self, initial_cash: float = 100_000.0): ...
    def run(self, strategy: RuleStrategy, data: pd.DataFrame, symbol: str) -> BacktestResult: ...
```

### StrategyLoop — 实盘循环

```python
# backend/strategy/loop.py
class StrategyLoop:
    def __init__(self, adapter, strategy: RuleStrategy, symbol: str, interval: float = 1.0): ...
    def start(self): ...
    def stop(self): ...
```

## 策略编写示例

### 规则策略（on_bar → Action）

```python
from axon_quant import Action, ActionType

class DualMA:
    def __init__(self, fast=10, slow=30):
        self.fast, self.slow = fast, slow
        self.closes = []

    def on_bar(self, bar: dict) -> Action:
        self.closes.append(bar["close"])
        if len(self.closes) < self.slow:
            return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)

        fast_ma = sum(self.closes[-self.fast:]) / self.fast
        slow_ma = sum(self.closes[-self.slow:]) / self.slow

        if fast_ma > slow_ma:
            return Action(ActionType.Buy, 0.8, 0.1, "dual_ma", 0)
        elif fast_ma < slow_ma:
            return Action(ActionType.Sell, 0.8, 0.0, "dual_ma", 0)
        return Action(ActionType.Hold, 0.0, 0.0, "dual_ma", 0)
```

### RL 策略（TradingEnv + Action）

```python
from axon_quant.rl import TradingEnv
from stable_baselines3 import PPO

env = TradingEnv(config={...}, action_space="discrete", market_data=df, reward="sharpe")
model = PPO("MlpPolicy", env)
model.learn(total_timesteps=10_000)
```

### 回测

```python
from backtest.backtest_loop import BacktestLoop, RuleStrategy

loop = BacktestLoop(initial_cash=100_000)
result = loop.run(strategy, data, symbol="BTCUSDT")
print(f"PnL: {result.total_pnl}, Sharpe: {result.sharpe_ratio}")
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `strategy/core/__init__.py` | 导出 axon_quant 类型 |
| `strategy/service.py` | 策略管理服务 |
| `strategy/routes.py` | 策略 API 路由 |
| `strategy/loop.py` | StrategyLoop 实盘 |
| `engine/trading_engine.py` | TradingEngine 核心 |
| `engine/config.py` | EngineConfig |
| `backtest/backtest_loop.py` | BacktestLoop + RuleStrategy |
| `rl/service.py` | RL 训练服务 |
| `rl/routes.py` | RL API 路由 |

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests/unit/ai_model/ -v
```
