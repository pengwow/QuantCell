# 核心交易链路打通 — 设计文档

**日期**: 2026-07-25
**状态**: 待实施
**范围**: 后端（不做前端 mock 替换）

## 背景

QuantCell 的核心交易链路存在 7 个关键断点，导致策略无法通过 API 真正启动、实盘下单跳过风控、Action→订单转换与回测不一致。本次目标是串联已有模块（TradingEngine/StrategyLoop/BacktestLoop/RiskEngine/WebSocket/Deployer），形成最小可用的策略运行闭环。

**用户确认的调整**:
1. 回测 API 入口统一放在 `/api/engine/backtest`，不属于 strategy routes
2. 策略运行独立于 Worker 系统（Worker 用于分布式/多进程扩展，单机直接用 StrategyLoop）
3. 本次只做后端，前端 mock 替换放到后续任务

---

## 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                     REST API Layer                            │
│  engine/routes.py (新增)  │  backtest/routes.py (已有)       │
│  strategy/routes.py (已有)│  websocket/routes.py (已有)      │
└──────────────┬───────────────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────────────┐
│  TradingEngine (模块级单例, lifespan 初始化)                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ register_strategy / start_strategy / stop_strategy     │  │
│  │ run_backtest / list_strategies / get_strategy_status   │  │
│  │ _risk_check_order() (供 StrategyLoop 调用)             │  │
│  └─────┬──────────────────────────────┬──────────────────┘  │
│        │                              │                      │
│  ┌─────▼─────┐                ┌──────▼──────┐               │
│  │RiskEngine │◄───风控检查────│StrategyLoop │               │
│  │(已存在)   │  下单前必过     │(修复+增强)   │               │
│  └───────────┘                └──────┬──────┘               │
│                                      │ place_order           │
│                              ┌───────▼────────┐              │
│                              │Exchange Adapter│              │
│                              │(Binance/OKX)   │              │
│                              └────────────────┘              │
└──────────────────────────────────────────────────────────────┘
               │
               │ WebSocket 广播事件
               ▼
┌──────────────────────────────────────────────────────────────┐
│  WebSocket Manager (已有)                                     │
│  strategy.started / strategy.stopped / order.placed          │
│  order.rejected / bar.processed / pnl.updated                │
└──────────────────────────────────────────────────────────────┘
```

**设计原则**:
- 不重写已有模块，只做串联和修复
- TradingEngine 是唯一调度中心，统管回测和实盘
- 实盘下单强制经过风控，违反则拒绝并记录
- 策略状态通过已有 WebSocket 推送
- Deployer 干跑模式保留，实盘模式委托给 TradingEngine
- Worker 系统不强制整合，保留为后续分布式扩展

---

## 改动清单

### 1. engine/trading_engine.py — 修复与增强

**改动**:

1.1 添加模块级单例 `get_trading_engine()`:
```python
@lru_cache(maxsize=1)
def get_trading_engine(config: EngineConfig | None = None) -> TradingEngine:
    """获取 TradingEngine 单例。首次调用时传入 config，后续忽略。"""
```

1.2 增强 `StrategyRuntime`（engine/strategy_runtime.py），新增字段:
- `started_at: float` — 启动时间戳
- `order_count: int` — 订单计数
- `fill_count: int` — 成交计数
- `rejected_count: int` — 风控拒绝计数
- `last_action: str | None` — 最后动作类型
- `last_price: float` — 最后价格
- `realized_pnl: float` — 已实现 PnL

1.3 新增 `get_strategy_status(sid) -> dict`:
- 返回运行时长、订单数、成交数、拒绝数、最后动作、PnL 等

1.4 修复 `start_strategy()`:
- 注入 risk_engine 到 StrategyLoop
- 注入 account_equity 提供者（从 adapter 查询余额，默认用 initial_cash）
- 启动成功后广播 WebSocket `strategy.started` 事件

1.5 StrategyLoop 通过 RiskService 单例（`services.risk_service.get_risk_service()`）在下单前做风控检查，TradingEngine 在创建 StrategyLoop 时注入该引用。

1.6 修复 `stop_strategy()`:
- 停止后广播 `strategy.stopped` 事件
- 更新 runtime 状态

1.7 `run_backtest()` 保持不变（已正确委托给 BacktestLoop）。

### 2. engine/routes.py — 新增（引擎管理 API）

**新增文件**，统一暴露引擎能力:

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/engine/status` | 引擎状态（交易所连接、风控状态、运行策略数） |
| GET | `/api/engine/strategies` | 列出所有策略（含状态） |
| POST | `/api/engine/strategies/start` | 启动策略 |
| POST | `/api/engine/strategies/{sid}/stop` | 停止策略 |
| GET | `/api/engine/strategies/{sid}/status` | 策略详情（PnL/订单/最后 bar） |
| POST | `/api/engine/backtest` | 运行回测 |

**请求/响应**:

```jsonc
// POST /api/engine/strategies/start
{
  "strategy_name": "dual_ma",     // 必须，已注册的策略名
  "symbols": ["BTCUSDT"],         // 必须，交易对列表
  "account": "binance_paper",     // 可选，凭证名（paper 模式可省）
  "mode": "paper",                // paper | live，默认 paper
  "params": {"fast": 10, "slow": 30},  // 可选，策略参数
  "initial_cash": 100000.0        // 可选，初始资金
}
// Response
{"code": 0, "data": {"strategy_id": "a1b2c3d4", "status": "running"}}
```

```jsonc
// POST /api/engine/backtest
{
  "strategy_name": "dual_ma",
  "symbol": "BTCUSDT",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31",
  "params": {"fast": 10, "slow": 30},
  "initial_cash": 100000.0,
  "frequency": "1h"              // K线频率
}
// Response: BacktestResult（与现有 backtest 结果格式一致）
```

### 3. strategy/loop.py — 关键修复

**改动**:

3.1 **构造函数注入 risk_engine 和 portfolio 状态**:
```python
def __init__(self, adapter, strategy, symbol, interval=1.0,
             risk_engine=None, account_equity=100_000.0,
             event_callback=None):
```

3.2 **风控检查**（`_execute_action` 开头）:
```python
# 置信度过滤
if action.confidence < 0.3:
    return
# 构造 order dict（先构造再检查）
ratio = float(action.target_position or 0.0)
if str(action.action_type) == "sell":
    ratio = -ratio
qty = abs(ratio) * self._account_equity / current_price

order_dict = {
    "symbol": self._symbol,
    "side": side,
    "type": "market",
    "quantity": qty,
    "price": current_price,
}
# 风控检查（若注入了 risk_engine）
if self._risk_engine is not None:
    portfolio_state = {"cash": {"USD": self._account_equity}}
    check = self._risk_engine.check_order(order_dict, portfolio_state)
    if not check.get("passed"):
        self._rejected_count += 1
        reason = check.get("reason", "unknown")
        if self._event_callback:
            self._event_callback("order.rejected", {"reason": reason, "order": order_dict})
        logger.warning(f"风控拒绝订单: {reason}")
        return
```

3.3 **修复 target_position → qty 转换**:
- `target_position` 是仓位比例（0.0~1.0），与 BacktestLoop 保持一致
- qty = ratio * account_equity / current_price
- 不再把 target_position 当作绝对数量

3.4 **事件回调**:
- 订单执行成功后调用 `event_callback("order.placed", {...})`
- 每根 bar 处理后调用 `event_callback("bar.processed", {...})`
- 回调由 TradingEngine 注入，用于广播 WebSocket 和更新 runtime 状态

3.5 **on_fill 回调**:
- 成交后调用 `self._strategy.on_fill(fill)` 更新策略内部状态

### 4. engine/deployer.py — 实盘接入

**改动**:

4.1 移除 `NotImplementedError`，实盘模式委托给 TradingEngine 单例:
```python
if not self.dry_run:
    engine = get_trading_engine()
    sid = engine.start_strategy(strategy, [symbol], account=account_name)
    handle.engine_strategy_id = sid
```

4.2 WorkerHandle 增加字段:
- `engine_strategy_id: str | None` — 对应 TradingEngine 中的 sid
- `mode: str` — paper/live
- `started_at: float` — 启动时间

4.3 `stop()` 委托给 TradingEngine.stop_strategy()。

4.4 `list_active()` 与 TradingEngine.list_strategies() 状态同步。

4.5 干跑模式保留：验证凭证存在 + 策略可加载 + 返回 handle，但不启动 loop。

### 5. main.py — lifespan 初始化 + 路由注册

**改动**:

5.1 在现有 lifespan 中添加 TradingEngine 初始化（paper 模式默认配置）。

5.2 注册 engine router:
```python
from engine.routes import router as engine_router
app.include_router(engine_router)
```

5.3 确保 `/health` 端点包含引擎状态摘要。

### 6. engine/strategy_runtime.py — 增强

查看现有文件，补充 1.2 中列出的新字段和更新方法。

### 7. WebSocket 事件集成

**改动**（最小化，复用已有设施）:

7.1 在 `engine/trading_engine.py` 中引入已有的 websocket manager:
```python
from websocket.manager import manager as ws_manager
```

7.2 在策略启动/停止/订单执行/拒绝时调用 `ws_manager.broadcast()` 发送 JSON 事件。

7.3 事件格式:
```json
{
  "type": "order.placed",
  "strategy_id": "a1b2c3d4",
  "data": {
    "symbol": "BTCUSDT",
    "side": "buy",
    "quantity": 0.01,
    "price": 65000.0,
    "timestamp": 1234567890
  }
}
```

7.4 不新增 WebSocket 端点，复用现有的 `/api/ws/*` 通道。

---

## 不做的事（明确 scope out）

1. **前端 mock 替换** — 本次只做后端 API，前端对接后续任务
2. **Worker 系统深度整合** — 策略独立运行，不强制注册为 Worker；Worker 系统保留用于未来分布式扩展
3. **OKX/Bybit 行情 API 实现** — market_data_factory 中的 TODO 不在本次范围
4. **axon_worker_system placeholder 替换** — 该模块是 Worker 级别策略分发，与独立策略运行解耦，后续单独处理
5. **HPO/walk_forward 实现** — 属于超参优化模块，不在核心交易链路范围
6. **限价单/高级订单类型** — 本次先用市价单，后续扩展
7. **账户净值实时更新** — 初版用 initial_cash 或从 adapter.get_balance() 启动时获取，不做逐 bar 更新

---

## 文件改动汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `engine/trading_engine.py` | 修改 | 单例、风控集成、状态追踪、事件广播 |
| `engine/strategy_runtime.py` | 修改 | 补充运行时状态字段 |
| `engine/routes.py` | **新增** | 引擎管理 REST API |
| `strategy/loop.py` | 修改 | 风控检查、qty 修正、事件回调、on_fill |
| `engine/deployer.py` | 修改 | 实盘模式接入 TradingEngine |
| `main.py` | 修改 | lifespan 初始化引擎 + 注册路由 |
| `tests/unit/engine/` | 新增测试 | TradingEngine 单例、StrategyLoop 风控、deployer 实盘 |

---

## 测试策略

1. **单元测试**:
   - `test_trading_engine_singleton` — 验证单例模式
   - `test_start_stop_strategy` — 策略启动/停止生命周期
   - `test_risk_check_rejects_oversized_order` — StrategyLoop 风控拦截
   - `test_target_position_conversion` — Action→order qty 转换正确性（与 BacktestLoop 一致）
   - `test_deployer_dry_run` — 干跑模式验证
   - `test_deployer_live_mode` — 实盘模式委托给 TradingEngine

2. **集成测试**（标记为 integration，需要 adapter）:
   - Mock exchange adapter 下策略完整生命周期
   - WebSocket 事件广播验证

3. **验证方式**:
   - `pytest tests/unit/engine/ tests/unit/services/ tests/unit/strategy/ -v`
   - 手动通过 curl 调用 `/api/engine/status` 和 `/api/engine/strategies/start`（paper 模式）验证
