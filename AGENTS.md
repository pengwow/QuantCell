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
│        worker_system (StrategyManager 核心单例)           │
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
│  axon-kernel(Kernel/BarLifecycle)  axon-worker(PyKernel) │
└──────────────────────────────────────────────────────────┘
```

## 统一主回路（回测 / paper / live）

三种模式跑**同一条主回路**：`axon-kernel` 的 `Kernel`（`kernel_loop.rs`）驱动九步 per-bar 编排
（`axon-kernel/src/lifecycle.rs::BarLifecycle::on_bar_closed`）。模式差异只在装配：数据泵
（历史 `build_frames` vs 实时 `KernelPump`）与 `ExecutionSink`（`BacktestSink` 回测撮合 /
`PaperSink` 模拟盘 / 实盘 sink）。主回路本身没有 mode 分支。Python 侧由
`axon-worker::PyKernel` 薄包装，暴露为 `axon_quant.worker.Kernel`。

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

### StrategyManager — 核心引擎（worker_system 单例）

```python
# backend/worker/strategy_manager.py
# 模块级单例：worker_system = StrategyManager()
worker_system.engine_status()          # 引擎状态概览（exchange/mode/risk/策略数）
worker_system.register_strategy(...)   # 注册策略
worker_system.list_strategies()        # 策略列表
```

### BacktestLoop — 回测循环

M6 起仅作 Python 回退路径（`engine_config['runner']='python'`）；默认走统一内核，见下节。

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

### 回测编排 — 统一内核（默认） / 两条回退口

`backtest/engine_service.py` 默认构造 `axon_quant.worker.Kernel`（Rust 侧 `PyKernel`，内部调
`axon-kernel` 的 `Kernel::run_history`）。三条执行路径由 `engine_config['runner']` 选择：

| `runner` | 走哪条路 | 说明 |
|----------|----------|------|
| 缺省（`kernel`） | `worker.Kernel` | 默认路径，统一内核 `run_history` |
| `legacy`（旧名 `rust`） | `worker.BacktestRunner` | legacy 编排，M6 只冻结不删 |
| `python` | `BacktestLoop` | 纯 Python 回退 |

`data_type` 不在 `RUST_RUNNER_DATA_TYPES` 时无论 runner 配置都会退回 `BacktestLoop`。
放行条件：`data_type ∈ RUST_RUNNER_DATA_TYPES`（见 `engine_service.py` 模块常量，共 10 类 —— kline / markPriceKlines / indexPriceKlines / premiumIndexKlines / aggTrades / trades / bookDepth / bookTicker / fundingRate / openInterest，均由数据适配器聚合成 bar 形状）。期货资金费、逐 bar 特征注入、`force_liquidate` 均已由 Rust 侧支持；多品种按「每品种独立跑一个内核」执行（与 `BacktestLoop` 每品种独立资金池口径一致），跨品种聚合仍在 Python 侧。

两个语义边界（改动这块前先读 `engine_service.py` 顶部注释）：`fundingRate` 作为 data_type 是 DerivAdapter 产出的特征列，**不是** `funding_by_symbol` 的资金费结算通道，混用会双重计费；`bookDepth` / `bookTicker` 聚合出的是 mid-price 合成价，不是可撮合盘口。原生 tick / 逐档 book 驱动的撮合不在放行范围（需 Rust L2/L3 + 非 bar 步进编排）。

永续结算口径：`settle` 由 `market` 推导（`cm` → `coin_margin`，其余 → `usd_margin`），`contract_size` 走 `engine_config['contract_size']`（默认 1.0）。注意引擎尚未把乘数计入名义价值/盈亏，币本位账务仍是近似（详见 `engine_service.py` 里的 ponytail 注释）。

```python
# backend/strategy/rust_adapter.py —— BaseStrategy(on_bar) → Rust StrategyHost 桥接
from axon_quant import worker

kernel = worker.Kernel(initial_cash=100_000.0, interval="1h")
kernel.add_strategy(RustStrategyAdapter(strategy, initial_cash=100_000.0))
result = kernel.run(
    bars_by_symbol={"BTC/USDT": [{"timestamp": ns, "open": .., "high": .., "low": .., "close": .., "volume": ..}]},
    states_by_symbol={},
)
# legacy 回退：worker.BacktestRunner(...)，run 签名与上面一致
```

`RustStrategyAdapter` 对齐 `BacktestLoop` 语义：symbol 归一化为 `BASE/QUOTE`；`target_position` 由权益占比按 `ratio * equity / price` 换算为绝对数量；hold 保持上次目标。
三条路径输出同一 `BacktestResult` 契约。`tests/unit/backtest/test_rust_runner_parity.py` 守护
Python ↔ legacy（`runner='rust'`）逐字段一致；Kernel 与 legacy 的逐 bar 语义一致性由
axon-quant 的 kernel 单测与 M3 shadow oracle（`axon-worker::shadow`）守护。

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
# Python 回退路径（engine_config['runner']='python'）；默认走 worker.Kernel，见上文
from backtest.backtest_loop import BacktestLoop, RuleStrategy

loop = BacktestLoop(initial_cash=100_000)
result = loop.run(strategy, data, symbol="BTCUSDT")
print(f"PnL: {result.total_pnl}, Sharpe: {result.sharpe_ratio}")
```

### LLM 策略回测必须提供 replay 记录

`mode='llm'` 的策略在回测中禁止真实请求 LLM：`run_mode="backtest"` 时
`strategy/llm_replay.py::wrap_llm_provider` 会把 `llm_provider` 换成 `ReplayProvider`，
只从录制 JSONL 查表，未命中直接抛 `ReplayMissError`，不降级为 heuristic / Hold。
录制由 paper / live 的 `RecordingProvider` 完成，默认目录 `backend/data/llm_replay`
（`QUANTCELL_LLM_REPLAY_DIR` 可重定向），也可用策略参数 `llm_replay_path` 指定。

## 关键文件

| 文件 | 用途 |
|------|------|
| `strategy/core/__init__.py` | 导出 axon_quant 类型 |
| `strategy/service.py` | 策略管理服务 |
| `strategy/routes.py` | 策略 API 路由 |
| `strategy/loop.py` | StrategyLoop 实盘 |
| `worker/strategy_manager.py` | worker_system 核心单例（StrategyManager） |
| `backtest/engine_service.py` | 回测编排入口：`runner` 开关（kernel / legacy / python） |
| `backtest/backtest_loop.py` | BacktestLoop + RuleStrategy（Python 回退） |
| `strategy/rust_adapter.py` | BaseStrategy → 内核 `StrategyHost` 桥接 |
| `strategy/llm_replay.py` | LLM 决策录制 / 回放 provider |
| `rl/service.py` | RL 训练服务 |
| `rl/routes.py` | RL API 路由 |
| `axon_quant/crates/axon-kernel/src/lifecycle.rs` | 九步 per-bar 编排（回测 / paper / live 共用） |
| `axon_quant/crates/axon-worker/src/python.rs` | `PyKernel` → `worker.Kernel` Python 绑定 |

## 测试

```bash
cd backend && .venv/bin/python -m pytest tests/unit/ai_model/ -v
```
