# axon-quant 深度集成到 QuantCell 实现计划

&gt; **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 axon-quant 0.10.0 完整深度集成到 QuantCell 的回测、交易、策略、服务各层，消除冗余代码，统一使用 axon_quant 原生 API。

**Architecture:** 遵循 YAGNI 原则，最小改动原则：1) 优化 BacktestLoop 使用 axon_quant 原生 set_target_position + with_auto_rebalance API；2) 统一策略基类签名；3) 简化 TradingEngine 调用链；4) 修复测试导入问题；5) 检查并优化 services 层集成。

**Tech Stack:** Python 3.14, axon-quant>=0.10.0, FastAPI, pandas, pytest

---

## 文件变更概览

| 文件 | 操作 | 职责 |
|------|------|------|
| `backtest/backtest_loop.py` | 修改 | 优化回测循环使用原生 API，添加 with_seed |
| `strategy/base.py` | 修改 | 统一策略基类，兼容 ctx 参数 |
| `backtest/strategies/` | 检查 | 确认适配新策略接口 |
| `engine/trading_engine.py` | 修改 | 简化直接使用 axon API |
| `tests/unit/collector/services/test_archive_service.py` | 修复 | 修复导入错误 |
| `services/` | 检查优化 | 确保各服务正确使用 axon_bridge |

---

### Task 1: 修复测试导入错误

**Files:**
- Modify: `tests/unit/collector/services/test_archive_service.py`

- [ ] **Step 1: 查看并修复导入错误**

先检查问题文件的导入语句：

```bash
cd /Users/liupeng/workspace/quant/QuantCell/backend
head -30 tests/unit/collector/services/test_archive_service.py
```

- [ ] **Step 2: 修复导入路径**

问题是导入路径错误。将错误的相对导入改为正确的绝对导入：

```python
# 错误的导入类似:
# from services.test_archive_service import ...
# 应该改为:
from collector.services import archive_service
```

- [ ] **Step 3: 验证修复**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/collector/services/test_archive_service.py -v --tb=short`
Expected: 收集测试成功，不再有 ImportError

---

### Task 2: 优化 BacktestLoop 使用 axon_quant 原生 API

**Files:**
- Modify: `backtest/backtest_loop.py`
- Test: `tests/unit/backtest/test_baseline_axon_engine.py`

- [ ] **Step 1: 查看当前 backtest_loop.py 的订单推送方式**

当前代码使用 `engine.push_event({"type": "order_submitted", ...})` 手动推送订单，axon_quant 0.10.0 提供了更原生的 API。

- [ ] **Step 2: 优化 BacktestLoop，使用 set_target_position + with_auto_rebalance + with_seed**

参考 baseline.py 中已经验证正确的模式，修改 `backtest/backtest_loop.py`：

```python
# 在 __init__ 后添加引擎配置链式调用
engine = _AxonBacktestEngine(initial_cash=self._initial_cash)
engine = engine.with_seed(42)  # 添加可复现性
engine = engine.with_seed_liquidity(
    half_spread=_DEFAULT_HALF_SPREAD_RATIO,
    depth_levels=_DEFAULT_DEPTH_LEVELS,
    size_per_level=_DEFAULT_SIZE_PER_LEVEL,
)
engine = engine.with_auto_rebalance(threshold=0.001)  # 启用自动调仓

if effective_force_liquidate:
    engine = engine.with_force_liquidate(True)

# ... 遍历 bar 时 ...
# 旧代码: push_event order_submitted
# 新代码: 直接 set_target_position
from axon_bridge.backtest import spot_instrument
instrument = spot_instrument(symbol.replace("USDT", ""), "USDT")
engine.set_target_position(instrument, action.target_position)
# 在每根 bar 结束时 rebalance 和 step
engine.rebalance_to_target()
while engine.pending_events &gt; 0:
    engine.step()
```

关键改动点：
1. 添加 `.with_seed(42)` 确保可复现性
2. 添加 `.with_auto_rebalance(threshold=0.001)`
3. 策略返回 Action 后，使用 `set_target_position` 代替手动 push order_submitted
4. 每根 bar 调用 `rebalance_to_target()` + drain events
5. 需要正确创建 instrument (spot_instrument)

- [ ] **Step 3: 保留 BacktestResult 接口兼容性**

确保 BacktestResult dataclass 字段不变，所有现有字段都正确填充。

- [ ] **Step 4: 运行基线测试验证**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/backtest/test_baseline_axon_engine.py -v --tb=short`
Expected: 全部 6 个测试 PASSED

---

### Task 3: 统一策略基类签名

**Files:**
- Modify: `strategy/base.py`
- Modify: `backtest/backtest_loop.py` (RuleStrategy → 兼容 BaseStrategy)
- Check: `backtest/strategies/event_strategy.py`, `backtest/strategies/base.py`
- Check: `strategy/templates/*.py` 8个策略模板

- [ ] **Step 1: 修改 BaseStrategy.on_bar 支持可选 ctx 参数**

修改 `strategy/base.py`，让 `on_bar` 的 ctx 参数有默认值 None，保持向后兼容：

```python
@abstractmethod
def on_bar(self, bar: dict, ctx: Optional[StrategyContext] = None) -&gt; Action:
    """必须实现：每根 K 线返回 Action。ctx 可选，用于支持新老两种调用方式"""
```

同样修改 `on_start` 和 `on_stop`：
```python
def on_start(self, ctx: Optional[StrategyContext] = None) -&gt; None:
    """可选：启动钩子"""
    if ctx is not None:
        self._ctx = ctx

def on_fill(self, fill: dict, ctx: Optional[StrategyContext] = None) -&gt; None:
    """可选：成交回调"""

def on_stop(self, ctx: Optional[StrategyContext] = None) -&gt; None:
    """可选：停止钩子"""
```

- [ ] **Step 2: 让 backtest_loop 的 RuleStrategy 兼容 BaseStrategy**

方案：在 BacktestLoop.run() 中检测策略类型，如果是 BaseStrategy 则传入简单的 ctx，否则按旧方式调用。

```python
from strategy.base import BaseStrategy, StrategyContext

# 在遍历 bar 前创建简单的 ctx
ctx = StrategyContext(symbol=symbol, account_equity=self._initial_cash)
if isinstance(strategy, BaseStrategy):
    strategy.on_start(ctx)
else:
    strategy.on_start()

# 在 on_bar 调用时:
if isinstance(strategy, BaseStrategy):
    action = strategy.on_bar(bar, ctx)
else:
    action = strategy.on_bar(bar)

# 在结束时:
if isinstance(strategy, BaseStrategy):
    strategy.on_stop(ctx)
else:
    strategy.on_stop()
```

- [ ] **Step 3: 验证所有策略模板兼容**

检查 8 个策略模板的 on_bar 签名：
- `strategy/templates/dual_ma.py`
- `strategy/templates/funding_arbitrage.py`
- `strategy/templates/grid.py`
- `strategy/templates/mean_reversion.py`
- `strategy/templates/momentum.py`
- `strategy/templates/trend_follow.py`
- `strategy/templates/cross_sectional.py`
- `strategy/templates/mean_reversion_rl.py`
- `strategy/templates/llm_signal.py`

确保它们的 on_bar 签名兼容 `(self, bar, ctx=None)`。

- [ ] **Step 4: 运行策略相关测试**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/strategy/ tests/unit/backtest/ -v --tb=short`
Expected: 所有相关测试 PASSED

---

### Task 4: 简化 TradingEngine 直接使用 axon API

**Files:**
- Modify: `engine/trading_engine.py`

- [ ] **Step 1: 简化 run_backtest 方法**

TradingEngine.run_backtest 应该直接使用 axon_bridge + BacktestLoop，不引入额外复杂度：

```python
def run_backtest(
    self,
    strategy: RuleStrategy,
    data: pd.DataFrame,
    symbol: str = "BTCUSDT",
    initial_cash: float = 100_000.0,
) -&gt; BacktestResult:
    # 直接使用 BacktestLoop（已经内部使用 axon_quant 原生 API）
    loop = BacktestLoop(initial_cash=initial_cash)
    return loop.run(strategy, data, symbol)
```

确保导入正确：
```python
from backtest.backtest_loop import BacktestLoop, BacktestResult, RuleStrategy
```

- [ ] **Step 2: 确保 exchange adapter 和 risk engine 正确初始化**

检查 axon_bridge.exchange 是否真的导出 BinanceAdapter/OkxAdapter。如果没有导出，需要补充到 axon_bridge/exchange/__init__.py。

先检查 axon_bridge/exchange/__init__.py 的内容。

- [ ] **Step 3: 验证引擎可初始化**

写一个简单的测试脚本验证：

```python
# 临时测试，不提交
from engine.config import EngineConfig
from engine.trading_engine import TradingEngine

config = EngineConfig(exchange="binance", trading_mode="paper")
engine = TradingEngine(config)
print("TradingEngine initialized successfully")
```

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -c "..."`
Expected: 无导入错误

---

### Task 5: 检查并修复 axon_bridge 子模块

**Files:**
- Check: `axon_bridge/exchange/__init__.py`
- Check: `axon_bridge/rl/__init__.py`
- Check: `axon_bridge/inference/__init__.py`
- Check: `axon_bridge/ensemble/__init__.py`

- [ ] **Step 1: 检查 exchange 适配器导出**

查看 `axon_bridge/exchange/__init__.py` 是否正确导出 BinanceAdapter/OkxAdapter。如果没有，需要补充正确的重导出。

注意：项目规则说 axon_quant 通过 PyPI 安装，不要加载本地源码。检查 axon_quant 实际暴露了哪些 exchange 相关类。

- [ ] **Step 2: 检查 RL 模块导出**

查看 `axon_bridge/rl/__init__.py` 是否正确导出 TradingEnv。

- [ ] **Step 3: 检查其他子模块**

快速检查 inference/ensemble/trading 等子模块，确保所有 axon_quant 暴露的类型都正确通过 axon_bridge 重导出。

---

### Task 6: 优化 Services 层集成

**Files:**
- Check: `services/risk_service.py` - 确认使用 axon_bridge.risk
- Check: `services/oms_service.py` - 确认使用 axon_bridge.oms
- Check: `services/rl_service.py` - 确认 RL 训练/回测正确
- Check: `services/llm_service.py` - 检查是否可集成 axon_quant.llm.ReActAgent
- Check: `services/inference_service.py`
- Check: `services/ensemble_service.py`
- Check: `services/hpo_service.py`
- Check: `services/data_service.py`

- [ ] **Step 1: 快速检查每个 service 的导入**

对每个 service 文件，检查是否有：
1. 直接 import axon_quant 而不是通过 axon_bridge（应该统一走 axon_bridge）
2. 旧的/冗余的回测逻辑没有使用 axon_quant
3. 可以简化的地方

- [ ] **Step 2: 修复 RL service 的 backtest 方法**

rl/service.py 中的 backtest() 方法目前创建 RLStrategy 包装类然后用 BacktestLoop 运行。确保它与更新后的 BacktestLoop 兼容。

- [ ] **Step 3: 验证 services 可导入**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -c "from services import risk_service, oms_service, rl_service, llm_service, inference_service, ensemble_service, hpo_service, data_service; print('All services import OK')"`
Expected: 无错误

---

### Task 7: 运行完整测试套件验证

**Files:**
- All modified files

- [ ] **Step 1: 运行核心回测和 axon_bridge 测试**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/backtest/ tests/unit/axon_bridge/ -v --tb=short`
Expected: 90+ PASSED, 2 SKIPPED

- [ ] **Step 2: 运行策略相关测试**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/unit/strategy/ -v --tb=short`
Expected: 所有 PASSED

- [ ] **Step 3: 运行基线回测集成测试**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/integration/test_baseline_axon_0_7_0.py tests/integration/test_funding_arb_backtest.py -v --tb=short`
Expected: 所有 PASSED

- [ ] **Step 4: 验证基线报告可生成**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python scripts/regenerate_baselines.py`
Expected: 16 份基线报告成功生成（8策略×2周期）

---

### Task 8: 运行完整测试（排除已知问题）

- [ ] **Step 1: 运行所有可收集的测试**

Run: `cd /Users/liupeng/workspace/quant/QuantCell/backend && .venv/bin/python -m pytest tests/ --ignore=tests/unit/collector -v --tb=short 2&gt;&amp;1 | tail -100`
Expected: 绝大多数 PASSED，预先存在的失败不新增

- [ ] **Step 2: 提交代码**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/
git commit -m "feat: deep integrate axon-quant 0.10.0 across all layers

- Optimize BacktestLoop with native set_target_position/with_auto_rebalance/with_seed APIs
- Unify strategy base class signature with optional ctx parameter
- Simplify TradingEngine call chain
- Fix test import errors
- Verify all services use axon_bridge adapter layer
- All core backtests pass with reproducible results"
```

---

## 验收标准

1. ✅ 88+ 核心 backtest/axon_bridge 测试通过
2. ✅ BacktestLoop 使用 with_seed(42) 可复现
3. ✅ 使用 set_target_position + with_auto_rebalance 替代手动 push_event
4. ✅ 策略基类签名统一 (on_bar(bar, ctx=None))
5. ✅ 16份基线报告重新生成且结果正确
6. ✅ TradingEngine 正常初始化无错误
7. ✅ Services 层所有模块可正确导入
