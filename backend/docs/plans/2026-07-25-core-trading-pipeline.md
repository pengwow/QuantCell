# Core Trading Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通 QuantCell 核心交易链路，使策略能通过 REST API 启动/停止/回测，实盘下单强制经过风控，策略状态通过 WebSocket 实时推送。

**Architecture:** TradingEngine 作为单例调度中心，统管回测（BacktestLoop）和实盘（StrategyLoop）；StrategyLoop 修复 qty 计算并接入 RiskService 单例；新增 engine/routes.py 暴露 REST API；复用已有 WebSocket manager 通过 topic="strategy" 广播事件；Deployer 实盘模式委托给 TradingEngine。

**Tech Stack:** Python 3.14, FastAPI, lru_cache 单例, axon_quant (通过 axon_bridge), 已有 WebSocket ConnectionManager, 已有 RiskService 单例。

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `engine/strategy_runtime.py` | 修改 | 补充运行时状态字段（started_at, order_count 等） |
| `strategy/loop.py` | 修改 | 风控检查、qty 修正、事件回调注入 |
| `engine/trading_engine.py` | 修改 | 单例模式、状态追踪、WebSocket 事件广播、start_strategy 增强 |
| `engine/routes.py` | 新增 | 引擎状态/策略启动停止/回测 REST API |
| `engine/deployer.py` | 修改 | 实盘模式接入 TradingEngine 单例 |
| `main.py` | 修改 | lifespan 初始化 TradingEngine + 注册 engine router |
| `tests/unit/engine/test_trading_engine.py` | 新增 | TradingEngine 单例和生命周期测试 |
| `tests/unit/engine/test_loop_risk.py` | 新增 | StrategyLoop 风控和 qty 测试 |
| `tests/unit/engine/test_deployer.py` | 新增 | Deployer 实盘/干跑测试 |

---

### Task 1: 增强 StrategyRuntime 数据类

**Files:**
- Modify: `backend/engine/strategy_runtime.py`

- [ ] **Step 1: 读取现有文件确认结构**

已读取，当前文件只有 5 个字段（strategy_id, strategy, symbols, status, loop）。

- [ ] **Step 2: 替换 StrategyRuntime 为增强版本**

将 `backend/engine/strategy_runtime.py` 全部替换为：

```python
# -*- coding: utf-8 -*-
"""StrategyRuntime — 策略运行时数据类"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StrategyRuntime:
    """策略运行时数据类

    Attributes:
        strategy_id: 策略 ID
        strategy: 策略实例（实现 on_bar → Action）
        symbols: 交易对列表
        status: 策略状态 (stopped/running/paused/error)
        loop: StrategyLoop 实例（实盘时使用）
        started_at: 启动时间戳（time.monotonic()）
        order_count: 已下订单数
        fill_count: 成交数
        rejected_count: 风控拒绝数
        last_action: 最后动作类型（buy/sell/hold）
        last_price: 最后处理价格
        realized_pnl: 已实现 PnL（初版固定 0.0）
        mode: 运行模式（paper/live/backtest）
        strategy_name: 策略模板名
        params: 策略参数字典
    """
    strategy_id: str
    strategy: Any
    symbols: list[str]
    status: str = "stopped"
    loop: Optional[Any] = None
    started_at: float = 0.0
    order_count: int = 0
    fill_count: int = 0
    rejected_count: int = 0
    last_action: Optional[str] = None
    last_price: float = 0.0
    realized_pnl: float = 0.0
    mode: str = "paper"
    strategy_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 API 响应字典"""
        duration = time.monotonic() - self.started_at if self.started_at > 0 else 0
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbols": self.symbols,
            "status": self.status,
            "mode": self.mode,
            "started_at": self.started_at,
            "duration_secs": round(duration, 1),
            "order_count": self.order_count,
            "fill_count": self.fill_count,
            "rejected_count": self.rejected_count,
            "last_action": self.last_action,
            "last_price": self.last_price,
            "realized_pnl": self.realized_pnl,
        }
```

- [ ] **Step 3: 验证导入不报错**

Run: `cd backend && .venv/bin/python -c "from engine.strategy_runtime import StrategyRuntime; r = StrategyRuntime(strategy_id='test', strategy=None, symbols=['BTCUSDT'], strategy_name='test'); print(r.to_dict())"`
Expected: 输出包含 strategy_id, status='stopped', order_count=0 等字段的 dict。

- [ ] **Step 4: Commit**

```bash
git add backend/engine/strategy_runtime.py
git commit -m "feat(engine): enhance StrategyRuntime with runtime tracking fields"
```

---

### Task 2: 修复 StrategyLoop（风控 + qty 修正 + 事件回调）

**Files:**
- Modify: `backend/strategy/loop.py`

- [ ] **Step 1: 先写失败测试**

创建 `backend/tests/unit/engine/test_loop_risk.py`：

```python
# -*- coding: utf-8 -*-
"""StrategyLoop 风控和 qty 转换测试"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from strategy.loop import StrategyLoop


@dataclass
class FakeAction:
    action_type: str
    confidence: float
    target_position: float


class FakeStrategy:
    """测试用策略：返回固定 Action"""
    def __init__(self, action):
        self._action = action
        self.started = False
        self.stopped = False
        self.fills = []

    def on_start(self):
        self.started = True

    def on_stop(self):
        self.stopped = True

    def on_bar(self, bar, ctx=None):
        return self._action

    def on_fill(self, fill, ctx=None):
        self.fills.append(fill)


class FakeAdapter:
    """测试用交易所适配器"""
    def __init__(self):
        self.connected = False
        self.subscribed = []
        self.orders = []
        self.disconnected = False
        self._ticker = {"open": 65000, "high": 65100, "low": 64900, "last": 65050, "volume": 100.0}

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.disconnected = True

    def subscribe(self, symbols):
        self.subscribed = list(symbols)

    def get_ticker(self, symbol):
        return self._ticker

    def place_order(self, order_dict):
        self.orders.append(order_dict)
        return {"order_id": "test_123", "status": "accepted"}


class FakeRiskEngine:
    """测试用风控引擎：通过 check_passed 控制结果"""
    def __init__(self, check_passed: bool = True, reason: str | None = None):
        self.check_passed = check_passed
        self.reason = reason
        self.checked_orders = []

    def check_order(self, order, portfolio):
        self.checked_orders.append(order)
        return {"passed": self.check_passed, "reason": self.reason}


def test_qty_conversion_target_position_is_ratio():
    """target_position=0.1 应转换为 qty=0.1*100000/65050 ≈ 0.1537"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.8, target_position=0.1))
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,  # 大间隔，手动控制
        risk_engine=FakeRiskEngine(check_passed=True),
        account_equity=100_000.0,
    )

    loop.strategy.on_start()
    bar = {"open": 65000, "high": 65100, "low": 64900, "close": 65050, "volume": 100, "symbol": "BTCUSDT"}
    action = strategy.on_bar(bar)
    # 直接调用 _execute_action 测试 qty 转换
    loop._execute_action(action, 65050.0)

    assert len(adapter.orders) == 1
    order = adapter.orders[0]
    # qty = ratio * equity / price = 0.1 * 100000 / 65050 ≈ 0.1537
    assert abs(order["quantity"] - (0.1 * 100_000 / 65050)) < 1e-6
    assert order["side"] == "Buy"
    assert order["symbol"] == "BTCUSDT"


def test_risk_engine_rejects_order():
    """风控拒绝时不下单"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.8, target_position=0.5))
    risk = FakeRiskEngine(check_passed=False, reason="position_limit_exceeded")
    rejected_events = []
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=risk,
        account_equity=100_000.0,
        event_callback=lambda evt_type, data: rejected_events.append((evt_type, data)) if evt_type == "order.rejected" else None,
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65000.0)

    assert len(adapter.orders) == 0, "风控拒绝的订单不应被下到交易所"
    assert len(risk.checked_orders) == 1
    assert len(rejected_events) == 1
    assert rejected_events[0][1]["reason"] == "position_limit_exceeded"


def test_low_confidence_filtered():
    """置信度 < 0.3 的信号不下单"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.2, target_position=0.1))
    risk = FakeRiskEngine(check_passed=True)
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=risk,
        account_equity=100_000.0,
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65000.0)

    assert len(adapter.orders) == 0, "低置信度信号应被过滤"
    assert len(risk.checked_orders) == 0, "低置信度信号不应进入风控检查"


def test_no_risk_engine_still_places_order():
    """未注入风控引擎时直接下单（兼容模式）"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("sell", confidence=0.9, target_position=0.05))
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=None,
        account_equity=100_000.0,
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65000.0)

    assert len(adapter.orders) == 1
    assert adapter.orders[0]["side"] == "Sell"


def test_event_callback_on_order_placed():
    """订单成功后触发 order.placed 回调"""
    adapter = FakeAdapter()
    strategy = FakeStrategy(FakeAction("buy", confidence=0.8, target_position=0.1))
    events = []
    loop = StrategyLoop(
        adapter=adapter,
        strategy=strategy,
        symbol="BTCUSDT",
        interval=100.0,
        risk_engine=FakeRiskEngine(check_passed=True),
        account_equity=100_000.0,
        event_callback=lambda evt_type, data: events.append((evt_type, data)),
    )

    action = strategy.on_bar({})
    loop._execute_action(action, 65050.0)

    placed = [e for e in events if e[0] == "order.placed"]
    assert len(placed) == 1
    assert placed[0][1]["side"] == "Buy"
    assert placed[0][1]["quantity"] > 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_loop_risk.py -v`
Expected: FAIL — StrategyLoop 构造函数不接受 risk_engine/account_equity/event_callback 参数，_execute_action 也不做风控检查。

- [ ] **Step 3: 重写 strategy/loop.py**

将 `backend/strategy/loop.py` 替换为：

```python
# -*- coding: utf-8 -*-
"""StrategyLoop — 实盘策略循环

使用 axon_quant.exchange adapter 获取行情，
执行策略生成的 Action 订单，强制经过风控检查。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from axon_bridge import Action

logger = logging.getLogger(__name__)


class StrategyLoop:
    """实盘策略循环

    Args:
        adapter: 交易所适配器（axon_quant.exchange.*Adapter）
        strategy: 策略实例（实现 on_bar → Action）
        symbol: 交易对符号
        interval: 轮询间隔（秒）
        risk_engine: 风控引擎（需实现 check_order(order, portfolio) -> {"passed": bool, "reason": str}）
        account_equity: 账户净值（用于 target_position → qty 转换）
        event_callback: 事件回调 fn(event_type: str, data: dict)，用于 WebSocket 推送和状态更新
    """

    def __init__(
        self,
        adapter: Any,
        strategy: Any,
        symbol: str,
        interval: float = 1.0,
        risk_engine: Any = None,
        account_equity: float = 100_000.0,
        event_callback: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ):
        self._adapter = adapter
        self._strategy = strategy
        self._symbol = symbol
        self._interval = interval
        self._risk_engine = risk_engine
        self._account_equity = account_equity
        self._event_callback = event_callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._order_count = 0
        self._rejected_count = 0
        self._fill_count = 0
        self._last_price = 0.0
        self._last_action: Optional[str] = None

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "order_count": self._order_count,
            "fill_count": self._fill_count,
            "rejected_count": self._rejected_count,
            "last_price": self._last_price,
            "last_action": self._last_action,
        }

    def start(self) -> None:
        self._adapter.connect()
        if hasattr(self._adapter, "subscribe"):
            self._adapter.subscribe([self._symbol])

        self._strategy.on_start()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"StrategyLoop 已启动: {self._symbol}")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._strategy.on_stop()
        self._adapter.disconnect()
        logger.info(f"StrategyLoop 已停止: {self._symbol}")

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """发出事件回调（线程安全）"""
        if self._event_callback:
            try:
                self._event_callback(event_type, data)
            except Exception as e:
                logger.error(f"事件回调失败 ({event_type}): {e}")

    def _run_loop(self) -> None:
        while self._running:
            try:
                ticker = self._adapter.get_ticker(self._symbol)
                close_price = float(ticker.get("last", 0.0))
                bar = {
                    "open": float(ticker.get("open", close_price)),
                    "high": float(ticker.get("high", close_price)),
                    "low": float(ticker.get("low", close_price)),
                    "close": close_price,
                    "volume": float(ticker.get("volume", 0.0)),
                    "symbol": self._symbol,
                    "timestamp_ns": int(time.time() * 1_000_000_000),
                }
                self._last_price = close_price

                action = self._strategy.on_bar(bar)
                action_type_str = str(action.action_type)
                self._last_action = action_type_str
                if action_type_str in ("buy", "sell"):
                    self._execute_action(action, close_price)

                self._emit("bar.processed", {
                    "symbol": self._symbol,
                    "price": close_price,
                    "action": action_type_str,
                    "timestamp": bar["timestamp_ns"],
                })

            except Exception as e:
                logger.error(f"StrategyLoop 错误: {e}", exc_info=True)

            time.sleep(self._interval)

    def _execute_action(self, action: Action, current_price: float) -> None:
        """执行 Action：置信度过滤 → qty 计算 → 风控检查 → 下单"""
        try:
            # 1. 置信度过滤
            confidence = float(getattr(action, "confidence", 1.0) or 0.0)
            if confidence < 0.3:
                logger.debug(f"信号置信度 {confidence:.2f} < 0.3，跳过")
                return

            # 2. qty 计算：target_position 是仓位比例（与 BacktestLoop 一致）
            ratio = float(getattr(action, "target_position", 0.0) or 0.0)
            action_type_str = str(action.action_type)
            if current_price <= 0:
                logger.warning(f"当前价格无效: {current_price}")
                return
            qty = abs(ratio) * self._account_equity / current_price
            if qty <= 0:
                return

            side = "Buy" if action_type_str == "buy" else "Sell"

            order_dict = {
                "symbol": self._symbol,
                "side": side,
                "type": "market",
                "quantity": qty,
                "price": current_price,
            }

            # 3. 风控检查
            if self._risk_engine is not None:
                portfolio_state = {"cash": {"USD": self._account_equity}}
                check = self._risk_engine.check_order(order_dict, portfolio_state)
                if not check.get("passed"):
                    self._rejected_count += 1
                    reason = check.get("reason", "unknown")
                    self._emit("order.rejected", {
                        "symbol": self._symbol,
                        "side": side,
                        "quantity": qty,
                        "price": current_price,
                        "reason": reason,
                    })
                    logger.warning(f"风控拒绝订单: {reason}")
                    return

            # 4. 执行下单
            result = self._adapter.place_order(order_dict)
            self._order_count += 1

            self._emit("order.placed", {
                "symbol": self._symbol,
                "side": side,
                "quantity": qty,
                "price": current_price,
                "order_id": result.get("order_id", "") if isinstance(result, dict) else "",
                "confidence": confidence,
            })
            logger.info(f"订单已执行: {order_dict} -> {result}")

        except Exception as e:
            logger.error(f"订单执行失败: {e}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_loop_risk.py -v`
Expected: 5 passed

- [ ] **Step 5: 确认现有 backtest 测试不受影响**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/backtest/ tests/unit/strategy/ -v 2>&1 | tail -20`
Expected: 所有已有测试通过。

- [ ] **Step 6: Commit**

```bash
git add backend/strategy/loop.py backend/tests/unit/engine/test_loop_risk.py
git commit -m "feat(strategy): add risk check, qty fix, event callbacks to StrategyLoop"
```

---

### Task 3: TradingEngine 单例 + 状态追踪 + WebSocket 广播

**Files:**
- Modify: `backend/engine/trading_engine.py`

- [ ] **Step 1: 先写失败测试**

创建 `backend/tests/unit/engine/test_trading_engine.py`：

```python
# -*- coding: utf-8 -*-
"""TradingEngine 单例和生命周期测试"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.config import EngineConfig
from engine.strategy_runtime import StrategyRuntime


def test_get_trading_engine_singleton():
    """get_trading_engine 始终返回同一实例"""
    # 需要清除 lru_cache 以避免其他测试干扰
    from engine import trading_engine
    trading_engine.get_trading_engine.cache_clear()

    from engine.trading_engine import get_trading_engine
    with patch("engine.trading_engine.BinanceAdapter") as mock_binance, \
         patch("engine.trading_engine.DefaultRiskEngine") as mock_risk:
        mock_binance.return_value = MagicMock()
        mock_risk.return_value = MagicMock()
        mock_risk.return_value.check_order = MagicMock(return_value={"passed": True, "reason": None})

        config = EngineConfig(exchange="binance", trading_mode="paper")
        e1 = get_trading_engine(config)
        e2 = get_trading_engine()  # 第二次不传 config
        assert e1 is e2

    trading_engine.get_trading_engine.cache_clear()


def test_register_strategy_returns_id_and_tracks():
    """register_strategy 返回 sid 并记录 runtime"""
    from engine import trading_engine
    trading_engine.get_trading_engine.cache_clear()

    from engine.trading_engine import get_trading_engine
    with patch("engine.trading_engine.BinanceAdapter"), \
         patch("engine.trading_engine.DefaultRiskEngine"):
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        strategy = MagicMock()
        sid = engine.register_strategy(strategy, ["BTCUSDT"])
        assert sid
        assert len(engine.list_strategies()) == 1
        status = engine.list_strategies()[0]
        assert status["symbols"] == ["BTCUSDT"]
        assert status["id"] == sid

    trading_engine.get_trading_engine.cache_clear()


def test_get_strategy_status():
    """get_strategy_status 返回完整状态字典"""
    from engine import trading_engine
    trading_engine.get_trading_engine.cache_clear()

    from engine.trading_engine import get_trading_engine
    with patch("engine.trading_engine.BinanceAdapter"), \
         patch("engine.trading_engine.DefaultRiskEngine"):
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        strategy = MagicMock()
        sid = engine.register_strategy(strategy, ["ETHUSDT"])
        rt = engine._strategies[sid]
        rt.order_count = 5
        rt.rejected_count = 1
        rt.last_action = "buy"
        rt.last_price = 3500.0
        rt.status = "running"

        status = engine.get_strategy_status(sid)
        assert status["order_count"] == 5
        assert status["rejected_count"] == 1
        assert status["last_action"] == "buy"
        assert status["symbols"] == ["ETHUSDT"]

    trading_engine.get_trading_engine.cache_clear()


def test_stop_strategy_updates_status():
    """stop_strategy 更新状态并停止 loop"""
    from engine import trading_engine
    trading_engine.get_trading_engine.cache_clear()

    from engine.trading_engine import get_trading_engine
    with patch("engine.trading_engine.BinanceAdapter"), \
         patch("engine.trading_engine.DefaultRiskEngine"):
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        mock_loop = MagicMock()
        strategy = MagicMock()
        sid = engine.register_strategy(strategy, ["BTCUSDT"])
        engine._strategies[sid].loop = mock_loop
        engine._strategies[sid].status = "running"

        result = engine.stop_strategy(sid)
        assert result is True
        mock_loop.stop.assert_called_once()
        assert engine._strategies[sid].status == "stopped"

    trading_engine.get_trading_engine.cache_clear()


def test_engine_status():
    """engine_status 返回引擎概览"""
    from engine import trading_engine
    trading_engine.get_trading_engine.cache_clear()

    from engine.trading_engine import get_trading_engine
    with patch("engine.trading_engine.BinanceAdapter"), \
         patch("engine.trading_engine.DefaultRiskEngine"):
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        engine._strategies.clear()

        status = engine.engine_status()
        assert status["exchange"] == "binance"
        assert status["mode"] == "paper"
        assert status["running_strategies"] == 0
        assert status["exchange_connected"] is True
        assert status["risk_available"] is True

    trading_engine.get_trading_engine.cache_clear()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py -v`
Expected: FAIL — get_trading_engine 不存在，get_strategy_status 和 engine_status 方法不存在。

- [ ] **Step 3: 重写 trading_engine.py**

将 `backend/engine/trading_engine.py` 替换为：

```python
# -*- coding: utf-8 -*-
"""TradingEngine — 核心交易引擎

统一管理策略生命周期，注入 exchange adapter + risk engine，
桥接 backtest ↔ live。单例模式，通过 get_trading_engine() 获取。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from functools import lru_cache
from typing import Any, Optional

import pandas as pd

from .config import EngineConfig
from .strategy_runtime import StrategyRuntime
from backtest.backtest_loop import BacktestLoop, BacktestResult, RuleStrategy
from strategy.loop import StrategyLoop

logger = logging.getLogger(__name__)

# WebSocket 事件推送 topic
_WS_TOPIC = "strategy"


def _ws_emit(event_type: str, data: dict[str, Any]) -> None:
    """线程安全地将事件推送到 WebSocket 消息队列。

    StrategyLoop 运行在独立线程中，通过 manager.message_queue.put_nowait
    跨线程投递消息，与 core/lifespan.py 中 kline_consumer 的模式一致。
    """
    try:
        from websocket.manager import manager
        if manager.message_queue is None:
            return
        message = {
            "type": event_type,
            "topic": _WS_TOPIC,
            "timestamp": int(time.time() * 1000),
            "data": data,
        }
        manager.message_queue.put_nowait(message)
    except Exception:
        # WebSocket 不可用时不阻塞交易逻辑
        pass


class TradingEngine:
    """核心交易引擎"""

    def __init__(self, config: EngineConfig):
        self._config = config
        self._strategies: dict[str, StrategyRuntime] = {}
        self._exchange = self._create_exchange_adapter(config)
        self._risk_engine = self._create_risk_engine(config)

        logger.info(
            f"TradingEngine 已初始化: "
            f"exchange={config.exchange}, "
            f"mode={config.trading_mode}"
        )

    def _create_exchange_adapter(self, config: EngineConfig) -> Optional[Any]:
        try:
            if config.exchange == "binance":
                from axon_bridge.exchange import BinanceAdapter, ExchangeConfig
                exchange_config = ExchangeConfig(
                    exchange_id="binance",
                    testnet=config.trading_mode == "paper",
                )
                return BinanceAdapter(exchange_config)
            elif config.exchange == "okx":
                from axon_bridge.exchange import OkxAdapter, ExchangeConfig
                exchange_config = ExchangeConfig(
                    exchange_id="okx",
                    testnet=config.trading_mode == "paper",
                )
                return OkxAdapter(exchange_config)
            else:
                logger.warning(f"不支持的交易所: {config.exchange}")
                return None
        except Exception as e:
            logger.error(f"创建 exchange adapter 失败: {e}")
            return None

    def _create_risk_engine(self, config: EngineConfig) -> Optional[Any]:
        """创建 axon_quant 风控引擎。API 路由层使用 services.risk_service 单例，
        引擎层直接用 axon_bridge 的 DefaultRiskEngine 进行实盘前检查。"""
        try:
            from services.risk_service import get_risk_service
            return get_risk_service()
        except Exception as e:
            logger.error(f"创建 risk engine 失败: {e}")
            return None

    @property
    def exchange(self) -> Optional[Any]:
        return self._exchange

    @property
    def risk_engine(self) -> Optional[Any]:
        return self._risk_engine

    def engine_status(self) -> dict[str, Any]:
        """返回引擎概览状态"""
        running = sum(1 for rt in self._strategies.values() if rt.status == "running")
        return {
            "exchange": self._config.exchange,
            "mode": self._config.trading_mode,
            "exchange_connected": self._exchange is not None,
            "risk_available": self._risk_engine is not None,
            "total_strategies": len(self._strategies),
            "running_strategies": running,
        }

    def register_strategy(
        self,
        strategy: Any,
        symbols: list[str],
        strategy_name: str = "",
        params: dict[str, Any] | None = None,
        mode: str = "paper",
    ) -> str:
        sid = str(uuid.uuid4())[:8]
        self._strategies[sid] = StrategyRuntime(
            strategy_id=sid,
            strategy=strategy,
            symbols=list(symbols),
            strategy_name=strategy_name or strategy.__class__.__name__,
            params=params or {},
            mode=mode,
        )
        logger.info(f"策略已注册: {sid} {symbols}")
        _ws_emit("strategy.registered", {
            "strategy_id": sid,
            "symbols": symbols,
            "strategy_name": strategy_name,
            "mode": mode,
        })
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
        if self._exchange is None:
            raise RuntimeError(
                "exchange adapter 不可用，无法启动实盘策略。"
                "请确保 axon_quant.exchange 已安装并配置正确。"
            )

        sid = self.register_strategy(
            strategy, symbols, strategy_name, params, mode=mode
        )
        runtime = self._strategies[sid]

        # 创建事件回调，更新 runtime 计数
        def event_callback(event_type: str, data: dict[str, Any]) -> None:
            if event_type == "order.placed":
                runtime.order_count += 1
                runtime.last_price = data.get("price", runtime.last_price)
                runtime.last_action = data.get("side", "").lower()
            elif event_type == "order.rejected":
                runtime.rejected_count += 1
            elif event_type == "bar.processed":
                runtime.last_price = data.get("price", runtime.last_price)
                runtime.last_action = data.get("action", runtime.last_action)
            # 附加 strategy_id 后广播
            data["strategy_id"] = sid
            _ws_emit(event_type, data)

        loop = StrategyLoop(
            adapter=self._exchange,
            strategy=strategy,
            symbol=symbols[0],
            risk_engine=self._risk_engine,
            account_equity=account_equity,
            event_callback=event_callback,
        )
        loop.start()

        runtime.loop = loop
        runtime.status = "running"
        runtime.started_at = time.monotonic()

        logger.info(f"策略已启动: {sid} {symbols}")
        _ws_emit("strategy.started", {
            "strategy_id": sid,
            "symbols": symbols,
            "strategy_name": runtime.strategy_name,
            "mode": mode,
        })
        return sid

    def stop_strategy(self, strategy_id: str) -> bool:
        if strategy_id not in self._strategies:
            logger.warning(f"策略不存在: {strategy_id}")
            return False

        runtime = self._strategies[strategy_id]
        if runtime.loop is not None:
            runtime.loop.stop()
        runtime.status = "stopped"
        logger.info(f"策略已停止: {strategy_id}")
        _ws_emit("strategy.stopped", {
            "strategy_id": strategy_id,
            "strategy_name": runtime.strategy_name,
        })
        return True

    def get_strategy_status(self, strategy_id: str) -> Optional[dict[str, Any]]:
        runtime = self._strategies.get(strategy_id)
        if runtime is None:
            return None
        # 从 loop 同步最新统计
        if runtime.loop is not None and hasattr(runtime.loop, "stats"):
            stats = runtime.loop.stats
            runtime.order_count = stats["order_count"]
            runtime.fill_count = stats["fill_count"]
            runtime.rejected_count = stats["rejected_count"]
            runtime.last_price = stats["last_price"]
            runtime.last_action = stats["last_action"]
        return runtime.to_dict()

    def list_strategies(self) -> list[dict]:
        return [
            self.get_strategy_status(sid) or {"id": sid, "status": "unknown"}
            for sid in self._strategies
        ]

    def run_backtest(
        self,
        strategy: RuleStrategy,
        data: pd.DataFrame,
        symbol: str = "BTCUSDT",
        initial_cash: float = 100_000.0,
    ) -> BacktestResult:
        loop = BacktestLoop(initial_cash=initial_cash)
        return loop.run(strategy, data, symbol)


@lru_cache(maxsize=1)
def get_trading_engine(config: EngineConfig | None = None) -> TradingEngine:
    """获取 TradingEngine 单例。首次调用需传入 config。"""
    if config is None:
        config = EngineConfig(exchange="binance", trading_mode="paper")
    return TradingEngine(config)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_trading_engine.py -v`
Expected: 5 passed

- [ ] **Step 5: 运行之前的所有相关测试确认无回归**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/ tests/unit/services/ tests/unit/backtest/ -v 2>&1 | tail -30`
Expected: 所有测试通过。

- [ ] **Step 6: Commit**

```bash
git add backend/engine/trading_engine.py backend/tests/unit/engine/test_trading_engine.py
git commit -m "feat(engine): TradingEngine singleton with status tracking and WebSocket events"
```

---

### Task 4: 新增 engine/routes.py REST API

**Files:**
- Create: `backend/engine/routes.py`

- [ ] **Step 1: 创建 engine API 路由文件**

创建 `backend/engine/routes.py`：

```python
# -*- coding: utf-8 -*-
"""Engine API routes — 交易引擎管理和策略运行控制"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from common.schemas import ApiResponse
from strategy.loader import StrategyLoader

router = APIRouter(prefix="/api/engine", tags=["Engine"])


def _sanitize(obj: Any) -> Any:
    """替换 NaN/inf 为 None，确保 JSON 可序列化"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


# ---------- 请求模型 ----------

class StartStrategyRequest(BaseModel):
    strategy_name: str = Field(..., description="策略模板名（已注册）")
    symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT"])
    mode: str = Field(default="paper", description="paper | live")
    params: dict[str, Any] = Field(default_factory=dict)
    initial_cash: float = Field(default=100_000.0, gt=0)
    account: str | None = Field(default=None, description="凭证名（live 模式需要）")


class BacktestRequest(BaseModel):
    strategy_name: str = Field(..., description="策略模板名")
    symbol: str = Field(default="BTCUSDT")
    data: list[dict[str, Any]] = Field(..., min_length=1, description="OHLCV 数据列表，每条必须包含 open/high/low/close/volume")
    params: dict[str, Any] = Field(default_factory=dict)
    initial_cash: float = Field(default=100_000.0, gt=0)
    # ponytail: v1 仅支持请求体传入 data，数据库查询数据源后续接入


# ---------- 端点 ----------

@router.get("/status")
async def engine_status() -> ApiResponse:
    """获取引擎状态概览"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    return ApiResponse(code=0, message="ok", data=engine.engine_status())


@router.get("/strategies")
async def list_strategies() -> ApiResponse:
    """列出所有策略及其运行状态"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    return ApiResponse(code=0, message="ok", data=engine.list_strategies())


@router.post("/strategies/start")
async def start_strategy(req: StartStrategyRequest) -> ApiResponse:
    """启动策略（paper 或 live 模式）"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()

    # 加载策略类
    strategy_cls = StrategyLoader.get(req.strategy_name)
    from strategy.base import StrategyConfig
    config = StrategyConfig(
        name=req.strategy_name,
        symbol=req.symbols[0],
        params=req.params,
    )
    strategy = strategy_cls(config)

    if req.mode == "live" and not req.account:
        raise HTTPException(status_code=400, detail="live 模式必须指定 account 凭证名")

    sid = engine.start_strategy(
        strategy=strategy,
        symbols=req.symbols,
        strategy_name=req.strategy_name,
        params=req.params,
        account_equity=req.initial_cash,
        mode=req.mode,
    )
    return ApiResponse(
        code=0,
        message="策略启动成功",
        data={"strategy_id": sid, "status": "running", "mode": req.mode},
    )


@router.post("/strategies/{sid}/stop")
async def stop_strategy(sid: str) -> ApiResponse:
    """停止运行中的策略"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    ok = engine.stop_strategy(sid)
    if not ok:
        raise HTTPException(status_code=404, detail=f"策略 {sid} 不存在")
    return ApiResponse(code=0, message="策略已停止", data={"strategy_id": sid})


@router.get("/strategies/{sid}/status")
async def get_strategy_status(sid: str) -> ApiResponse:
    """获取单个策略运行详情"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()
    status = engine.get_strategy_status(sid)
    if status is None:
        raise HTTPException(status_code=404, detail=f"策略 {sid} 不存在")
    return ApiResponse(code=0, message="ok", data=status)


@router.post("/backtest")
async def run_backtest(req: BacktestRequest) -> ApiResponse:
    """运行回测"""
    from engine.trading_engine import get_trading_engine
    engine = get_trading_engine()

    # 加载策略
    strategy_cls = StrategyLoader.get(req.strategy_name)
    from strategy.base import StrategyConfig
    config = StrategyConfig(
        name=req.strategy_name,
        symbol=req.symbol,
        params=req.params,
    )
    strategy = strategy_cls(config)

    # 数据加载：v1 要求请求体直接提供 OHLCV data 列表
    df = pd.DataFrame(req.data)
    # 兼容大小写列名
    col_map = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    for upper, lower in col_map.items():
        if lower not in df.columns and upper in df.columns:
            df[lower] = df[upper]
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(status_code=400, detail=f"数据缺少必要列: {missing}")

    # 若有 timestamp/datetime 列，设为索引以兼容 BacktestLoop 的 DatetimeIndex 处理
    if "timestamp" in df.columns:
        try:
            df.index = pd.to_datetime(df["timestamp"], unit="ns", utc=True)
        except Exception:
            pass

    if len(df) == 0:
        raise HTTPException(status_code=400, detail="数据为空，无法回测")

    result = engine.run_backtest(
        strategy=strategy,
        data=df,
        symbol=req.symbol,
        initial_cash=req.initial_cash,
    )

    return ApiResponse(
        code=0,
        message="回测完成",
        data=_sanitize({
            "total_pnl": result.total_pnl,
            "total_orders": result.total_orders,
            "fills": result.fills,
            "final_nav": result.final_nav,
            "max_drawdown": result.max_drawdown,
            "max_drawdown_pct": result.max_drawdown_pct,
            "win_rate": result.win_rate,
            "sharpe_ratio": result.sharpe_ratio,
            "total_fees": result.total_fees,
            "nav_peak": result.nav_peak,
            "bar_count": result.bar_count,
            "equity_curve": result.equity_curve,
            "trade_records": result.trade_records,
        }),
    )
```

- [ ] **Step 2: 验证模块导入**

Run: `cd backend && .venv/bin/python -c "from engine.routes import router; print(f'Routes: {len(router.routes)}'); [print(f'  {r.methods} {r.path}') for r in router.routes]"`
Expected: 输出 6 个路由（status, strategies list, start, stop, status detail, backtest）。

- [ ] **Step 3: Commit**

```bash
git add backend/engine/routes.py
git commit -m "feat(engine): add engine REST API routes for strategy lifecycle and backtest"
```

---

### Task 5: Deployer 实盘接入 TradingEngine

**Files:**
- Modify: `backend/engine/deployer.py`
- Test: `backend/tests/unit/engine/test_deployer.py`

- [ ] **Step 1: 写测试**

创建 `backend/tests/unit/engine/test_deployer.py`：

```python
# -*- coding: utf-8 -*-
"""StrategyDeployer 测试"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.deployer import StrategyDeployer, WorkerHandle


def test_dry_run_creates_handle_without_starting():
    """干跑模式创建 handle 但不启动 StrategyLoop"""
    deployer = StrategyDeployer(dry_run=True)
    with patch("engine.deployer.CredentialsService") as mock_cred_cls, \
         patch("engine.deployer.StrategyLoader") as mock_loader:
        mock_cred_cls.return_value.get_credential.return_value = ("key", "secret")
        mock_strategy_cls = MagicMock()
        mock_strategy_cls.return_value = MagicMock()
        mock_loader.get.return_value = mock_strategy_cls

        handle = deployer.deploy("dual_ma", "test_account", "BTCUSDT")
        assert isinstance(handle, WorkerHandle)
        assert handle.status == "running"
        assert handle.strategy_name == "dual_ma"
        assert handle.symbol == "BTCUSDT"
        # 干跑模式 engine_strategy_id 为空
        assert handle.engine_strategy_id is None


def test_live_mode_delegates_to_trading_engine():
    """实盘模式委托给 TradingEngine.start_strategy"""
    deployer = StrategyDeployer(dry_run=False)
    with patch("engine.deployer.CredentialsService") as mock_cred_cls, \
         patch("engine.deployer.StrategyLoader") as mock_loader, \
         patch("engine.deployer.get_trading_engine") as mock_get_engine:
        mock_cred_cls.return_value.get_credential.return_value = ("key", "secret")
        mock_strategy_cls = MagicMock()
        mock_strategy_instance = MagicMock()
        mock_strategy_cls.return_value = mock_strategy_instance
        mock_loader.get.return_value = mock_strategy_cls

        mock_engine = MagicMock()
        mock_engine.start_strategy.return_value = "test_sid_123"
        mock_get_engine.return_value = mock_engine

        handle = deployer.deploy("dual_ma", "live_account", "BTCUSDT")
        assert handle.engine_strategy_id == "test_sid_123"
        assert handle.mode == "live"
        mock_engine.start_strategy.assert_called_once()


def test_stop_delegates_to_engine():
    """stop 委托给 TradingEngine.stop_strategy"""
    deployer = StrategyDeployer(dry_run=False)
    with patch("engine.deployer.get_trading_engine") as mock_get_engine:
        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        handle = WorkerHandle(
            worker_id=__import__("uuid").uuid4(),
            strategy_name="dual_ma",
            account_name="test",
            symbol="BTCUSDT",
            status="running",
            engine_strategy_id="sid_456",
            mode="live",
        )
        deployer.stop(handle)
        mock_engine.stop_strategy.assert_called_once_with("sid_456")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_deployer.py -v`
Expected: FAIL — WorkerHandle 没有 engine_strategy_id 和 mode 字段，deployer 实盘模式抛 NotImplementedError。

- [ ] **Step 3: 更新 deployer.py**

将 `backend/engine/deployer.py` 替换为：

```python
"""策略 → 账户 → 实盘部署

ponytail: deploy 流程 = 取凭证 + 加载策略 + 启动策略循环
         干跑模式: 不真下单,仅验证凭证 + 策略可加载
         实盘模式: 委托 TradingEngine.start_strategy()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from credentials.service import CredentialsService
from credentials.exceptions import AccountNotFoundError
from strategy.base import BaseStrategy, StrategyConfig
from strategy.loader import StrategyLoader


@dataclass
class WorkerHandle:
    """worker 句柄,表示一个运行中的策略实例。"""
    worker_id: UUID
    strategy_name: str
    account_name: str
    symbol: str
    status: str  # running | stopped | error
    engine_strategy_id: str | None = None  # TradingEngine 返回的 sid
    mode: str = "dry_run"
    started_at: float = 0.0


class StrategyDeployer:
    """策略部署器:把策略 + 账户 + 标的 绑成 worker。"""

    def __init__(self, dry_run: bool = True, credentials_db: str | None = None):
        self.dry_run = dry_run
        self.credentials = CredentialsService(db_path=credentials_db) if credentials_db else CredentialsService()
        self._workers: dict[UUID, WorkerHandle] = {}

    def deploy(self, strategy_name: str, account_name: str, symbol: str) -> WorkerHandle:
        """部署策略到指定账户/标的。

        Raises:
            AccountNotFoundError: 账号不存在
            ValueError: 策略名未知
        """
        import time

        # 1. 验证凭证存在
        api_key, api_secret = self.credentials.get_credential(account_name)

        # 2. 加载策略类
        strategy_cls = StrategyLoader.get(strategy_name)
        config = StrategyConfig(name=strategy_name, symbol=symbol)
        strategy: BaseStrategy = strategy_cls(config)

        worker_id = uuid4()
        mode = "dry_run" if self.dry_run else "paper"  # 默认 paper，后续可扩展 live

        # 3. 干跑模式: 仅记录, 不真接入 TradingEngine
        if self.dry_run:
            handle = WorkerHandle(
                worker_id=worker_id,
                strategy_name=strategy_name,
                account_name=account_name,
                symbol=symbol,
                status="running",
                engine_strategy_id=None,
                mode="dry_run",
                started_at=time.monotonic(),
            )
            self._workers[worker_id] = handle
            return handle

        # 4. 实盘/paper 模式: 委托 TradingEngine
        from engine.trading_engine import get_trading_engine
        engine = get_trading_engine()
        sid = engine.start_strategy(
            strategy=strategy,
            symbols=[symbol],
            strategy_name=strategy_name,
            mode=mode,
        )

        handle = WorkerHandle(
            worker_id=worker_id,
            strategy_name=strategy_name,
            account_name=account_name,
            symbol=symbol,
            status="running",
            engine_strategy_id=sid,
            mode=mode,
            started_at=time.monotonic(),
        )
        self._workers[worker_id] = handle
        return handle

    def stop(self, handle: WorkerHandle) -> None:
        """停止 worker。"""
        if handle.engine_strategy_id:
            from engine.trading_engine import get_trading_engine
            engine = get_trading_engine()
            engine.stop_strategy(handle.engine_strategy_id)
        if handle.worker_id in self._workers:
            handle.status = "stopped"

    def list_active(self) -> list[WorkerHandle]:
        """列出所有 running 状态 worker。"""
        return [h for h in self._workers.values() if h.status == "running"]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/test_deployer.py -v`
Expected: 3 passed

- [ ] **Step 5: 运行所有 engine 测试**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/engine/ -v`
Expected: 所有测试通过（trading_engine + loop_risk + deployer）。

- [ ] **Step 6: Commit**

```bash
git add backend/engine/deployer.py backend/tests/unit/engine/test_deployer.py
git commit -m "feat(engine): wire StrategyDeployer live mode to TradingEngine"
```

---

### Task 6: lifespan 初始化 + main.py 路由注册 + health 增强

**Files:**
- Modify: `backend/core/lifespan.py`
- Modify: `backend/main.py`

- [ ] **Step 1: 在 lifespan 中初始化 TradingEngine**

在 `backend/core/lifespan.py` 中，在 WebSocket manager start 之后（约第 230 行后），添加 TradingEngine 初始化：

在现有代码 `logger.info("WebSocket连接管理器启动成功")` 之后，添加：

```python
    # 初始化 TradingEngine（paper 模式默认配置）
    try:
        from engine.trading_engine import get_trading_engine
        from engine.config import EngineConfig
        engine = get_trading_engine(EngineConfig(exchange="binance", trading_mode="paper"))
        app.state.trading_engine = engine
        logger.info(f"TradingEngine 初始化完成: {engine.engine_status()}")
    except Exception as e:
        logger.error(f"TradingEngine 初始化失败: {e}")
```

注意：在 `yield` 之前的启动阶段添加，在 shutdown 阶段（yield 之后），在"步骤 5" WebSocket 停止之前，添加：

```python
    # 步骤 4.5: 停止 TradingEngine 中所有运行的策略
    try:
        if hasattr(app.state, "trading_engine"):
            engine = app.state.trading_engine
            for rt in list(engine._strategies.values()):
                if rt.status == "running" and rt.loop:
                    try:
                        engine.stop_strategy(rt.strategy_id)
                    except Exception as stop_err:
                        logger.error(f"停止策略 {rt.strategy_id} 失败: {stop_err}")
            logger.info("TradingEngine 所有策略已停止")
    except Exception as e:
        logger.error(f"TradingEngine 关闭失败: {e}")
```

- [ ] **Step 2: 在 main.py 中注册 engine router**

在 `backend/main.py` 的 router 注册部分（搜索 `app.include_router`），添加：

```python
from engine.routes import router as engine_router
app.include_router(engine_router)
```

- [ ] **Step 3: 增强 /health 端点**

在 main.py 的 health 端点中加入引擎状态：

找到现有 health 端点，替换为：

```python
@app.get("/health")
async def health_check():
    try:
        from engine.trading_engine import get_trading_engine
        engine = get_trading_engine()
        engine_status = engine.engine_status()
    except Exception:
        engine_status = {"status": "not_initialized"}
    return {"status": "ok", "service": "QuantCell API", "engine": engine_status}
```

- [ ] **Step 4: 验证服务启动**

Run: `cd backend && timeout 8 .venv/bin/python -c "
import uvicorn, threading, time, requests
def run_server():
    uvicorn.run('main:app', host='127.0.0.1', port=18999, log_level='error')
t = threading.Thread(target=run_server, daemon=True)
t.start()
time.sleep(4)
import urllib.request
resp = urllib.request.urlopen('http://127.0.0.1:18999/health')
import json
data = json.loads(resp.read())
print('Health:', data['status'])
print('Engine mode:', data['engine'].get('mode'))
print('Engine exchange:', data['engine'].get('exchange'))
assert data['status'] == 'ok'
assert 'engine' in data
print('✅ Health endpoint with engine status OK')
" 2>&1`
Expected: 输出包含 Health: ok 和引擎状态信息，无异常。

- [ ] **Step 5: Commit**

```bash
git add backend/core/lifespan.py backend/main.py
git commit -m "feat(engine): initialize TradingEngine in lifespan, register engine routes, enhance health"
```

---

### Task 7: 完整验证

- [ ] **Step 1: 运行所有单元测试**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/services/ tests/unit/engine/ tests/unit/backtest/ tests/unit/strategy/ tests/unit/api/ -v 2>&1 | tail -40`
Expected: 所有测试通过（包含之前的 246+ 测试 + 新增的 engine 测试）。

- [ ] **Step 2: 验证 API 端点可达**

Run: 使用 curl 或 Python 验证（同 Task 6 Step 4 的方式）：
- `GET /api/engine/status` 返回引擎状态
- `GET /api/engine/strategies` 返回空列表
- `GET /health` 包含 engine 字段

- [ ] **Step 3: 运行 CLI 确认不破坏**

Run: `cd backend && .venv/bin/python -m cli.run --help`
Expected: CLI 正常输出，无 ImportError。

- [ ] **Step 4: 前端构建验证**

Run: `cd frontend && bun run build 2>&1 | tail -10`
Expected: 构建成功（前端未修改，应无变化）。

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test(engine): verify full pipeline - all tests pass"
```
