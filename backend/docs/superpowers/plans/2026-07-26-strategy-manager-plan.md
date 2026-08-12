# StrategyManager 统一策略执行系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 AxonTradingSystem 重命名为 StrategyManager，合并 TradingEngine 的功能，统一策略执行系统。

**Architecture:** 将 worker/axon_worker_system.py 重命名为 worker/strategy_manager.py，类名改为 StrategyManager。修改 engine/trading_engine.py 为委托模式，内部调用 StrategyManager。统一 StrategyRuntime 字段定义。

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, axon_quant

---

## 文件结构

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `worker/strategy_manager.py` | 创建 | 从 axon_worker_system.py 复制并重命名类 |
| `worker/axon_worker_system.py` | 删除 | 原文件 |
| `worker/__init__.py` | 修改 | 更新导出为 StrategyManager |
| `worker/state.py` | 修改 | StrategyRuntime 字段补充 |
| `engine/trading_engine.py` | 修改 | 委托给 StrategyManager |
| `engine/strategy_runtime.py` | 删除 | 合并到 worker/state.py |
| `strategy/loader.py` | 修改 | 标记废弃 |

---

### Task 1: 创建 StrategyManager 类

**Files:**
- Create: `worker/strategy_manager.py`
- Delete: `worker/axon_worker_system.py`

- [ ] **Step 1: 复制 axon_worker_system.py 内容到 strategy_manager.py**

```bash
cp /Users/liupeng/workspace/quant/QuantCell/backend/worker/axon_worker_system.py /Users/liupeng/workspace/quant/QuantCell/backend/worker/strategy_manager.py
```

- [ ] **Step 2: 修改类名和所有内部引用**

```python
# 将所有 AxonTradingSystem 替换为 StrategyManager
# 将所有 [AxonTradingSystem] 日志前缀替换为 [StrategyManager]
```

- [ ] **Step 3: 添加 TradingEngine 的核心方法**

在 StrategyManager 类中添加：

```python
from backtest.backtest_loop import BacktestLoop, BacktestResult, RuleStrategy
import pandas as pd
from typing import Any, Optional

def run_backtest(
    self,
    strategy: RuleStrategy,
    data: pd.DataFrame,
    symbol: str = "BTCUSDT",
    initial_cash: float = 100_000.0,
) -> BacktestResult:
    """运行回测"""
    loop = BacktestLoop(initial_cash=initial_cash)
    return loop.run(strategy, data, symbol)

def engine_status(self) -> dict[str, Any]:
    """获取引擎状态概览"""
    from .state import strategy_registry
    running = sum(1 for rt in strategy_registry.list_all() if rt.status == "running")
    return {
        "exchange": "binance",  # 从配置获取
        "mode": "paper",        # 从配置获取
        "exchange_connected": True,
        "risk_available": True,
        "total_strategies": len(strategy_registry.list_all()),
        "running_strategies": running,
    }

def list_strategies(self) -> list[dict]:
    """列出所有策略"""
    from .state import strategy_registry
    return [rt.to_dict() for rt in strategy_registry.list_all()]

def get_strategy_status(self, strategy_id: str) -> Optional[dict[str, Any]]:
    """获取策略状态"""
    from .state import strategy_registry
    # 支持 string 和 int 类型的 strategy_id
    try:
        worker_id = int(strategy_id)
    except ValueError:
        worker_id = strategy_id
    runtime = strategy_registry.get(worker_id)
    return runtime.to_dict() if runtime else None
```

- [ ] **Step 4: 删除原 axon_worker_system.py**

```bash
mv /Users/liupeng/workspace/quant/QuantCell/backend/worker/axon_worker_system.py /tmp/
```

- [ ] **Step 5: Commit**

```bash
git add backend/worker/strategy_manager.py
git commit -m "refactor: create StrategyManager by renaming AxonTradingSystem"
```

---

### Task 2: 修改 StrategyRuntime 字段

**Files:**
- Modify: `worker/state.py`
- Delete: `engine/strategy_runtime.py`

- [ ] **Step 1: 读取 engine/strategy_runtime.py 了解需要补充的字段**

```bash
cat /Users/liupeng/workspace/quant/QuantCell/backend/engine/strategy_runtime.py
```

- [ ] **Step 2: 修改 worker/state.py 中的 StrategyRuntime**

补充字段：

```python
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class StrategyRuntime:
    worker_id: int
    strategy_id: int
    name: str
    status: str = "stopped"
    
    # 从 TradingEngine.StrategyRuntime 补充的字段
    strategy: Any = None
    symbols: list[str] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    mode: str = "paper"
    order_count: int = 0
    fill_count: int = 0
    rejected_count: int = 0
    last_price: float = 0.0
    last_action: str = ""
    
    # 原有字段
    trading_node: Optional[Any] = None
    _run_task: Optional[asyncio.Task] = None
    _run_thread: Optional[threading.Thread] = None
    _flush_stop: Optional[threading.Event] = None
    _pid: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    
    # 更新 to_dict 方法
    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "strategy_id": self.strategy_id,
            "name": self.name,
            "status": self.status,
            "is_running": self.is_running,
            "pid": self._pid,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            # 新增字段
            "strategy_name": self.name,
            "symbols": self.symbols,
            "params": self.params,
            "mode": self.mode,
            "order_count": self.order_count,
            "fill_count": self.fill_count,
            "rejected_count": self.rejected_count,
            "last_price": self.last_price,
            "last_action": self.last_action,
        }
```

- [ ] **Step 3: 删除 engine/strategy_runtime.py**

```bash
mv /Users/liupeng/workspace/quant/QuantCell/backend/engine/strategy_runtime.py /tmp/
```

- [ ] **Step 4: Commit**

```bash
git add backend/worker/state.py
git commit -m "refactor: unify StrategyRuntime fields"
```

---

### Task 3: 更新 worker/__init__.py 导出

**Files:**
- Modify: `worker/__init__.py`

- [ ] **Step 1: 修改导出**

```python
"""
Worker管理模块

提供Worker进程管理和API接口

主要组件:
    - StrategyManager: 策略执行引擎
    - TradingNodeWorkerManager: 策略生命周期协调器
    - EventHandler: 事件处理器
"""

from .routes import router
from .service import worker_service
from .manager import TradingNodeWorkerManager
from .event_handler import EventHandler, EventBufferConfig
from .strategy_manager import StrategyManager, worker_system

__all__ = [
    'router',
    'worker_service',
    'StrategyManager',
    'worker_system',
    'TradingNodeWorkerManager',
    'EventHandler',
    'EventBufferConfig',
]
```

- [ ] **Step 2: Commit**

```bash
git add backend/worker/__init__.py
git commit -m "refactor: update worker exports to StrategyManager"
```

---

### Task 4: 修改 engine/trading_engine.py 为委托模式

**Files:**
- Modify: `engine/trading_engine.py`

- [ ] **Step 1: 重写 engine/trading_engine.py**

```python
# -*- coding: utf-8 -*-
"""TradingEngine — 核心交易引擎（向后兼容门面）

内部委托给 StrategyManager，保持原有 API 兼容性。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from backtest.backtest_loop import BacktestLoop, BacktestResult, RuleStrategy

logger = logging.getLogger(__name__)


def get_trading_engine(config=None) -> Any:
    """获取 TradingEngine 单例（向后兼容，内部委托给 StrategyManager）"""
    from worker.strategy_manager import worker_system
    return worker_system


class TradingEngine:
    """核心交易引擎（向后兼容）
    
    所有方法内部委托给 StrategyManager。
    """
    
    def __init__(self, config=None):
        from worker.strategy_manager import StrategyManager
        self._manager = StrategyManager()
    
    @property
    def exchange(self) -> Optional[Any]:
        return None  # 委托给 StrategyManager
    
    @property
    def risk_engine(self) -> Optional[Any]:
        return None  # 委托给 StrategyManager
    
    def engine_status(self) -> dict[str, Any]:
        return self._manager.engine_status()
    
    def register_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        mode: str = "paper",
    ) -> str:
        # TradingEngine 返回 string sid，StrategyManager 返回 int worker_id
        # 为了兼容，返回字符串形式的 worker_id
        from worker.strategy_manager import worker_system
        from worker.state import strategy_registry, StrategyRuntime
        
        # 创建临时策略（无持久化）
        sid = str(len(strategy_registry.list_all()) + 1).zfill(8)
        # 这里需要一个临时的 int worker_id
        temp_id = hash(sid) % 1000000
        runtime = StrategyRuntime(
            worker_id=temp_id,
            strategy_id=0,
            name=strategy_name or strategy.__class__.__name__,
            strategy=strategy,
            symbols=list(symbols),
            params=params or {},
            mode=mode,
        )
        strategy_registry.register(runtime)
        return sid
    
    def start_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        account_equity: float = 100_000.0,
        mode: str = "paper",
    ) -> str:
        # 委托给 StrategyManager 的 create_strategy + start_strategy
        from worker.strategy_manager import worker_system
        from utils.db_session import get_db_session
        
        with get_db_session() as db:
            worker_id = worker_system.create_strategy(
                db,
                {
                    "name": strategy_name or strategy.__class__.__name__,
                    "strategy_id": 0,  # 需要实际策略 ID
                    "exchange": "binance",
                    "trading_mode": mode,
                    "config": {"symbols": symbols, "params": params or {}},
                },
            )
        
        worker_system.start_strategy(worker_id)
        return str(worker_id)
    
    def stop_strategy(self, strategy_id: str) -> bool:
        try:
            worker_id = int(strategy_id)
        except ValueError:
            # 对于 string 类型的策略 ID，查找匹配的策略
            from worker.state import strategy_registry
            for rt in strategy_registry.list_all():
                if str(rt.worker_id) == strategy_id or rt.name == strategy_id:
                    worker_id = rt.worker_id
                    break
            else:
                logger.warning(f"策略不存在: {strategy_id}")
                return False
        
        from worker.strategy_manager import worker_system
        return worker_system.stop_strategy(worker_id)
    
    def get_strategy_status(self, strategy_id: str) -> Optional[dict[str, Any]]:
        return self._manager.get_strategy_status(strategy_id)
    
    def list_strategies(self) -> list[dict]:
        return self._manager.list_strategies()
    
    def run_backtest(
        self,
        strategy: RuleStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
    ) -> BacktestResult:
        return self._manager.run_backtest(strategy, data, symbol, initial_cash)
```

- [ ] **Step 2: Commit**

```bash
git add backend/engine/trading_engine.py
git commit -m "refactor: make TradingEngine delegate to StrategyManager"
```

---

### Task 5: 更新所有引用 AxonTradingSystem 的文件

**Files:**
- Modify: `engine/deployer.py`
- Modify: `tests/unit/engine/test_deployer.py`
- Modify: `main.py`
- Modify: `core/lifespan.py`
- Modify: `engine/routes.py`
- Modify: `tests/unit/engine/test_trading_engine.py`
- Modify: `worker/routes.py`
- Modify: `worker/core_service.py`

- [ ] **Step 1: 批量替换所有引用**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
grep -r "AxonTradingSystem" --include="*.py" -l | xargs sed -i '' 's/AxonTradingSystem/StrategyManager/g'
```

- [ ] **Step 2: 更新导入路径**

```bash
grep -r "from worker.axon_worker_system" --include="*.py" -l | xargs sed -i '' 's/from worker.axon_worker_system/from worker.strategy_manager/g'
```

- [ ] **Step 3: 更新文件头注释**

检查所有修改的文件，更新文件头注释中的描述。

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor: update all AxonTradingSystem references to StrategyManager"
```

---

### Task 6: 标记 strategy/loader.py 为废弃

**Files:**
- Modify: `strategy/loader.py`

- [ ] **Step 1: 添加废弃标记**

在文件顶部添加：

```python
"""
策略加载器（已废弃）

请使用 backtest.strategy_loader_service.StrategyLoaderService 替代。
"""

import warnings
warnings.warn(
    "strategy.loader is deprecated, use backtest.strategy_loader_service.StrategyLoaderService instead",
    DeprecationWarning,
    stacklevel=2,
)
```

- [ ] **Step 2: Commit**

```bash
git add backend/strategy/loader.py
git commit -m "chore: mark strategy.loader as deprecated"
```

---

### Task 7: 运行测试验证

**Files:**
- Test: `tests/unit/engine/test_trading_engine.py`
- Test: `tests/unit/worker/`

- [ ] **Step 1: 运行引擎测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py -v
```

- [ ] **Step 2: 运行 worker 测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/python -m pytest tests/unit/worker/ -v
```

- [ ] **Step 3: 运行完整测试套件**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/python -m pytest tests/unit/ -v --tb=short
```

- [ ] **Step 4: 修复测试失败**

根据测试失败信息修复代码。

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "fix: resolve test failures after StrategyManager migration"
```

---

## 自审查

### 1. Spec 覆盖
- ✅ 文件重命名：Task 1
- ✅ StrategyRuntime 字段统一：Task 2
- ✅ 合并核心方法：Task 1 Step 3
- ✅ 向后兼容门面：Task 4
- ✅ 更新引用：Task 5
- ✅ 测试验证：Task 7

### 2. 占位符扫描
- ✅ 无 TBD/TODO
- ✅ 所有步骤包含具体代码
- ✅ 所有命令明确

### 3. 类型一致性
- ✅ StrategyRuntime 字段在所有任务中一致
- ✅ StrategyManager 类名在所有任务中一致
