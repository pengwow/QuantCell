# QuantCell 核心交易引擎重构设计

> 日期: 2026-06-24
> 状态: 已批准

## [S1] 架构总览

5层架构：API → TradingEngine → StrategyLoop/BacktestLoop/RLInference → axon_quant Rust核心

```
┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│            TradingEngine (新核心单例)                      │
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

## [S2] 统一策略接口

废弃 `StrategyBase` (Decimal/InstrumentId) 和 `AxonStrategy` (float/str)，统一为 axon 风格 (float/str)。

```python
class UnifiedStrategy(ABC):
    """统一策略基类 — axon风格 (float/str)"""
    
    def on_start(self, ctx: StrategyContext) -> None: ...
    def on_bar(self, bar: Bar, ctx: StrategyContext) -> list[Order]: ...
    def on_stop(self, ctx: StrategyContext) -> None: ...
    
    # 交易接口 (由StrategyContext注入)
    def buy(self, symbol: str, quantity: float, price: float = 0) -> str: ...
    def sell(self, symbol: str, quantity: float, price: float = 0) -> str: ...
    def cancel(self, order_id: str) -> bool: ...
    def get_position(self, symbol: str) -> float: ...
```

## [S3] TradingEngine 核心

统一交易引擎，管理策略、数据、执行。

```python
class TradingEngine:
    def __init__(self, config: EngineConfig):
        self.exchange = create_exchange_adapter(config.exchange)
        self.risk_engine = create_risk_engine(config.risk)
        self._strategies: dict[str, StrategyRuntime] = {}
    
    def start_strategy(self, strategy: UnifiedStrategy, symbols: list[str]) -> str: ...
    def stop_strategy(self, strategy_id: str) -> bool: ...
    def run_backtest(self, strategy: UnifiedStrategy, data: pd.DataFrame) -> BacktestResult: ...
```

## [S4] 关键变更清单

| 组件 | 变更 | 原因 |
|------|------|------|
| `strategy/core/strategy.py` | 废弃StrategyBase | 被UnifiedStrategy替代 |
| `axond/axon_strategy.py` | 废弃AxonStrategy | 被UnifiedStrategy替代 |
| `axond/strategy_loop.py` | 重写 | 修复adapter注入、错误处理、数据源 |
| `worker/axon_worker_system.py` | 重构 | 使用TradingEngine统一管理 |
| `backtest/engines/axon_engine.py` | 增强 | 支持策略回调 |
| `backtest/engines/vector_engine.py` | 删除 | 被axon_quant替代 |
| `exchange/base.py` | 增强 | 添加subscribe()方法 |
| `realtime/` | 保留但不再主用 | 数据源切换到axon_quant exchange |

## [S5] 实施顺序

1. **UnifiedStrategy** — 定义统一接口 + StrategyContext
2. **TradingEngine** — 核心引擎，连接exchange/risk/backtest
3. **StrategyLoop重构** — 使用axon_quant exchange adapter
4. **BacktestLoop** — 使用axon_quant BacktestEngine + 策略回调
5. **迁移现有策略** — 从StrategyBase/AxonStrategy迁移到UnifiedStrategy
6. **集成测试** — 端到端验证

## [S6] 设计决策

1. **统一到axon风格**: float/str接口，废弃Decimal/InstrumentId
2. **axon_quant exchange作为数据源**: 废弃realtime引擎作为主数据源
3. **axon_quant BacktestEngine作为唯一回测引擎**: 废弃VectorEngine
4. **TradingEngine作为核心单例**: 统一管理策略生命周期
5. **StrategyContext注入交易接口**: 解决NotImplementedError问题
