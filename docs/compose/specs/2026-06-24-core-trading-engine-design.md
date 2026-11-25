# QuantCell 核心交易引擎重构设计

> 日期: 2026-06-24
> 状态: 已批准

## [S1] 架构总览

5层架构：API → TradingEngine → StrategyLoop/BacktestLoop/RLInference → Rust 核心

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
│                      Rust 核心引擎                       │
│  exchange.adapter  backtest.engine  risk.engine           │
│  llm.agent         inference.engine  rl.env              │
└──────────────────────────────────────────────────────────┘
```

## [S2] 统一策略接口

废弃旧策略基类（Decimal/InstrumentId 口径）与旧强类型策略实现，统一为 float/str 口径。

```python
class UnifiedStrategy(ABC):
    """统一策略基类 — float/str 口径"""
    
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
| 旧强类型策略实现 | 废弃 | 被UnifiedStrategy替代 |
| 旧策略循环实现 | 重写 | 修复adapter注入、错误处理、数据源 |
| 旧 Worker 实现 | 重构 | 使用TradingEngine统一管理 |
| 旧回测引擎实现 | 增强 | 支持策略回调 |
| 旧向量化回测引擎 | 删除 | 被统一内核替代 |
| `exchange/base.py` | 增强 | 添加subscribe()方法 |
| `realtime/` | 保留但不再主用 | 数据源切换到内核 exchange 适配器 |

## [S5] 实施顺序

1. **UnifiedStrategy** — 定义统一接口 + StrategyContext
2. **TradingEngine** — 核心引擎，连接exchange/risk/backtest
3. **StrategyLoop重构** — 使用内核 exchange adapter
4. **BacktestLoop** — 使用内核 BacktestEngine + 策略回调
5. **迁移现有策略** — 从旧策略基类迁移到UnifiedStrategy
6. **集成测试** — 端到端验证

## [S6] 设计决策

1. **统一口径**: float/str接口，废弃Decimal/InstrumentId
2. **内核 exchange 作为数据源**: 废弃realtime引擎作为主数据源
3. **内核 BacktestEngine 作为唯一回测引擎**: 废弃VectorEngine
4. **TradingEngine作为核心单例**: 统一管理策略生命周期
5. **StrategyContext注入交易接口**: 解决NotImplementedError问题
