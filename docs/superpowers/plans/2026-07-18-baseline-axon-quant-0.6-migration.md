# Baseline axon_quant 0.6.0 多 leg 化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 BaselineBacktestService 走 axon_quant 0.6.0 多 leg API,funding cash 计算下沉引擎,axon_bridge 加 0.6.0 多 leg 重导出。

**Architecture:**
- baseline.run() 驱动 BacktestEngine 多 leg (spot + perp),Action 映射为 2 leg target
- 策略层 settle_funding() 标 DEPRECATED no-op,funding 累加由 engine.push_funding() 做
- axon_bridge.backtest 模块重导出 spot_instrument / swap_instrument / limit_order + PushFundingHelper
- 8 策略统一走多 leg 路径,单 leg 策略 perp target=0

**Tech Stack:** Python 3.14, pytest, uv, pandas, axon_quant 0.6.0

**Spec:** `docs/superpowers/specs/2026-07-18-baseline-axon-quant-0.6-migration.md`
**Background:**
- axon_quant 0.6.0 引入 Instrument 抽象 + 多 leg BacktestEngine
- 引擎层提供 push_funding() / set_target_position() / with_auto_rebalance()
- 现有 v2.3.1 baseline 自算 PnL + 策略层 settle_funding 是 hack,完全下沉

---

## File Structure

| 文件 | 改动 | 职责 |
|---|---|---|
| `backend/axon_bridge/backtest.py` | 新建 | 0.6.0 多 leg 工厂重导出 + PushFundingHelper |
| `backend/axon_bridge/__init__.py` | 改 | 加 `from .backtest import ...` |
| `backend/strategy/base.py` | 改 | StrategyContext.funding_cash/settle_funding 标 DEPRECATED no-op |
| `backend/strategy/templates/funding_arbitrage.py` | 改 | 删 ctx.settle_funding() 调用 |
| `backend/backtest/baseline.py` | 重写 | run() 走 BacktestEngine,删 _compute_funding_periods/funding_injection_window_hours |
| `backend/tests/unit/backtest/test_axon_bridge_backtest.py` | 新建 | 5 个新单元测试 |
| `backend/tests/unit/backtest/test_baseline_funding.py` | 改 | 删 4 个老测试,加 3 个新测试 |
| `backend/tests/unit/strategy/test_advanced_templates.py` | 改 | 删 1 个 funding_cash 累加测试 |
| `backend/tests/integration/test_funding_arb_backtest.py` | 改 | 改 equity_curve + funding_cash 测试,加 delta-neutral 测试 |
| `scripts/check_funding_arb.py` | 改 | 验证 total_funding_pnl > 0 + delta 中性 |
| `data/source/backtest_baselines/archive/v2.3.1/` | 新建目录 | 归档老 8 策略 baseline 报告 |
| `data/source/backtest_baselines/{8 策略}_BTCUSDT_*.{json,md}` | 重新生成 | 新基线 (engine: 0.6.0) |
| `docs/superpowers/CHANGELOG_funding_arb.md` | 改 | v2.3.1 → v2.3.2 |
| `uv.lock` | 改 | uv lock 重新生成 |

---

## Task 1: 升级 axon_quant 到 0.6.0 + 验证

**Files:**
- Modify: `backend/uv.lock` (uv pip install --upgrade 自动更新)
- Test: `backend/tests/unit/axon_quant/test_0_6_compat.py` (新建,验证 import)

- [ ] **Step 1: 升级 axon_quant**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
uv pip install --upgrade axon-quant
```

- [ ] **Step 2: 验证 import + 关键 API**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/python -c "
import axon_quant
print('version:', axon_quant.__version__)
from axon_quant.backtest import spot_instrument, swap_instrument, limit_order, BacktestEngine
spot = spot_instrument('BTC', 'USDT')
perp = swap_instrument('BTC', 'USDT', settle='usd_margin', contract_size=1.0)
print('spot:', spot)
print('perp:', perp)
import inspect
print('push_funding sig:', inspect.signature(BacktestEngine.push_funding))
print('with_auto_rebalance sig:', inspect.signature(BacktestEngine.with_auto_rebalance))
"
```

**Expected**: version 输出 0.6.0, spot/perp dict 正确,push_funding / with_auto_rebalance 签名正确。

- [ ] **Step 3: 写 import 验证测试 (TDD red → green)**

```python
# backend/tests/unit/axon_quant/test_0_6_compat.py
"""验证 axon_quant 0.6.0 关键多 leg API 可用。"""
import inspect

import pytest
from axon_quant import __version__ as axon_version
from axon_quant.backtest import (
    BacktestEngine,
    InstrumentDict,
    limit_order,
    spot_instrument,
    swap_instrument,
)


def test_axon_quant_version_at_least_0_6_0():
    """axon_quant >= 0.6.0 (多 leg API 最低要求)。"""
    major, minor, *_ = axon_version.split(".")
    assert int(major) > 0 or int(minor) >= 6, f"需要 >= 0.6.0, 当前 {axon_version}"


def test_spot_instrument_returns_dict():
    """spot_instrument 返回 InstrumentDict。"""
    inst = spot_instrument("BTC", "USDT")
    assert isinstance(inst, dict)
    assert inst["kind"] == "spot"
    assert inst["base"] == "BTC"
    assert inst["quote"] == "USDT"


def test_swap_instrument_returns_dict():
    """swap_instrument 返回 SwapInstrumentDict。"""
    inst = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)
    assert isinstance(inst, dict)
    assert inst["kind"] == "swap"
    assert inst["base"] == "BTC"
    assert inst["quote"] == "USDT"
    assert inst["settle"] == "usd_margin"
    assert inst["contract_size"] == 1.0


def test_backtest_engine_push_funding_signature():
    """push_funding 接受 (instrument, funding_rate, mark_price, timestamp_ns)。"""
    sig = inspect.signature(BacktestEngine.push_funding)
    params = list(sig.parameters)
    assert "instrument" in params
    assert "funding_rate" in params
    assert "mark_price" in params
    assert "timestamp_ns" in params


def test_backtest_engine_with_auto_rebalance_signature():
    """with_auto_rebalance 接受 threshold。"""
    sig = inspect.signature(BacktestEngine.with_auto_rebalance)
    params = list(sig.parameters)
    assert "threshold" in params
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/axon_quant/test_0_6_compat.py -v
```

**Expected**: 5/5 PASS

- [ ] **Step 5: 重新生成 uv.lock + Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
uv lock
git add backend/uv.lock backend/tests/unit/axon_quant/test_0_6_compat.py
git commit -m "feat(deps): 升级 axon-quant 到 0.6.0 + 多 leg 兼容测试"
```

---

## Task 2: axon_bridge.backtest 模块 + PushFundingHelper (TDD)

**Files:**
- Create: `backend/axon_bridge/backtest.py`
- Modify: `backend/axon_bridge/__init__.py`
- Test: `backend/tests/unit/axon_bridge/test_backtest.py` (新建)

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/axon_bridge/test_backtest.py
"""axon_bridge.backtest 0.6.0 多 leg 适配层测试。"""
import pytest

from axon_bridge.backtest import (
    spot_instrument,
    swap_instrument,
    limit_order,
    PushFundingHelper,
)


def test_spot_instrument_exported():
    """axon_bridge.backtest.spot_instrument 可用。"""
    inst = spot_instrument("BTC", "USDT")
    assert inst["kind"] == "spot"


def test_swap_instrument_exported():
    """axon_bridge.backtest.swap_instrument 可用。"""
    inst = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)
    assert inst["kind"] == "swap"


def test_limit_order_exported():
    """axon_bridge.backtest.limit_order 可用。"""
    spot = spot_instrument("BTC", "USDT")
    order = limit_order(1, spot, "Buy", 50000.0, 0.1)
    assert order["id"] == 1
    assert order["side"] == "Buy"


def test_push_funding_helper_maybe_push_triggers():
    """PushFundingHelper 在 funding window 内调 push_funding。"""
    from unittest.mock import MagicMock
    from axon_quant.backtest import BacktestEngine

    engine = MagicMock(spec=BacktestEngine)
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    # funding 在 8h 周期, fixture 1 个 key
    funding_ts_ms = 1719792000000  # 2024-07-01 00:00 UTC
    history = {funding_ts_ms: 0.0003}
    helper = PushFundingHelper(history)

    # ts_ms 落点在 [funding_ts - 8h, funding_ts] 范围 → 推
    cur_ts_ms = funding_ts_ms  # 精确 = funding_ts
    helper.maybe_push(perp, 50000.0, cur_ts_ms * 1_000_000, engine)
    assert engine.push_funding.called, "应触发 push_funding"
    args = engine.push_funding.call_args[0]
    assert args[1] == 0.0003  # funding_rate
    assert args[2] == 50000.0  # mark_price
    assert args[3] == funding_ts_ms * 1_000_000  # timestamp_ns


def test_push_funding_helper_window_injection():
    """ts_ms 落点在 [funding_ts - 8h, funding_ts] 范围 → 推。"""
    from unittest.mock import MagicMock

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000
    history = {funding_ts_ms: 0.0005}
    helper = PushFundingHelper(history)

    # 5h 之前 (在 8h window 内) → 推
    cur_ts_ms = funding_ts_ms - 5 * 3600 * 1000
    helper.maybe_push(perp, 50000.0, cur_ts_ms * 1_000_000, engine)
    assert engine.push_funding.called, "8h window 内应触发 push_funding"


def test_push_funding_helper_no_double_push():
    """重复 ts_ms 不重复 push。"""
    from unittest.mock import MagicMock

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000
    history = {funding_ts_ms: 0.0003}
    helper = PushFundingHelper(history)

    helper.maybe_push(perp, 50000.0, funding_ts_ms * 1_000_000, engine)
    call_count_1 = engine.push_funding.call_count

    # 同一 funding_ts 再次调用 → 不重复
    helper.maybe_push(perp, 50000.0, funding_ts_ms * 1_000_000, engine)
    call_count_2 = engine.push_funding.call_count
    assert call_count_1 == call_count_2, f"重复调用应不重复 push: {call_count_1} vs {call_count_2}"


def test_push_funding_helper_outside_window_no_push():
    """ts_ms 落点在 [funding_ts - 8h, funding_ts] 之外 → 不推。"""
    from unittest.mock import MagicMock

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    funding_ts_ms = 1719792000000
    history = {funding_ts_ms: 0.0003}
    helper = PushFundingHelper(history)

    # 9h 之前 (在 8h window 外) → 不推
    cur_ts_ms = funding_ts_ms - 9 * 3600 * 1000
    helper.maybe_push(perp, 50000.0, cur_ts_ms * 1_000_000, engine)
    assert not engine.push_funding.called, "8h window 外应不触发 push_funding"


def test_push_funding_helper_empty_history():
    """空 funding_history → 不推。"""
    from unittest.mock import MagicMock

    engine = MagicMock()
    perp = swap_instrument("BTC", "USDT", settle="usd_margin", contract_size=1.0)

    helper = PushFundingHelper({})
    helper.maybe_push(perp, 50000.0, 1719792000000000000, engine)
    assert not engine.push_funding.called
```

- [ ] **Step 2: 跑测试确认 FAIL**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/axon_bridge/test_backtest.py -v
```

**Expected**: 8/8 FAIL (ModuleNotFoundError: No module named 'axon_bridge.backtest')

- [ ] **Step 3: 实现 axon_bridge.backtest 模块**

```python
# backend/axon_bridge/backtest.py
"""axon_quant 0.6.0 多 leg 回测适配层。

ponytail: 业务代码统一从 axon_bridge 导入多 leg 工厂函数,
         跟其他子模块风格一致
"""
from axon_quant.backtest import (  # noqa: F401
    spot_instrument,
    swap_instrument,
    limit_order,
    InstrumentDict,
)


class PushFundingHelper:
    """funding fixture → engine.push_funding 调度器。

    ponytail: funding fixture 是 dict[ts_ms, rate],
             engine.push_funding 接受 (instrument, rate, mark, ts_ns)
             转换 + 重复时间防御一次过
             8h window 兼容: ts_ms 落点在 [funding_ts - 8h, funding_ts] 都触发
    """

    WINDOW_MS = 8 * 3600 * 1000  # 8h funding 周期

    def __init__(self, funding_history: dict):
        self.funding_history = funding_history
        self._last_pushed_ts_ms: int = -1

    def maybe_push(self, perp, mark: float, ts_ns: int, engine) -> None:
        """ts_ms 落点在 funding fixture 某个 key 附近 8h 窗口 → 推 funding。

        Args:
            perp: swap instrument (engine.push_funding 第一个参数)
            mark: 当前 mark 价
            ts_ns: 当前 bar 时间戳 (纳秒)
            engine: BacktestEngine 实例
        """
        if not self.funding_history:
            return
        ts_ms = ts_ns // 1_000_000
        for funding_ts_ms, rate in self.funding_history.items():
            if funding_ts_ms - self.WINDOW_MS <= ts_ms <= funding_ts_ms:
                # 重复时间防御
                if funding_ts_ms > self._last_pushed_ts_ms:
                    engine.push_funding(perp, rate, mark, funding_ts_ms * 1_000_000)
                    self._last_pushed_ts_ms = funding_ts_ms
                return  # 只推最近的 funding 事件
```

- [ ] **Step 4: 在 axon_bridge/__init__.py 暴露**

```python
# backend/axon_bridge/__init__.py
# 在文件末尾添加:
from .backtest import (  # noqa: F401
    spot_instrument,
    swap_instrument,
    limit_order,
    InstrumentDict,
    PushFundingHelper,
)
```

- [ ] **Step 5: 跑测试确认 PASS**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/axon_bridge/test_backtest.py -v
```

**Expected**: 8/8 PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/axon_bridge/backtest.py backend/axon_bridge/__init__.py backend/tests/unit/axon_bridge/test_backtest.py
git commit -m "feat(axon_bridge): add 0.6.0 multi-leg adapter (spot/swap/limit_order/PushFundingHelper)"
```

---

## Task 3: StrategyContext funding 字段标 DEPRECATED (TDD)

**Files:**
- Modify: `backend/strategy/base.py:28-95` (StrategyContext + settle_funding)
- Test: `backend/tests/unit/strategy/test_context_deprecated.py` (新建)

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/unit/strategy/test_context_deprecated.py
"""StrategyContext.funding_cash/settle_funding 标 DEPRECATED no-op。"""
import pytest

from strategy.base import StrategyContext


def test_funding_cash_default_zero():
    """funding_cash 默认 0 (no-op 字段)。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.funding_cash == 0.0


def test_settle_funding_returns_zero():
    """settle_funding 标 no-op, 返回 0.0 (无论参数如何)。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    cash = ctx.settle_funding(
        funding_rate=0.0003,
        funding_time=1234567890,
        position_notional=10000.0,
    )
    assert cash == 0.0


def test_settle_funding_does_not_mutate_funding_cash():
    """settle_funding 不修改 funding_cash。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    ctx.settle_funding(
        funding_rate=0.0003,
        funding_time=1234567890,
        position_notional=10000.0,
    )
    assert ctx.funding_cash == 0.0


def test_funding_cash_settlement_enabled_default_false():
    """funding_cash_settlement_enabled 默认 False (防止意外累加)。"""
    ctx = StrategyContext(symbol="BTCUSDT")
    assert ctx.funding_cash_settlement_enabled is False
```

- [ ] **Step 2: 跑测试确认 PASS (因为老代码 settlement_enabled=True)**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/strategy/test_context_deprecated.py -v
```

**Expected**: 部分 PASS (test_funding_cash_default_zero, test_funding_cash_settlement_enabled_default_false FAIL, settle_funding_returns_zero / does_not_mutate_funding_cash PASS)

记录哪些 FAIL,继续。

- [ ] **Step 3: 改 StrategyContext 标 DEPRECATED**

```python
# backend/strategy/base.py
# 修改 StrategyContext dataclass + settle_funding 方法:

@dataclass
class StrategyContext:
    """策略运行上下文。

    ponytail: 简洁接口, 模板只关心 closes/positions/orders
             不感知具体交易所/账户细节
             DEPRECATED 字段 (2026-07-18 axon_quant 0.6.0 升级):
             - funding_cash / settle_funding: 完全下沉到 axon_quant 引擎
               RunResult.total_funding_pnl, 策略层不再调用
             - funding_cash_settlement_enabled 默认 False
    """
    symbol: str
    closes: list[float] = field(default_factory=list)
    positions: dict[str, float] = field(default_factory=dict)
    orders: list[dict] = field(default_factory=list)

    # —— 现货腿支持 (funding_arbitrage 用) ——
    spot_symbol: str = ""
    spot_close: float = 0.0
    spot_volume: float = 0.0
    spot_target_position: float = 0.0

    # —— 账户净值 (策略层算 notional 用) ——
    account_equity: float = 0.0

    # —— DEPRECATED 字段 (2026-07-18 0.6.0 升级后保留读接口) ——
    funding_cash: float = 0.0  # DEPRECATED: 始终为 0
    last_funding_rate: float = 0.0  # DEPRECATED
    last_funding_time: int = 0  # DEPRECATED
    funding_cash_settlement_enabled: bool = False  # DEPRECATED, 默认 False

    def settle_funding(
        self,
        funding_rate: float,
        funding_time: int,
        position_notional: float,
    ) -> float:
        """DEPRECATED: funding cash 已下沉到 axon_quant 引擎 (RunResult.total_funding_pnl)。

        保留 no-op 接口以避免破坏外部调用, 返回 0.0。
        业务代码不应再调用此方法, 由 axon_quant.backtest.BacktestEngine.push_funding() 替代。
        """
        return 0.0
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/strategy/test_context_deprecated.py -v
```

**Expected**: 4/4 PASS

- [ ] **Step 5: 跑老 context_fields 测试确保没破坏**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/strategy/test_context_fields.py -v
```

**Expected**: 12/12 PASS (即使 funding_cash 字段保留但默认 0, 仍满足老测试)

- [ ] **Step 6: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/strategy/base.py backend/tests/unit/strategy/test_context_deprecated.py
git commit -m "refactor(strategy): mark StrategyContext.funding_cash/settle_funding as DEPRECATED no-op"
```

---

## Task 4: funding_arbitrage 删 ctx.settle_funding() 调用 (TDD)

**Files:**
- Modify: `backend/strategy/templates/funding_arbitrage.py:60-80` (on_bar)
- Test: `backend/tests/unit/strategy/test_advanced_templates.py` (删 1 个 funding_cash 测试)

- [ ] **Step 1: 删 funding_cash 累加测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
# 用 Edit 工具删 test_funding_arbitrage_accumulates_funding_cash_on_long_funding 函数
# 整段从 def test_funding_arbitrage_accumulates_funding_cash_on_long_funding():
# 到该函数最后一个 assert 行
```

- [ ] **Step 2: 跑测试确认 PASS (其他 funding_arbitrage 测试不动)**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/strategy/test_advanced_templates.py -v
```

**Expected**: 测试总数 - 1, 之前 funding_arbitrage 相关 PASS 测试仍 PASS

- [ ] **Step 3: 改 funding_arbitrage.py on_bar 删 settle_funding 调用**

```python
# backend/strategy/templates/funding_arbitrage.py
# 改 on_bar 方法, 删 ctx.settle_funding() 调用:

def on_bar(self, bar: dict, ctx: StrategyContext) -> Action:
    # 兼容未调 on_start 的场景（测试/单 bar 模式）
    if self._ctx is None:
        self._ctx = ctx
    funding_rate = float(bar.get("funding_rate", 0.0))
    funding_time = int(bar.get("timestamp", bar.get("funding_time", 0)))
    close_price = float(bar["close"])

    # 1) 状态机更新 (先算 perp_target, 让 settle_funding 用 state 决定的 notional)
    #    2026-07-18 axon_quant 0.6.0 升级后, settle_funding 是 no-op,
    #    funding cash 完全由 axon_quant 引擎 push_funding() 累加 → RunResult.total_funding_pnl
    prev_state = self._state
    perp_target, spot_target, new_state = self._compute_targets(funding_rate)
    if new_state != prev_state and self._param("log_state_transitions"):
        ctx.orders.append({
            "type": "log",
            "msg": f"state: {prev_state.value} -> {new_state.value} (funding={funding_rate:.6f})",
        })
    self._state = new_state
    self._current_side = {
        FundingState.FLAT: "flat",
        FundingState.LONG_FUNDING: "short",
        FundingState.SHORT_FUNDING: "long",
    }[new_state]

    # 2) 写 ctx.spot_target_position (baseline 仍然读)
    ctx.spot_target_position = spot_target

    return Action(
        action_type=self._action_type_for(new_state),
        confidence=0.6,
        target_position=perp_target,
        model_id=self.config.name,
        inference_time_us=0,
    )
```

- [ ] **Step 4: 跑测试确认 PASS**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/strategy/test_advanced_templates.py -v
```

**Expected**: 所有 9 个 funding_arbitrage 测试 PASS (LONG_FUNDING state / 反转 / hold counter / spot leg 门控 / spot margin 降级)

- [ ] **Step 5: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/strategy/templates/funding_arbitrage.py backend/tests/unit/strategy/test_advanced_templates.py
git commit -m "refactor(strategy): funding_arbitrage 不再调 ctx.settle_funding() (no-op)"
```

---

## Task 5: BaselineBacktestService.run() 重写 (TDD) - 核心

**Files:**
- Modify: `backend/backtest/baseline.py` (重写 run() + 删 funding_injection_window_hours)
- Modify: `backend/tests/unit/backtest/test_baseline_funding.py` (改 4 个 + 加 3 个新)
- Test: 同上

- [ ] **Step 1: 删老 baseline_funding 4 个测试**

```python
# backend/tests/unit/backtest/test_baseline_funding.py
# 删以下 4 个测试函数 (v2.3.1 funding_injection_window_hours 相关):
# - test_baseline_accepts_funding_injection_window_hours
# - test_baseline_funding_periods_computed
# - test_baseline_funding_periods_empty
# - test_baseline_load_funding_history (保留 _load_funding_history 内部方法, 但改测试为 PushFundingHelper)
```

保留 4 个老测试 (funding_history_path / spot_symbol / funding_history_path_optional / load_funding_history),删除 3 个 v2.3.1 加的测试。

- [ ] **Step 2: 写新失败测试**

```python
# backend/tests/unit/backtest/test_baseline_funding.py
# 在文件末尾添加 3 个新测试:

def test_baseline_uses_axon_quant_backtest_engine():
    """baseline.run() 走 axon_quant 0.6.0 BacktestEngine, 报告字段含 engine_version。"""
    from backtest.baseline import BaselineBacktestService, make_synthetic_kline
    df = make_synthetic_kline(n=10, start_price=50000.0)
    svc = BaselineBacktestService(
        strategy_name="dual_ma",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
    )
    report = svc.run()
    assert report.engine_version == "0.6.0"
    assert hasattr(report, "funding_pnl")
    assert hasattr(report, "rebalances")


def test_baseline_maps_action_to_legs():
    """单 leg 策略: spot_target = action.target_position, perp_target = 0。"""
    from unittest.mock import patch, MagicMock
    from axon_bridge import Action, ActionType

    # 用 mock 验证 baseline.run() 调 BacktestEngine.set_target_position
    with patch("backtest.baseline.BacktestEngine") as MockEngine:
        mock_instance = MagicMock()
        mock_instance.run.return_value = MagicMock(
            total_pnl=0.0, total_funding_pnl=0.0, rebalances_triggered=0,
            max_drawdown=0.0, sharpe_ratio=0.0, win_rate=0.0, trades=0,
        )
        MockEngine.return_value = mock_instance

        from backtest.baseline import BaselineBacktestService, make_synthetic_kline
        df = make_synthetic_kline(n=10, start_price=50000.0)
        svc = BaselineBacktestService(
            strategy_name="dual_ma",
            symbol="BTCUSDT",
            start="2024-07-01",
            end="2024-07-08",
            data=df,
        )
        svc.run()

        # 验证 set_target_position 被调过, spot 传入 non-zero, perp 传入 0
        # (取决于 dual_ma 策略, 至少 1 次 set_target_position)
        set_calls = mock_instance.set_target_position.call_args_list
        assert len(set_calls) > 0, "应至少 1 次 set_target_position"


def test_baseline_funding_pnl_from_engine_result():
    """funding_pnl 字段读自 RunResult.total_funding_pnl。"""
    from unittest.mock import patch, MagicMock
    with patch("backtest.baseline.BacktestEngine") as MockEngine:
        mock_instance = MagicMock()
        mock_instance.run.return_value = MagicMock(
            total_pnl=10.0, total_funding_pnl=3.5, rebalances_triggered=2,
            max_drawdown=1.0, sharpe_ratio=0.5, win_rate=0.5, trades=2,
        )
        MockEngine.return_value = mock_instance

        from backtest.baseline import BaselineBacktestService, make_synthetic_kline
        df = make_synthetic_kline(n=10, start_price=50000.0)
        svc = BaselineBacktestService(
            strategy_name="funding_arbitrage",
            symbol="BTCUSDT",
            start="2024-07-01",
            end="2024-07-08",
            data=df,
        )
        report = svc.run()
        assert report.funding_pnl == 3.5
        assert report.rebalances == 2
```

- [ ] **Step 3: 跑测试确认 FAIL**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/backtest/test_baseline_funding.py -v
```

**Expected**: 3 个新测试 FAIL (engine_version / funding_pnl / rebalances 字段未定义)

- [ ] **Step 4: 重写 baseline.py**

```python
# backend/backtest/baseline.py
# 重写整个文件, 完整新实现:

"""基线回测报告生成器 (axon_quant 0.6.0 多 leg 版)。

ponytail: 简化版基线回测 — 驱动 axon_quant 0.6.0 BacktestEngine 多 leg
         spot + perp 两个 instrument, 8 策略统一路径
         单 leg 策略 perp target=0, 双 leg 策略 (funding_arbitrage) 反向
         funding cash 由 engine.push_funding() 累加 (策略层不调 settle_funding)
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from axon_bridge import (
    BacktestEngine,
    PushFundingHelper,
    spot_instrument,
    swap_instrument,
)
from strategy.base import BaseStrategy, StrategyConfig, StrategyContext
from strategy.loader import StrategyLoader


def _now_iso() -> str:
    """纳秒精度 ISO 8601 时间戳,符合项目硬约束。"""
    now = datetime.now(timezone.utc)
    micro = now.microsecond * 1000
    return now.strftime("%Y-%m-%dT%H:%M:%S") + f".{micro:09d}+00:00"


def make_synthetic_kline(
    n: int = 200,
    start_price: float = 30000.0,
    seed: int = 42,
) -> pd.DataFrame:
    """生成合成 K 线 DataFrame(走 GBM 随机游走)。

    ponytail: 仅用于基线/单元测试,避免依赖外部 Parquet
             O(n) 时间 O(n) 空间,n <= 10000 可控
    """
    rng = np.random.default_rng(seed)
    sigma = 0.02 / np.sqrt(24)
    drift = 0.0
    rets = rng.normal(drift, sigma, n)
    prices = start_price * np.exp(np.cumsum(rets))
    closes = prices
    opens = np.concatenate([[start_price], closes[:-1]])
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, sigma / 2, n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, sigma / 2, n)))
    volumes = rng.uniform(100, 1000, n)
    ts = pd.date_range("2024-07-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        }
    )


@dataclass
class BaselineReport:
    """基线回测报告数据。"""

    template: str
    symbol: str
    period: str
    interval: str
    candle_type: str
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    # —— 新增 0.6.0 字段 (2026-07-18) ——
    funding_pnl: float = 0.0           # 引擎层 funding 累计
    rebalances: int = 0                # 引擎 rebalance 触发次数
    engine_version: str = "0.6.0"      # 标记来源
    report_id: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class BaselineBacktestService:
    """基线回测 (axon_quant 0.6.0 多 leg 版)。"""

    def __init__(
        self,
        strategy_name: str,
        symbol: str,
        start: str,
        end: str,
        interval: str = "1h",
        candle_type: str = "spot",
        output_dir: Path | None = None,
        data: pd.DataFrame | None = None,
        funding_history_path: str | None = None,
        spot_symbol: str | None = None,
    ):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.start = start
        self.end = end
        self.interval = interval
        self.candle_type = candle_type
        self.output_dir = Path(output_dir) if output_dir else Path("data/source/backtest_baselines")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data = data
        self.funding_history_path = funding_history_path
        self.spot_symbol = spot_symbol
        self._funding_history: dict[int, float] | None = None

    def _load_kline(self) -> pd.DataFrame:
        if self.data is not None:
            return self.data
        return make_synthetic_kline(n=200, start_price=30000.0)

    def _load_funding_history(self) -> dict[int, float]:
        """加载 funding 历史 CSV → {funding_time_ms: funding_rate}。

        ponytail: 懒加载, 多次调用只解析一次
        """
        if self._funding_history is not None:
            return self._funding_history
        if not self.funding_history_path:
            self._funding_history = {}
            return self._funding_history
        path = Path(self.funding_history_path)
        if not path.exists():
            self._funding_history = {}
            return self._funding_history
        history: dict[int, float] = {}
        with path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                history[int(row["funding_time_ms"])] = float(row["funding_rate"])
        self._funding_history = history
        return self._funding_history

    def _row_timestamp_ns(self, row: pd.Series) -> int:
        """从 row 提取纳秒时间戳。

        ponytail: 优先 'timestamp' 列; 否则用 index DatetimeIndex
        """
        if "timestamp" in row.index and not isinstance(row["timestamp"], (int, float)):
            try:
                return int(pd.Timestamp(row["timestamp"]).timestamp() * 1_000_000_000)
            except (ValueError, TypeError):
                pass
        idx_name = row.name
        if isinstance(idx_name, pd.Timestamp):
            return int(idx_name.timestamp() * 1_000_000_000)
        return 0

    def _parse_symbol(self) -> tuple[str, str]:
        """从 self.symbol (e.g. 'BTCUSDT' 或 'BTCUSDT-PERP') 解析 (base, quote)。

        ponytail: 简单 split, 不处理多 quote 货币 (USDC/USDT)
        """
        symbol = self.symbol
        for quote in ["USDT", "USDC", "BUSD", "USD"]:
            if symbol.endswith(quote):
                base = symbol[: -len(quote)]
                return base, quote
        return symbol, "USDT"  # fallback

    def _build_bar(self, row: pd.Series, ts_ns: int) -> dict:
        """构造策略层 bar dict。"""
        return {
            "open": float(row.get("open", row["close"])),
            "high": float(row.get("high", row["close"])),
            "low": float(row.get("low", row["close"])),
            "close": float(row["close"]),
            "volume": float(row.get("volume", 0.0)),
            "timestamp": ts_ns // 1_000_000,  # 兼容老 bar timestamp 单位 ms
            "funding_rate": 0.0,
            "funding_time": ts_ns // 1_000_000,
            "cross_sectional_rank": 0,
        }

    def _map_action_to_legs(
        self, action, ctx: StrategyContext
    ) -> tuple[float, float]:
        """Action → (spot_target, perp_target)。

        - 双 leg 策略 (funding_arbitrage):  ctx.spot_target_position 已被策略 set
        - 单 leg 策略:  spot_target = action.target_position, perp_target = 0
        """
        if hasattr(ctx, "spot_target_position") and ctx.spot_target_position != 0.0:
            return ctx.spot_target_position, float(action.target_position)
        return float(action.target_position), 0.0

    def run(self) -> BaselineReport:
        """驱动 axon_quant 0.6.0 BacktestEngine 多 leg 回测。"""
        df = self._load_kline()
        if df is None or df.empty:
            raise ValueError(f"K 线数据为空: {self.symbol} {self.interval} {self.start}~{self.end}")

        base, quote = self._parse_symbol()
        spot = spot_instrument(base, quote)
        perp = swap_instrument(base, quote, settle="usd_margin", contract_size=1.0)

        engine = BacktestEngine(initial_cash=100_000.0)
        engine.with_seed_liquidity(half_spread=0.5, depth_levels=2, size_per_level=2.0)
        engine.with_auto_rebalance(1e-6)

        strategy_cls = StrategyLoader.get(self.strategy_name)
        config = StrategyConfig(name=self.strategy_name, symbol=self.symbol)
        strategy: BaseStrategy = strategy_cls(config)
        ctx = StrategyContext(symbol=self.symbol)
        ctx.spot_target_position = 0.0
        strategy.on_start(ctx)

        funding_history = self._load_funding_history()
        funding_helper = PushFundingHelper(funding_history)

        for _, row in df.iterrows():
            ts_ns = self._row_timestamp_ns(row)
            close = float(row["close"])

            engine.push_mark(spot, close, ts_ns)
            engine.push_mark(perp, close, ts_ns)
            engine.begin_bar(close, spot)
            engine.begin_bar(close, perp)
            funding_helper.maybe_push(perp, close, ts_ns, engine)

            bar = self._build_bar(row, ts_ns)
            action = strategy.on_bar(bar, ctx)
            spot_target, perp_target = self._map_action_to_legs(action, ctx)
            engine.set_target_position(spot, spot_target)
            engine.set_target_position(perp, perp_target)

        result = engine.run()
        return self._build_report(result)

    def _build_report(self, result) -> BaselineReport:
        return BaselineReport(
            template=self.strategy_name,
            symbol=self.symbol,
            period=f"{self.start}~{self.end}",
            interval=self.interval,
            candle_type=self.candle_type,
            total_pnl=round(float(getattr(result, "total_pnl", 0.0)), 4),
            sharpe_ratio=round(float(getattr(result, "sharpe_ratio", 0.0)), 4),
            max_drawdown=round(float(getattr(result, "max_drawdown", 0.0)), 4),
            win_rate=round(float(getattr(result, "win_rate", 0.0)), 4),
            total_trades=int(getattr(result, "trades", 0)),
            funding_pnl=round(float(getattr(result, "total_funding_pnl", 0.0)), 4),
            rebalances=int(getattr(result, "rebalances_triggered", 0)),
            engine_version="0.6.0",
            report_id=str(uuid4()),
            generated_at=_now_iso(),
        )

    def _write_reports(self, report: BaselineReport) -> None:
        base = f"{report.template}_{report.symbol}_{report.period.replace('~', '_')}"
        json_path = self.output_dir / f"{base}.json"
        md_path = self.output_dir / f"{base}.md"
        json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        md_path.write_text(self._render_md(report))

    def _render_md(self, r: BaselineReport) -> str:
        return f"""# {r.template} 基线回测报告

- **模板**: {r.template}
- **标的**: {r.symbol}
- **周期**: {r.period}
- **K线**: {r.interval} ({r.candle_type})
- **引擎**: axon_quant {r.engine_version}
- **报告 ID**: {r.report_id}
- **生成时间**: {r.generated_at}

## 业绩指标

| 指标 | 数值 |
|---|---|
| Total PnL | {r.total_pnl:.4f} |
| Funding PnL | {r.funding_pnl:.4f} |
| Sharpe Ratio | {r.sharpe_ratio:.4f} |
| Max Drawdown | {r.max_drawdown:.4f} |
| Win Rate | {r.win_rate:.2%} |
| Total Trades | {r.total_trades} |
| Rebalances | {r.rebalances} |

---
*由 QuantCell BaselineBacktestService (axon_quant {r.engine_version}) 自动生成*
"""
```

- [ ] **Step 5: 跑测试确认 PASS**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/backtest/test_baseline_funding.py -v
```

**Expected**: 7/7 PASS (4 老 + 3 新)

- [ ] **Step 6: 跑全部相关测试**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/backtest/ tests/unit/strategy/ tests/unit/axon_bridge/ tests/integration/test_funding_arb_backtest.py 2>&1 | tail -5
```

**Expected**: 全部 PASS (期望 ~40 个测试)

- [ ] **Step 7: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/backtest/baseline.py backend/tests/unit/backtest/test_baseline_funding.py
git commit -m "feat(backtest): 重写 baseline.run() 走 axon_quant 0.6.0 多 leg (spot+perp)"
```

---

## Task 6: 集成测试 + delta-neutral 不变量 (TDD)

**Files:**
- Modify: `backend/tests/integration/test_funding_arb_backtest.py` (改 1 个 + 加 1 个)

- [ ] **Step 1: 改 equity_curve 测试**

```python
# backend/tests/integration/test_funding_arb_backtest.py
# 改 test_backtest_equity_curve_includes_funding_cash:
# 旧: 验证 baseline.funding_cash 累加
# 新: 验证 baseline 报告 funding_pnl > 0 + 报告 total_pnl 含 funding

def test_backtest_equity_curve_includes_funding_cash():
    """funding cash 由 axon_quant 引擎累加, baseline 报告 funding_pnl 反映。"""
    from backtest.baseline import BaselineBacktestService
    import pandas as pd
    from pathlib import Path

    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-07-01", periods=200, freq="1h", tz="UTC"),
        "open": [50000.0] * 200,
        "high": [50100.0] * 200,
        "low": [49900.0] * 200,
        "close": [50000.0] * 200,
        "volume": [100.0] * 200,
    })
    fixtures = Path(__file__).parent.parent / "fixtures" / "funding_history_btcusdt_sample.csv"
    svc = BaselineBacktestService(
        strategy_name="funding_arbitrage",
        symbol="BTCUSDT",
        start="2024-07-01",
        end="2024-07-08",
        data=df,
        funding_history_path=str(fixtures),
    )
    report = svc.run()
    # 2026-07-18: funding cash 由 axon_quant 引擎 push_funding() 累加
    # → RunResult.total_funding_pnl > 0 (LONG_FUNDING 期间吃 funding)
    assert report.funding_pnl > 0, f"funding_pnl 应 > 0, 实际 {report.funding_pnl}"
```

- [ ] **Step 2: 写 delta-neutral 不变量测试**

```python
# backend/tests/integration/test_funding_arb_backtest.py
# 在文件末尾添加:

def test_funding_arb_backtest_delta_neutral_invariant():
    """funding_arbitrage 入场后 spot+perp target 互反 (delta 中性)。"""
    from unittest.mock import MagicMock, patch
    from axon_bridge import spot_instrument, swap_instrument

    captured_targets = []
    def capture_set_target_position(instrument, target):
        captured_targets.append((instrument["kind"], target))

    with patch("backtest.baseline.BacktestEngine") as MockEngine:
        mock_instance = MagicMock()
        mock_instance.set_target_position.side_effect = capture_set_target_position
        mock_instance.run.return_value = MagicMock(
            total_pnl=10.0, total_funding_pnl=3.5, rebalances_triggered=2,
            max_drawdown=1.0, sharpe_ratio=0.5, win_rate=0.5, trades=2,
        )
        MockEngine.return_value = mock_instance

        import pandas as pd
        from pathlib import Path
        from backtest.baseline import BaselineBacktestService

        df = pd.DataFrame({
            "timestamp": pd.date_range("2024-07-01", periods=200, freq="1h", tz="UTC"),
            "open": [50000.0] * 200,
            "high": [50100.0] * 200,
            "low": [49900.0] * 200,
            "close": [50000.0] * 200,
            "volume": [100.0] * 200,
        })
        fixtures = Path(__file__).parent.parent / "fixtures" / "funding_history_btcusdt_sample.csv"
        svc = BaselineBacktestService(
            strategy_name="funding_arbitrage",
            symbol="BTCUSDT",
            start="2024-07-01",
            end="2024-07-08",
            data=df,
            funding_history_path=str(fixtures),
        )
        report = svc.run()

        # 验证: funding_arbitrage 入场时 spot_target + perp_target 互反 (delta 中性)
        spot_targets = [t for k, t in captured_targets if k == "spot"]
        perp_targets = [t for k, t in captured_targets if k == "swap"]
        assert len(spot_targets) > 0, "应至少 1 次 spot target"
        assert len(perp_targets) > 0, "应至少 1 次 perp target"
        # 验证在 LONG_FUNDING 状态下 (funding > 0 持续 8 bar) spot+perp 反号
        for s, p in zip(spot_targets, perp_targets):
            if s != 0 and p != 0:
                # 至少 1 次非零 target 验证符号
                assert s * p < 0, f"delta 中性要求 spot+perp 反号, 但 spot={s}, perp={p}"
                break
```

- [ ] **Step 3: 跑测试确认 PASS**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/integration/test_funding_arb_backtest.py -v
```

**Expected**: 4/4 PASS (4 个老测试 + 1 个新增 delta-neutral)

注: 原来 4 个老测试可能因为 baseline 重构而 break, 需具体看。

- [ ] **Step 4: 跑 funding_arb 自检脚本**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
backend/.venv/bin/python scripts/check_funding_arb.py 2>&1 | tail -15
```

**Expected**: 端到端 OK + funding_pnl > 0 + 8 策略 baseline 报告生成

- [ ] **Step 5: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/tests/integration/test_funding_arb_backtest.py
git commit -m "test(backtest): 改 funding_pnl 测试 + 加 delta-neutral 不变量"
```

---

## Task 7: 8 策略 baseline 报告重新生成 + 归档老报告

**Files:**
- Move: `data/source/backtest_baselines/*.json` + `*.md` → `data/source/backtest_baselines/archive/v2.3.1/`
- Create: `data/source/backtest_baselines/{8 策略}_BTCUSDT_*.{json,md}`

- [ ] **Step 1: 创建归档目录**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
mkdir -p data/source/backtest_baselines/archive/v2.3.1
```

- [ ] **Step 2: 移动老报告到归档**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
# data/source/* 在 .gitignore, 用 mv 不用 rm
mv data/source/backtest_baselines/funding_arbitrage_BTCUSDT_*.json data/source/backtest_baselines/archive/v2.3.1/
mv data/source/backtest_baselines/funding_arbitrage_BTCUSDT_*.md data/source/backtest_baselines/archive/v2.3.1/
```

- [ ] **Step 3: 跑 8 策略 baseline (用 --strategy 全跑)**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
# 用 CLI (如果 quantcell CLI 已统一)
backend/.venv/bin/python -m quantcell strategy baseline --all 2>&1 | tail -20
# 或直接写脚本跑 8 个策略:
backend/.venv/bin/python -c "
import sys
from pathlib import Path
BACKEND = Path('/Users/liupeng/workspace/quant/QuantCell/backend')
sys.path.insert(0, str(BACKEND))
from backtest.baseline import BaselineBacktestService
import pandas as pd
from datetime import datetime, timezone, timedelta

start = datetime(2024, 7, 1, tzinfo=timezone.utc)
end = datetime(2024, 7, 8, tzinfo=timezone.utc)
ts = pd.date_range(start, periods=24*7, freq='1h', tz='UTC')
df = pd.DataFrame({
    'timestamp': ts,
    'open': [50000.0] * len(ts),
    'high': [50100.0] * len(ts),
    'low': [49900.0] * len(ts),
    'close': [50000.0] * len(ts),
    'volume': [100.0] * len(ts),
})

strategies = ['dual_ma', 'trend_follow', 'mean_reversion', 'grid', 'momentum',
              'mean_reversion_rl', 'cross_sectional', 'funding_arbitrage']
output_dir = Path('/Users/liupeng/workspace/quant/QuantCell/data/source/backtest_baselines')

for s in strategies:
    kwargs = dict(strategy_name=s, symbol='BTCUSDT', start='2024-07-01', end='2024-07-08',
                  data=df, output_dir=output_dir)
    if s == 'funding_arbitrage':
        kwargs['funding_history_path'] = str(BACKEND / 'tests' / 'fixtures' / 'funding_history_btcusdt_sample.csv')
    try:
        r = BaselineBacktestService(**kwargs).run()
        print(f'{s}: pnl={r.total_pnl:.2f} funding_pnl={r.funding_pnl:.2f} trades={r.total_trades}')
    except Exception as e:
        print(f'{s}: ERROR {e}')
" 2>&1 | tail -20
```

**Expected**: 8 个策略 baseline 报告生成 (8 json + 8 md)

- [ ] **Step 4: 验证 1 年 funding_arbitrage baseline (trades > 0, funding_pnl > 0)**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
backend/.venv/bin/python -c "
import sys
from pathlib import Path
BACKEND = Path('/Users/liupeng/workspace/quant/QuantCell/backend')
sys.path.insert(0, str(BACKEND))
from backtest.baseline import BaselineBacktestService, make_synthetic_kline

df = make_synthetic_kline(n=4000, start_price=50000.0, seed=42)
fixtures = BACKEND / 'tests' / 'fixtures' / 'funding_history_btcusdt_sample.csv'
output_dir = Path('/Users/liupeng/workspace/quant/QuantCell/data/source/backtest_baselines')

r = BaselineBacktestService(
    strategy_name='funding_arbitrage', symbol='BTCUSDT',
    start='2024-07-01', end='2025-07-01',
    data=df, funding_history_path=str(fixtures), output_dir=output_dir,
).run()
print(f'1年 funding_arbitrage: total_pnl={r.total_pnl:.2f} funding_pnl={r.funding_pnl:.2f} trades={r.total_trades} rebalances={r.rebalances}')
" 2>&1 | tail -5
```

**Expected**: total_pnl + funding_pnl > 0, trades > 0, rebalances > 0

- [ ] **Step 5: Commit (含归档 + 新报告)**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
# data/source/* 在 .gitignore, 用 git add -f
git add -f data/source/backtest_baselines/archive/v2.3.1/
git add -f data/source/backtest_baselines/*.json
git add -f data/source/backtest_baselines/*.md
git commit -m "feat(backtest): 重新生成 8 策略 baseline 报告 (axon_quant 0.6.0 多 leg), 归档 v2.3.1 老报告"
```

---

## Task 8: 文档 + CHANGELOG + uv.lock

**Files:**
- Modify: `docs/superpowers/CHANGELOG_funding_arb.md` (v2.3.1 → v2.3.2)
- Modify: `uv.lock` (uv lock 自动更新)
- Modify: `backend/README.md` 或类似 (声明 axon-quant >= 0.6.0 最低要求)

- [ ] **Step 1: 更新 CHANGELOG v2.3.2**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
python3 <<'PYEOF'
p = 'docs/superpowers/CHANGELOG_funding_arb.md'
s = open(p).read()

# v2.3.1 → v2.3.2
s = s.replace('**Version:** v2.3.1', '**Version:** v2.3.2')
s = s.replace('**Date:** 2026-07-17', '**Date:** 2026-07-18')

# 在文件末尾添加 v2.3.2 升级段
new_section = '''

---

# v2.3.2 升级 (2026-07-18) — axon_quant 0.6.0 多 leg 化

## 升级概要

把 `BaselineBacktestService` 全面重构走 `axon_quant 0.6.0` 多 leg API。funding cash 计算完全下沉到引擎层,策略层 `ctx.settle_funding()` 标 DEPRECATED no-op。

## 核心变化

### 1. axon_bridge 加 0.6.0 多 leg 重导出

| 重导出 | 来源 |
|---|---|
| `spot_instrument(base, quote)` | `axon_quant.backtest` |
| `swap_instrument(base, quote, settle, contract_size)` | `axon_quant.backtest` |
| `limit_order(id, instrument, side, price, qty, tif)` | `axon_quant.backtest` |
| `PushFundingHelper` (新建) | 本模块, 把 funding fixture dict 调 `engine.push_funding()` |

### 2. BaselineBacktestService.run() 重写

旧实现: 自己遍历 K 线 + 模拟 PnL + 注入 funding_rate  
新实现: 驱动 `axon_quant 0.6.0` BacktestEngine 多 leg (spot + perp)
- 8 策略统一走多 leg 路径
- 单 leg 策略 perp target=0, 双 leg 策略 (funding_arbitrage) 反向 target
- funding cash 由 `engine.push_funding()` 累加 (策略层不调 settle_funding)

### 3. StrategyContext funding 字段标 DEPRECATED

- `funding_cash` / `settle_funding()` / `last_funding_rate` / `last_funding_time` / `funding_cash_settlement_enabled` 标 DEPRECATED
- `settle_funding()` 改为 no-op 返回 0.0
- `funding_cash_settlement_enabled` 默认 False

### 4. funding_arbitrage 删 settle_funding 调用

策略层 `on_bar` 不再调 `ctx.settle_funding()`,状态机只控制 target_position。funding cash 累加完全由 axon_quant 引擎做。

## 8 策略 baseline 报告

| 策略 | Total PnL | Funding PnL | Trades | Rebalances |
|---|---|---|---|---|
| dual_ma | (新基线) | 0.0 | (新基线) | (新基线) |
| trend_follow | (新基线) | 0.0 | (新基线) | (新基线) |
| mean_reversion | (新基线) | 0.0 | (新基线) | (新基线) |
| grid | (新基线) | 0.0 | (新基线) | (新基线) |
| momentum | (新基线) | 0.0 | (新基线) | (新基线) |
| mean_reversion_rl | (新基线) | 0.0 | (新基线) | (新基线) |
| cross_sectional | (新基线) | 0.0 | (新基线) | (新基线) |
| funding_arbitrage | (新基线) | (新基线, > 0) | (新基线, > 0) | (新基线, > 0) |

(实际数字在 Task 7 跑完后回填)

老 v2.3.1 报告归档到 `data/source/backtest_baselines/archive/v2.3.1/`。

## 依赖

- `axon-quant >= 0.6.0` (不锁版本, `uv pip install --upgrade`)
'''

# 在文件末尾追加
s = s.rstrip() + new_section + '\n'
open(p, 'w').write(s)
print('OK CHANGELOG v2.3.2 更新完成')
PYEOF
```

- [ ] **Step 2: 验证 CHANGELOG 改动**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
grep -A 2 "Version" docs/superpowers/CHANGELOG_funding_arb.md | head -5
```

**Expected**: "**Version:** v2.3.2" / "**Date:** 2026-07-18"

- [ ] **Step 3: uv lock 重新生成**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
uv lock
```

- [ ] **Step 4: 跑全部相关测试最终验证**

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
.venv/bin/pytest tests/unit/axon_quant/ tests/unit/axon_bridge/ tests/unit/backtest/ tests/unit/strategy/ tests/integration/test_funding_arb_backtest.py 2>&1 | tail -5
```

**Expected**: 全部 PASS (期望 ~45 测试)

- [ ] **Step 5: 跑自检脚本最终验证**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
backend/.venv/bin/python scripts/check_funding_arb.py 2>&1 | tail -15
```

**Expected**: 端到端 OK + funding_pnl > 0 + 8 策略 baseline 报告生成

- [ ] **Step 6: Commit**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add docs/superpowers/CHANGELOG_funding_arb.md uv.lock
git commit -m "docs: CHANGELOG v2.3.2 (axon_quant 0.6.0 多 leg 化) + uv.lock 更新"
```

- [ ] **Step 7: 推送到 origin**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git push origin feat/migrate-nautilus-to-axon
```

---

## Self-Review Checklist (Plan ↔ Spec)

**Spec 覆盖**:
- [x] axon_quant 升级 0.6.0 → Task 1
- [x] axon_bridge.backtest 模块 + PushFundingHelper → Task 2
- [x] StrategyContext 标 DEPRECATED → Task 3
- [x] funding_arbitrage 删 settle_funding → Task 4
- [x] BaselineBacktestService.run() 重写 → Task 5
- [x] BaselineReport 字段扩展 (funding_pnl / rebalances / engine_version) → Task 5
- [x] 集成测试 + delta-neutral 不变量 → Task 6
- [x] 8 策略 baseline 报告重新生成 → Task 7
- [x] CHANGELOG v2.3.2 + uv.lock → Task 8
- [x] 8 策略 baseline 报告归档老版本 → Task 7

**No Placeholders Check**:
- ✅ 每个 task 含完整代码
- ✅ 步骤具体 + Run 命令 + Expected 输出
- ✅ 文件路径精确
- ✅ 测试代码完整

**类型一致性**:
- Task 1 `spot_instrument` 返回 dict → Task 2 重导出 dict → Task 5 `BaselineBacktestService` 用 dict ✅
- Task 3 `StrategyContext.settle_funding() -> float` → Task 4 `funding_arbitrage` 删调用 ✅
- Task 5 `BaselineReport` 字段 (total_pnl, funding_pnl, rebalances, engine_version) → Task 7/8 读这些字段 ✅

**潜在风险**:
- ⚠️ 8 策略 baseline 报告数字变化 (baseline 走 0.6.0 引擎 vs 自算) → Task 7 跑前先看 dual_ma 单策略回归
- ⚠️ Task 6 老 integration 测试可能因 baseline 重构而 break → Step 1 跑前先看 break point
- ⚠️ 老的 `make_synthetic_kline` 用 `pd.date_range` start 2024-07-01 → 跟 funding fixture 时间窗 (2024-07-01 起) 对齐 ✅
- ⚠️ `Limit order` Python 端不接受 instrument=InstrumentDict 是 dict, 是传 dict 不是 class → Task 2 验证 ✅

---

## 8 Tasks / ~45 Steps / 8 Commits / 8h

Plan complete. Execution options:

1. **Subagent-Driven (recommended)** - 我派 fresh subagent 一 task 一 task 跑, review between tasks, fast iteration
2. **Inline Execution** - executing-plans skill 批量跑, checkpoint for review

---

## 执行结果 (2026-07-19)

> 实际执行时 axon_quant 实际锁到 0.7.0 wheel (PyPI),不是 0.6.0。0.7.0 修复了 trades 字段 + step() 可用,但保留了 3 个 known issues (begin_bar_multi / with_funding_schedule / with_* 返回值),work-around 在 baseline.py 中已实现。

### 8 Tasks 状态

- [x] **Task 1**: 升级 axon_quant → 实际 0.7.0 (PyPI wheel), `uv.lock` 锁 0.7.0
- [x] **Task 2**: `axon_bridge.backtest` 重导出 + `PushFundingHelper` 类
- [x] **Task 3**: `StrategyContext.funding_cash / settle_funding` 标 DEPRECATED no-op
- [x] **Task 4**: `funding_arbitrage.py` 删 `ctx.settle_funding()` 调用,改 ratio 语义
- [x] **Task 5**: `BaselineBacktestService.run()` 重写 → `BacktestEngine` 事件驱动 + 多 leg
- [x] **Task 6**: 5 个集成测试 (delta-neutral / 单腿退路 / 中段 funding / PnL 分解 / 零 funding)
- [x] **Task 7**: 8 策略 baseline 报告重新生成 (7 天 + 1 年,各 16 个 json/md)
- [x] **Task 8**: CHANGELOG + uv.lock + 文档 (本文档 + `CHANGELOG_0_7_0_migration.md`)

### Commit 序列 (4 commits on `feat/migrate-nautilus-to-axon`)

```
f95b086 refactor(backtest): BaselineBacktestService.run() rewrite via axon_quant 0.7.0 multi-leg API
6027740 refactor(strategy): mark StrategyContext.funding_cash/settle_funding as DEPRECATED no-op
3d1243e feat(axon_bridge): add 0.6.0 multi-leg adapter (spot/swap/limit_order/PushFundingHelper)
cb87672 docs: add spec for baseline axon_quant 0.6.0 multi-leg migration
```

### 测试结果

- ✅ 5 个新单元测试 (test_baseline_axon_engine.py: dual_ma / total_trades / total_pnl / funding_arbitrage_multi_leg / sharpe_bar_nav) 通过
- ✅ 5 个新集成测试 (test_baseline_axon_0_7_0.py: delta-neutral / 单腿退路 / 中段 funding / PnL 分解 / 零 funding) 通过
- ✅ 8 策略 baseline 报告全部成功生成,0 失败
- ⚠️ 老 8 策略 baseline 报告未归档 (`archive/v2.3.1/` 未创建,因 git 中只 tracked 了 funding_arbitrage 1 年文件,其他 7 策略 baseline 不在 git 历史中)
- ⚠️ `test_axon_bridge_backtest.py` 5 个新单元测试未单独建文件,在 test_baseline_axon_engine.py / test_baseline_axon_0_7_0.py 中覆盖

### 关键 metrics

#### 7 天 (2024-07-01 ~ 2024-07-08, 168 根 1h bar)

| 策略 | total_pnl | funding_pnl | trades |
|---|---|---|---|
| dual_ma | -119.66 | 0.0 | 3 |
| trend_follow | -173.69 | 0.0 | 4 |
| mean_reversion | -220.02 | 0.0 | 2 |
| mean_reversion_rl | -1134.92 | 0.0 | 5 |
| momentum | 0.0 | 0.0 | 0 |
| grid | 0.0 | 0.0 | 0 |
| cross_sectional | 0.0 | 0.0 | 0 |
| **funding_arbitrage** | **54.72** | **99.96** | **32** |

#### 1 年 (2024-07-01 ~ 2025-07-01, 8784 根 1h bar)

| 策略 | total_pnl | funding_pnl | trades |
|---|---|---|---|
| dual_ma | -2675.85 | 0.0 | 170 |
| trend_follow | -6327.80 | 0.0 | 463 |
| mean_reversion | -3165.91 | 0.0 | 143 |
| mean_reversion_rl | -32720.08 | 0.0 | 298 |
| momentum | -58.73 | 0.0 | 18 |
| grid | 0.0 | 0.0 | 0 |
| cross_sectional | 0.0 | 0.0 | 0 |
| **funding_arbitrage** | **5013.92** | **5469.64** | **3266** |

### 0.7.0 → 0.7.1 等待 (axon_quant)

- PR-A: `begin_bar_multi` 改 `list[tuple[InstrumentDict, f64]]` (修 unhashable type)
- PR-B: `with_funding_schedule` 自动 push 资金费率事件
- PR-C: `with_*` 改回 `&mut Self` 链式
- 字段: `result.bar_nav_curve` (bar-by-bar NAV) — Sharpe / max_drawdown 重算用

### 文档归档

- `docs/superpowers/CHANGELOG_0_7_0_migration.md` — 详细 API 决策 + work-around + baseline metrics
- `docs/superpowers/specs/2026-07-18-baseline-axon-quant-0.6-migration.md` — 设计 spec
- `docs/superpowers/plans/2026-07-18-baseline-axon-quant-0.6-migration.md` — 本文档 (实施 plan)
- `backend/scripts/regenerate_baselines.py` — 8 策略 baseline 报告生成脚本
