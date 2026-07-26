# StrategyManager 统一策略执行系统设计文档

## 1. 概述

### 1.1 背景

QuantCell 项目中存在两套策略执行系统，职责严重重叠：

| 系统 | 位置 | 特点 |
|------|------|------|
| TradingEngine | `engine/trading_engine.py` | 内存级别策略管理，无持久化 |
| AxonTradingSystem | `worker/axon_worker_system.py` | 数据库持久化策略管理，支持重启恢复 |

### 1.2 目标

- 将 `AxonTradingSystem` 重命名为 `StrategyManager`
- 合并 `TradingEngine` 的核心功能到 `StrategyManager`
- 统一策略运行时状态定义
- 保持向后兼容性，现有 API 端点不变

### 1.3 范围

- **包含**：策略生命周期管理（注册/启动/停止/删除）、回测执行、交易所 Adapter、WebSocket 事件推送
- **不包含**：策略加载器重构（本次仅统一使用 StrategyLoaderService）、前端对接

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    StrategyManager (单例)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  内存层: StrategyRegistry (worker/state.py)         │   │
│  │    └── StrategyRuntime (统一字段定义)                │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  持久化层: worker/crud.py ↔ SQLite                  │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  策略执行: StrategyLoop (strategy/loop.py)          │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  交易所: ExchangeAdapter (axon_bridge.exchange)     │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────────┬──────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      /api/engine/*      /api/worker/*      deployer.py
   (engine/routes.py)  (worker/routes.py)  (engine/deployer.py)
```

### 2.2 核心组件

| 组件 | 职责 | 位置 |
|------|------|------|
| StrategyManager | 统一策略执行引擎，管理策略生命周期 | `worker/strategy_manager.py` |
| StrategyRegistry | 内存策略注册表，提供 CRUD 和状态变更回调 | `worker/state.py` |
| StrategyRuntime | 策略运行时状态对象 | `worker/state.py` |
| StrategyLoop | 策略执行循环（实盘） | `strategy/loop.py` |
| BacktestLoop | 回测执行循环 | `backtest/backtest_loop.py` |
| StrategyLoaderService | 策略加载器 | `backtest/strategy_loader_service.py` |

---

## 3. 关键设计

### 3.1 StrategyManager 类设计

```python
class StrategyManager:
    """统一策略执行引擎（单例）"""
    
    def __init__(self, max_workers: Optional[int] = None):
        self._executor: ThreadPoolExecutor  # 回测线程池
        self._strategy_loops: Dict[int, StrategyLoop]  # 运行中的策略循环
    
    async def initialize(self) -> None:
        """初始化系统，从数据库恢复策略状态"""
    
    async def create_strategy(self, db, config: Dict[str, Any]) -> int:
        """创建策略（持久化到数据库）"""
    
    async def start_strategy(self, worker_id: int) -> bool:
        """启动策略（支持实盘/模拟）"""
    
    async def stop_strategy(self, worker_id: int) -> bool:
        """停止策略"""
    
    async def delete_strategy(self, worker_id: int) -> bool:
        """删除策略"""
    
    async def register_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        mode: str = "paper",
    ) -> str:
        """注册策略（内存级别，无持久化）"""
    
    def get_strategy_status(self, strategy_id: str) -> Optional[dict]:
        """获取策略状态"""
    
    def list_strategies(self) -> list[dict]:
        """列出所有策略"""
    
    def run_backtest(
        self,
        strategy: RuleStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
    ) -> BacktestResult:
        """运行回测"""
    
    def engine_status(self) -> dict[str, Any]:
        """获取引擎状态概览"""
```

### 3.2 StrategyRuntime 字段统一

以 `worker/state.py` 中的定义为基准，补充 `TradingEngine` 需要的字段：

```python
@dataclass
class StrategyRuntime:
    worker_id: int
    strategy_id: int
    name: str
    status: str = "stopped"
    
    # 从 TradingEngine.StrategyRuntime 补充
    strategy: Any = None
    symbols: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    mode: str = "paper"
    order_count: int = 0
    fill_count: int = 0
    rejected_count: int = 0
    last_price: float = 0.0
    last_action: str = ""
    
    # 原有的运行时字段
    trading_node: Optional[Any] = None
    _run_task: Optional[asyncio.Task] = None
    _run_thread: Optional[threading.Thread] = None
    _flush_stop: Optional[threading.Event] = None
    _pid: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
```

### 3.3 向后兼容设计

保留 `engine/trading_engine.py`，将其实现改为委托给 `StrategyManager`：

```python
# engine/trading_engine.py (简化版)

def get_trading_engine(config=None):
    """获取 TradingEngine 单例（向后兼容，内部委托给 StrategyManager）"""
    from worker.strategy_manager import StrategyManager
    return StrategyManager.instance()

# 保留原有方法签名，确保 API 兼容性
class TradingEngine:
    # 所有方法内部委托给 StrategyManager
```

---

## 4. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `worker/axon_worker_system.py` | 重命名 | → `worker/strategy_manager.py` |
| `worker/__init__.py` | 修改 | 导出名变更为 `StrategyManager` |
| `worker/state.py` | 修改 | StrategyRuntime 字段补充 |
| `engine/trading_engine.py` | 修改 | 委托给 StrategyManager |
| `engine/strategy_runtime.py` | 删除 | 合并到 worker/state.py |
| `strategy/loader.py` | 标记废弃 | 统一用 StrategyLoaderService |

---

## 5. API 兼容性

所有现有 API 端点保持不变：

| 端点 | 路径 | 变更 |
|------|------|------|
| 引擎状态 | `/api/engine/status` | 无 |
| 策略列表 | `/api/engine/strategies` | 无 |
| 启动策略 | `/api/engine/strategies/start` | 无 |
| 停止策略 | `/api/engine/strategies/{sid}/stop` | 无 |
| 策略状态 | `/api/engine/strategies/{sid}/status` | 无 |
| 回测 | `/api/engine/backtest` | 无 |
| Worker 管理 | `/api/worker/*` | 无 |

---

## 6. 测试策略

- 单元测试：验证 `StrategyManager` 的核心方法
- 集成测试：验证 API 端点的向后兼容性
- 回归测试：确保现有功能不受影响

---

## 7. 实施步骤

1. 创建 `worker/strategy_manager.py`，复制 `AxonTradingSystem` 代码并重命名类
2. 修改 `worker/state.py`，补充 StrategyRuntime 字段
3. 修改 `worker/__init__.py`，更新导出
4. 修改 `engine/trading_engine.py`，改为委托模式
5. 删除 `engine/strategy_runtime.py`
6. 标记 `strategy/loader.py` 为废弃
7. 更新所有引用 `AxonTradingSystem` 的文件
8. 运行测试验证
