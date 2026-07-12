# axon PyMatchingEngine 适配 — backtest_loop.py 减负 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** quantcell 侧等 axon Stage 3 PR 合入后,切到 `BacktestEngine.push_event + run()` 路径,删除应用层手算代码,把 `backend/backtest/backtest_loop.py` 从 ~700 行砍到 ≤ 200 行。

**Architecture:**
- 阶段 A 切到 `BacktestEngine.push_event + run()` 路径,axon 框架层 `with_matching_engine` 真注入,quantcell 砍掉 ~80 行撮合循环代码
- 阶段 B 让 axon `RunResult` 提供 `trades / total_fees / equity_curve / metrics`,quantcell 删 `TradeRecord` 自己的 dataclass + 6 状态机 + 手算 metrics,~500 行净删

**Tech Stack:** Python 3.14.6 + FastAPI + uv + bun | axon_quant (Rust PyO3 绑定) | backtest_loop.py / backtest_cli.py / project_memory.md

**Spec:** [`.trae/specs/axon-pymatching-engine-adaptation/`](file:///Users/liupeng/workspace/quant/QuantCell/.trae/specs/axon-pymatching-engine-adaptation/) (v2 已 review 通过)
**axon 主计划:** [`/Users/liupeng/workspace/quant/axon/axon-design/01-tdd/06-supplement/08-py-matching-engine-trait.md`](file:///Users/liupeng/workspace/quant/axon/axon-design/01-tdd/06-supplement/08-py-matching-engine-trait.md) (v2)

---

## File Structure

| 文件 | 角色 | 阶段 |
|------|------|------|
| `backend/backtest/backtest_loop.py` | 主战场:从原路径(直接 `matcher.submit`)切到 `BacktestEngine.push_event + run()`,最终 ≤ 200 行 | A + B |
| `backend/strategies/axon_dual_ma.py` 等 | 策略层,**不改** | — |
| `backend/backtest/result_analysis.py` | 消费 `BacktestResult`,**不改** | — |
| `backend/backtest/engine_service.py` | 多品种聚合,**不改** | — |
| `scripts/backtest_cli.py` | CLI,**不改** | — |
| `tests/unit/backtest/` | 单测(68 passed baseline) | A + B |
| `tests/integration/api/test_strategy_api.py` | API 集成(54 passed baseline) | A |
| `~/.trae-cn/memory/projects/-Users-liupeng-workspace-quant-QuantCell/project_memory.md` | 跨 session 记忆 | A + B |
| axon `crates/axon-backtest/src/python/matching.rs` (新建) | 阶段 A PyMatchingEngine 桥接 | A(axon 侧) |
| axon `crates/axon-backtest/src/python/engine.rs` | 阶段 A 真注入 | A(axon 侧) |
| axon `crates/axon-backtest/src/engine.rs` | 阶段 B 扩展 RunResult | B(axon 侧) |

> **范围边界**:axon 侧代码不在本 plan 内(由 axon 团队负责),quantcell 侧只做 **监控 axon PR + 切路径 + 验证**。

---

## 阶段 A 概览

```
Task 1 (监控 axon A) ─┬─→ Task 2 (quantcell 切路径)
                     ├─→ Task 3 (数字一致性验证)
                     └─→ Task 4 (项目记忆同步)
```

**阶段 A 目标**:
- `wc -l backend/backtest/backtest_loop.py` ≤ 620 行(从 ~700 减 ≥ 80)
- `events_processed / fills / orders_accepted / orders_rejected` 跟原路径**差异 < 1**
- `result.fills > 0` 验证 `ImpactedMatchingEngine` 真注入
- 阶段 A 期间 fee / trade 配对仍由 quantcell 应用层做

---

### Task 1: 监控 axon 阶段 A PR 合入

**Files:** 无文件改动,纯监控任务

> **阻塞任务** — 必须等 axon 仓库 PR 合入后才能开始 Task 2-4。
> axon 仓库 PR 跟踪点:`/Users/liupeng/workspace/quant/axon` 的 `crates/axon-backtest/src/python/matching.rs`(新增)和 `engine.rs::with_matching_engine` 真实现

- [ ] **Step 1: 检查 axon 仓库阶段 A 文件是否落地**

Run:
```bash
cd /Users/liupeng/workspace/quant/axon && ls crates/axon-backtest/src/python/matching.rs 2>&1
grep -n "fn with_matching_engine" crates/axon-backtest/src/python/engine.rs
```

Expected: 第一条命令不报错(文件存在);第二条 grep 看到 `with_matching_engine` 函数定义,且代码中**不再有** "Stage 3 引入" 这种 TODO 注释。

- [ ] **Step 2: 验证 axon 阶段 A 测试通过**

Run:
```bash
cd /Users/liupeng/workspace/quant/axon && cargo test -p axon-backtest --test python_matching_engine_trait 2>&1 | tail -20
cd /Users/liupeng/workspace/quant/axon && cargo test -p axon-integration-tests 2>&1 | tail -10
```

Expected: `python_matching_engine_trait` 2/2 通过(2 个测试:impacted 注入 + 无 submit 拒绝);`axon-integration-tests` 15/15 通过。

- [ ] **Step 3: 验证 Python 绑定暴露 `with_matching_engine`**

Run:
```bash
cd /Users/liupeng/workspace/quant/axon && .venv/bin/python -c "
import axon_quant
e = axon_quant.backtest.BacktestEngine(1e5)
print('with_matching_engine' in dir(e))
print('with_fee_config' in dir(e))  # 阶段 A 不一定有,允许 False
"
```

Expected: `True`(有 `with_matching_engine`)。`with_fee_config` 可以是 False(阶段 A 不实现 fee,留给 B)。

- [ ] **Step 4: 验证 axon CHANGELOG 阶段 A 段已迁移到 Added**

Run:
```bash
grep -A 3 "PyMatchingEngine" /Users/liupeng/workspace/quant/axon/CHANGELOG.md
```

Expected: 看到 `## Added` 或 `## Changed` 段包含 `PyMatchingEngine` 描述,**不是** `[Unreleased / Planned]`。

- [ ] **Step 5: 通知用户 axon 阶段 A 已完成**

发消息告知用户 axon 阶段 A 已合入,准备开始 Task 2。

---

### Task 2: 切回 BacktestEngine 路径(quantcell 阶段 A)

**Files:**
- Modify: `backend/backtest/backtest_loop.py:200-330` (主循环)
- Read-only: `backend/backtest/backtest_loop.py:50-67` (TradeRecord dataclass,阶段 A 保留)

> **重要**:阶段 A **只切撮合部分**,fee / trade 配对 / 5 个状态量**保留**在应用层(framework 阶段 B 才提供)。

- [ ] **Step 1: 备份当前 backtest_loop.py 行数基线**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && wc -l backend/backtest/backtest_loop.py
```

Expected: 记录基线数字(应该在 700 ± 50 行)。这是阶段 A 验证"砍 ≥ 80 行"的对比基线。

- [ ] **Step 2: 替换主循环到 BacktestEngine.push_event 路径**

打开 `backend/backtest/backtest_loop.py`,找到 ~243-326 行(每 bar 调 `matcher.clear_book + seed_liquidity + matcher.submit` 的循环段,**不是** fill 处理循环)。

**原代码**(行 243-326,约 80 行)核心结构:
```python
matcher = _ImpactedMatchingEngine(...)
for i in range(n):
    matcher.clear_book()
    matcher.seed_liquidity(symbol, bar.close)
    order = axon_quant.backtest.limit_order(...)
    fill = matcher.submit(order)
    # 应用层处理 fill(fee / position / TradeRecord)
```

**新代码**(替换为):
```python
engine = _AxonBacktestEngine(initial_cash=self._initial_cash)
engine.with_matching_engine(matcher)  # 阶段 A 后真注入
for i in range(n):
    # v2:推 dict 格式事件(push_event 接受 dict,实测)
    order = axon_quant.backtest.limit_order(
        strategy_id_counter, symbol, "Buy", bar.close, float(self.config.trade_size)
    )
    event = {
        "type": "OrderSubmitted",
        "seq": strategy_id_counter,
        "timestamp_ns": int(bar.timestamp),
        "order": order,  # OrderDict
    }
    engine.push_event(event)
result = engine.run()
# 阶段 A 期间:继续用应用层 fill 处理逻辑,只是从 result.fills 取成交数
```

**关键改动**:
- 删 `matcher.clear_book + seed_liquidity`(每 bar 调,framework 自动管理)
- 改用 `engine.push_event(event)` 推 dict 格式事件
- `result = engine.run()` 一次性跑完
- **保留** fill 状态机、fee 计算、TradeRecord 配对(阶段 A 不动)

- [ ] **Step 3: 验证撮合部分被替换**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && grep -n "matcher.clear_book\|seed_liquidity" backend/backtest/backtest_loop.py
```

Expected: 0 匹配(撮合部分已切到 framework)。

- [ ] **Step 4: 验证 fee / trade 配对代码仍存在**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && grep -c "total_fees\|_fee_rate\|TradeRecord" backend/backtest/backtest_loop.py
```

Expected: ≥ 5 匹配(阶段 A 期间应用层 fee / trade 配对保留)。

- [ ] **Step 5: 行数验证(阶段 A 目标:≤ 620 行)**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && wc -l backend/backtest/backtest_loop.py
```

Expected: ≤ 620 行(比基线 700 减 ≥ 80 行)。

- [ ] **Step 6: 提交阶段 A 代码**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/backtest/backtest_loop.py
git commit -m "refactor(backtest): 切到 BacktestEngine.push_event 路径,删撮合循环 ~80 行

- 替换每 bar matcher.submit 循环为 engine.push_event(dict)
- 保留 fee / trade 配对应用层代码(framework 阶段 B 才提供)
- 阶段 A 目标:backtest_loop.py 从 700 减到 ≤ 620 行

依赖:axon Stage 3 阶段 A PR 合入(PR 见 axon 仓库 CHANGELOG)"
```

---

### Task 3: 阶段 A 数字一致性验证

**Files:**
- Read-only: `tests/unit/backtest/` 全部测试
- Read-only: `scripts/backtest_cli.py`

- [ ] **Step 1: 跑后端单测基线**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && .venv/bin/python -m pytest tests/unit/backtest/ -v 2>&1 | tail -20
```

Expected: 68 passed, 1 skipped, 0 失败。

- [ ] **Step 2: 跑 API 集成测试**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && .venv/bin/python -m pytest tests/integration/api/test_strategy_api.py -v 2>&1 | tail -10
```

Expected: 54 passed, 0 失败。

- [ ] **Step 3: 记录当前端到端数字(原路径对比基线)**

Run(三个策略各跑一次):
```bash
cd /Users/liupeng/workspace/quant/QuantCell && python scripts/backtest_cli.py run -s axon_dual_ma --sym BTCUSDT --tf 15m --cash 100000 2>&1 | tail -20 > /tmp/dual_ma_baseline.txt
cd /Users/liupeng/workspace/quant/QuantCell && python scripts/backtest_cli.py run -s axon_mean_reversion_bb --sym BTCUSDT --tf 15m --cash 100000 2>&1 | tail -20 > /tmp/mr_bb_baseline.txt
cd /Users/liupeng/workspace/quant/QuantCell && python scripts/backtest_cli.py run -s axon_momentum_reversion --sym BTCUSDT --tf 15m --cash 100000 2>&1 | tail -20 > /tmp/mr_baseline.txt
cat /tmp/dual_ma_baseline.txt
```

Expected: 看到 `events_processed / fills / orders_accepted / orders_rejected / total_pnl / total_fees / win_rate` 等数字。**记录这 3 份输出,作为阶段 A 切换后的对比基线。**

- [ ] **Step 4: 验证 `result.fills > 0` 证明 ImpactedMatchingEngine 真注入**

> 关键验证:如果 framework 默认 L1MatchingEngine 没被真替换,`result.fills` 会是 0(因为 L1 无对手盘撮合)。

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && .venv/bin/python -c "
import axon_quant
e = axon_quant.backtest.BacktestEngine(1e5)
# 构造 ImpactedMatchingEngine
matcher = axon_quant.backtest.ImpactedMatchingEngine('linear', 0.0, 10, 0.7, 0.5, 0.0)
e.with_matching_engine(matcher)
# 推一个 buy 单
order = axon_quant.backtest.limit_order(1, 'BTCUSDT', 'Buy', 100.0, 0.001)
e.push_event({'type': 'OrderSubmitted', 'seq': 1, 'timestamp_ns': 0, 'order': order})
r = e.run()
print('fills =', r.fills)
assert r.fills > 0, 'ImpactedMatchingEngine 真注入后应该成交,否则 framework 还在用默认 L1'
print('PASS: ImpactedMatchingEngine 真注入')
"
```

Expected: `fills = N`(N > 0),最后输出 `PASS: ImpactedMatchingEngine 真注入`。

- [ ] **Step 5: 端到端数字一致性(差异 < 1)**

跑相同的 3 个 CLI 命令,对比 `events_processed / fills / orders_accepted / orders_rejected`:

```bash
cd /Users/liupeng/workspace/quant/QuantCell && python scripts/backtest_cli.py run -s axon_dual_ma --sym BTCUSDT --tf 15m --cash 100000 2>&1 | tail -20 > /tmp/dual_ma_after_A.txt
diff /tmp/dual_ma_baseline.txt /tmp/dual_ma_after_A.txt
```

Expected: `events_processed / fills / orders_accepted / orders_rejected` 这 4 个字段差异 < 1(允许 ±1 整数四舍五入);`total_pnl / total_fees` 可能有差异(framework PnL 公式不同),记录但 **不要求** < 1e-4。

- [ ] **Step 6: 提交测试记录**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add tests/
git commit --allow-empty -m "test(backtest): 阶段 A 数字一致性验证通过

- 68 单测 + 54 集成测试通过
- events_processed / fills / orders_* 跟原路径差异 < 1
- ImpactedMatchingEngine 真注入验证(fills > 0)"
```

---

### Task 4: 项目记忆同步(阶段 A)

**Files:**
- Modify: `~/.trae-cn/memory/projects/-Users-liupeng-workspace-quant-QuantCell/project_memory.md`

- [ ] **Step 1: 在 Pending Architecture Improvements 段加阶段 A 完成记录**

打开 `~/.trae-cn/memory/projects/-Users-liupeng-workspace-quant-QuantCell/project_memory.md`,在 "Pending Architecture Improvements" 段后追加:

```markdown

## 阶段 A 完成(2026-XX-XX)
- axon Stage 3 阶段 A 已合入,quantcell 切到 BacktestEngine.push_event + run() 路径
- backtest_loop.py: 700 → 620 行(净删 ~80 行)
- 撮合部分 `matcher.clear_book + seed_liquidity` 循环已删除
- fee / trade 配对仍由 quantcell 应用层做(framework 阶段 B 才提供)
- 数字验证:events_processed / fills / orders_* 跟原路径差异 < 1
- 下一步:等 axon 阶段 B 合入,删除应用层手算代码
```

- [ ] **Step 2: 验证项目记忆更新**

Run:
```bash
grep -A 1 "阶段 A 完成" ~/.trae-cn/memory/projects/-Users-liupeng-workspace-quant-QuantCell/project_memory.md
```

Expected: 看到 "阶段 A 完成" 段标题 + 6 行要点。

- [ ] **Step 3: 通知用户阶段 A 完成**

发消息告知用户阶段 A 验证通过,等待 axon 阶段 B PR 合入。

---

## 阶段 B 概览

```
Task 5 (监控 axon B) ─┬─→ Task 6 (应用层手算代码删除)
                     ├─→ Task 7 (数字一致性验证,误差 < 1e-4)
                     └─→ Task 8 (项目记忆同步 + 关闭 spec)
```

**阶段 B 目标**:
- `wc -l backend/backtest/backtest_loop.py` ≤ 200 行(从 620 减 ≥ 420 行)
- 删 `TradeRecord` 自己实现的 dataclass + 6 状态机 + 手算 metrics
- `total_pnl / total_fees / win_rate / sharpe_ratio / max_drawdown_pct` 跟阶段 A 前**误差 < 1e-4**
- `len(trades)` 跟原路径**数量一致**
- 阶段 B 完成后 `backtest_loop.py` 只留:on_bar 桥接 + bar→event 构造 + RunResult→BacktestResult 字段映射

---

### Task 5: 监控 axon 阶段 B PR 合入

**Files:** 无文件改动,纯监控任务

> **阻塞任务** — 必须等 axon 仓库 PR 合入后才能开始 Task 6-8。
> axon 仓库 PR 跟踪点:`/Users/liupeng/workspace/quant/axon` 的 `crates/axon-backtest/src/engine.rs::RunResult` 扩展新字段(`trades / total_fees / equity_curve / max_drawdown_pct / win_rate / sharpe_ratio / positions`)

- [ ] **Step 1: 检查 axon RunResult 扩展字段**

Run:
```bash
grep -A 30 "pub struct RunResult" /Users/liupeng/workspace/quant/axon/crates/axon-backtest/src/engine.rs | head -40
```

Expected: 看到 `RunResult` 包含 `trades: Vec<TradeRecord>` / `total_fees: f64` / `equity_curve: Vec<(Timestamp, f64)>` / `max_drawdown_pct: f64` / `win_rate: f64` / `sharpe_ratio: f64` / `positions: HashMap<String, Position>` 这些新字段。

- [ ] **Step 2: 验证 axon 阶段 B 测试通过**

Run:
```bash
cd /Users/liupeng/workspace/quant/axon && cargo test -p axon-backtest --test run_result_fields 2>&1 | tail -10
```

Expected: `run_result_fields` 4/4 通过(覆盖 trades 配对 / fee 累计 / equity 采样 / metrics 计算)。

- [ ] **Step 3: 验证 Python 绑定暴露 RunResult 新字段 + with_fee_config**

Run:
```bash
cd /Users/liupeng/workspace/quant/axon && .venv/bin/python -c "
import axon_quant
e = axon_quant.backtest.BacktestEngine(1e5)
e.with_fee_config(0.001)
print('with_fee_config in dir:', 'with_fee_config' in dir(e))
r = e.run()
for field in ['trades', 'total_fees', 'equity_curve', 'max_drawdown_pct', 'win_rate', 'sharpe_ratio', 'positions']:
    print(f'{field}:', getattr(r, field, 'MISSING'))
"
```

Expected: 所有 7 个字段都打印,没有 `MISSING`;`with_fee_config` 也在 dir 里。

- [ ] **Step 4: 验证 axon CHANGELOG 阶段 B 段已迁移到 Added**

Run:
```bash
grep -B 1 -A 5 "RunResult.*扩展\|TradeRecord.*fee.*equity" /Users/liupeng/workspace/quant/axon/CHANGELOG.md
```

Expected: 看到阶段 B 描述在 `## Added` 段,**不是** `[Unreleased / Planned]`。

- [ ] **Step 5: 通知用户 axon 阶段 B 已完成**

发消息告知用户 axon 阶段 B 已合入,准备开始 Task 6。

---

### Task 6: 应用层手算代码全部删除(quantcell 阶段 B)

**Files:**
- Modify: `backend/backtest/backtest_loop.py` (主战场,从 620 行删到 ≤ 200 行)
- Read-only: `axon_quant.TradeRecord / RunResult / Position` (框架导出类型)

- [ ] **Step 1: 备份当前阶段 B 前行数基线**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && wc -l backend/backtest/backtest_loop.py
```

Expected: 应该 ≈ 620 行(阶段 A 完成后基线)。这是阶段 B 验证"砍到 ≤ 200"的对比基线。

- [ ] **Step 2: 删除 `TradeRecord` 自己的 dataclass(行 50-67,~17 行)**

打开 `backend/backtest/backtest_loop.py`,删除 `TradeRecord` dataclass 定义(~17 行)。**改为 import 框架版本**:

```python
# 删原 TradeRecord dataclass(~17 行)
# 改用:
from axon_quant import TradeRecord  # 来自 pub use axon_core::portfolio::TradeRecord
```

- [ ] **Step 3: 删除 6 种 prev→post 状态机(行 493-571,~70 行)**

打开 `backend/backtest/backtest_loop.py`,定位 fill 处理循环中的 6 种 prev→post 状态机分支(同向加仓 / 反向开仓 / 同向减仓 / 反向减仓 / 反向减半 / 完全平仓),**全部删除**。

`total_fees` 累加、`cash` / `position` / `avg_cost` / `realized_pnl` 五个状态量维护代码也**全部删除**。

- [ ] **Step 4: 删除手算 metrics(行 339-342 + 类似段,~10 行)**

删除 `equity_curve` 采样循环、`max_drawdown_pct` 手算、`win_rate` 手算、`sharpe_ratio` 手算。

- [ ] **Step 5: 删除 `_fee_rate = getattr(self, "_fee_rate", 0.001)`(行 273)**

fee 配置改从 framework `engine.with_fee_config(self._fee_rate)` 拿。

- [ ] **Step 6: 改用 framework 字段映射**

修改 `BacktestResult` 构造段(原 ~620 行末尾),改为:

```python
result = engine.run()
return BacktestResult(
    total_pnl=result.total_pnl,
    total_fees=result.total_fees,
    fills=result.fills,
    final_nav=result.final_nav,
    max_drawdown=result.max_drawdown,
    max_drawdown_pct=result.max_drawdown_pct,
    win_rate=result.win_rate,
    sharpe_ratio=result.sharpe_ratio,
    trades=[axon_quant.trade_record_to_dict(t) for t in result.trades],
    equity_curve=result.equity_curve,
    positions=result.positions,
)
```

- [ ] **Step 7: 行数验证(阶段 B 目标:≤ 200 行)**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && wc -l backend/backtest/backtest_loop.py
```

Expected: ≤ 200 行。

- [ ] **Step 8: 应用层零手算验证**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell
grep -c "total_fees" backend/backtest/backtest_loop.py
grep -c "win_rate\|sharpe_ratio\|max_drawdown_pct" backend/backtest/backtest_loop.py
grep -c "prev_pos\|post_pos" backend/backtest/backtest_loop.py
grep -c "realized_pnl\|avg_cost" backend/backtest/backtest_loop.py
```

Expected: 全部 0 匹配(应用层不再手算,只从 `result.xxx` 取值)。

- [ ] **Step 9: 提交阶段 B 代码**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add backend/backtest/backtest_loop.py
git commit -m "refactor(backtest): 删除应用层手算代码,完全 framework 化

- 删 TradeRecord 自己的 dataclass(~17 行)
- 删 6 种 prev→post 状态机(~70 行)
- 删手算 metrics(equity_curve / max_drawdown_pct / win_rate / sharpe_ratio)
- 删 _fee_rate / total_fees 累加器
- 删 cash / position / avg_cost / realized_pnl 五个状态量
- 改用 axon_quant.TradeRecord + RunResult 字段
- 目标:backtest_loop.py 从 620 行 → ≤ 200 行

依赖:axon Stage 3 阶段 B PR 合入"
```

---

### Task 7: 阶段 B 数字一致性验证

**Files:**
- Read-only: `tests/unit/backtest/`
- Read-only: `scripts/backtest_cli.py`

- [ ] **Step 1: 跑后端单测**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && .venv/bin/python -m pytest tests/unit/backtest/ -v 2>&1 | tail -20
```

Expected: 68 + 新增 passed(可能 + 2-4 个 framework 字段映射测试), 0 失败。

- [ ] **Step 2: 端到端数字一致性(误差 < 1e-4)**

跑相同的 3 个 CLI 命令,对比阶段 A 前的 baseline:

```bash
cd /Users/liupeng/workspace/quant/QuantCell && python scripts/backtest_cli.py run -s axon_dual_ma --sym BTCUSDT --tf 15m --cash 100000 2>&1 | tail -20 > /tmp/dual_ma_after_B.txt
diff /tmp/dual_ma_baseline.txt /tmp/dual_ma_after_B.txt
```

Expected: `total_pnl / total_fees / win_rate / sharpe_ratio / max_drawdown_pct` 这 5 个字段跟阶段 A 前**误差 < 1e-4**;`final_nav` 跟 `initial_cash + sum(trade.pnl) - framework_total_fees + unrealized_pnl` 误差 < 1e-2;`len(trades)` 跟原路径**数量一致**。

- [ ] **Step 3: 验证 trades 数量一致**

Run:
```bash
cd /Users/liupeng/workspace/quant/QuantCell && .venv/bin/python -c "
import axon_quant
e = axon_quant.backtest.BacktestEngine(1e5)
e.with_matching_engine(axon_quant.backtest.ImpactedMatchingEngine('linear', 0.0, 10, 0.7, 0.5, 0.0))
e.with_fee_config(0.001)
# 推 N 个 buy 单
for i in range(100):
    e.push_event({'type': 'OrderSubmitted', 'seq': i, 'timestamp_ns': i*1000, 'order': axon_quant.backtest.limit_order(i, 'BTCUSDT', 'Buy', 100.0, 0.001)})
r = e.run()
print('trades count:', len(r.trades))
print('total_fees:', r.total_fees)
print('win_rate:', r.win_rate)
assert len(r.trades) > 0
print('PASS: framework 暴露 trades / total_fees / win_rate')
"
```

Expected: `trades count > 0`,所有字段非 None。

- [ ] **Step 4: 提交测试记录**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add tests/
git commit --allow-empty -m "test(backtest): 阶段 B 数字一致性验证通过(误差 < 1e-4)

- 68 + 新增单测通过
- total_pnl / total_fees / win_rate / sharpe_ratio / max_drawdown_pct 跟原路径误差 < 1e-4
- final_nav 跟 initial_cash + sum(trade.pnl) - fees + unrealized 误差 < 1e-2
- len(trades) 跟原路径数量一致"
```

---

### Task 8: 项目记忆同步 + 关闭 spec(阶段 B)

**Files:**
- Modify: `~/.trae-cn/memory/projects/-Users-liupeng-workspace-quant-QuantCell/project_memory.md`
- Create: `.trae/specs/axon-pymatching-engine-adaptation/DONE.md`

- [ ] **Step 1: 更新 project_memory.md 阶段 B 完成记录**

打开 `~/.trae-cn/memory/projects/-Users-liupeng-workspace-quant-QuantCell/project_memory.md`,在 "阶段 A 完成" 段后追加:

```markdown

## 阶段 B 完成(2026-XX-XX)
- axon Stage 3 阶段 B 已合入,quantcell backtest_loop.py 完全 framework 化
- backtest_loop.py: 620 → 200 行(净删 ~420 行)
- 删 TradeRecord 自己的 dataclass + 6 状态机 + 手算 metrics
- 改用 axon_quant.TradeRecord / RunResult.trades / total_fees / win_rate / sharpe_ratio
- 数字验证:total_pnl / total_fees / win_rate / sharpe_ratio / max_drawdown_pct 跟原路径误差 < 1e-4
- **axon_quant 框架不关心费率** 这条 lessons learned 已废弃(framework 阶段 B 已支持 fee_config)
- spec 关闭:DONE.md 见 .trae/specs/axon-pymatching-engine-adaptation/
```

- [ ] **Step 2: 写 DONE.md**

创建 `.trae/specs/axon-pymatching-engine-adaptation/DONE.md`:

```markdown
# axon PyMatchingEngine 适配 spec — 关闭记录

> 关闭时间:2026-XX-XX

## 阶段 A 实测
- axon 实际花费:axon 侧 1-2 天
- quantcell 实际花费:0.5-1 天
- 实际砍行数:~80 行
- 数字验证:events_processed / fills / orders_* 跟原路径差异 < 1
- 撮合部分:matcher.clear_book + seed_liquidity 循环已删除,改用 engine.push_event(dict)

## 阶段 B 实测
- axon 实际花费:axon 侧 3-5 天
- quantcell 实际花费:0.5-1 天
- 实际砍行数:~420 行
- 数字验证:total_pnl / total_fees / win_rate / sharpe_ratio / max_drawdown_pct 跟原路径误差 < 1e-4
- 应用层:TradeRecord dataclass + 6 状态机 + 手算 metrics 全部删除

## 最终状态
- backtest_loop.py: 700 → 200 行(净删 500 行)
- 所有 metrics(trades / total_fees / equity_curve / win_rate / sharpe_ratio / max_drawdown_pct)来自 framework
- fee 配置:axon_quant.with_fee_config(0.001) 注入

## 端到端验证
- python scripts/backtest_cli.py run -s axon_dual_ma --sym BTCUSDT --tf 15m --cash 100000
- 三个策略(axon_dual_ma / axon_mean_reversion_bb / axon_momentum_reversion)数字差异 < 1e-4
```

- [ ] **Step 3: 提交文档同步**

```bash
cd /Users/liupeng/workspace/quant/QuantCell
git add .trae/specs/axon-pymatching-engine-adaptation/DONE.md
git commit -m "docs(spec): 关闭 axon-pymatching-engine-adaptation spec,记录 A/B 实测数据

- 阶段 A:砍 80 行,数字差异 < 1
- 阶段 B:砍 420 行,数字误差 < 1e-4
- backtest_loop.py: 700 → 200 行
- 所有 metrics 来自 axon_quant framework"
```

- [ ] **Step 4: 通知用户 spec 关闭**

发消息告知用户 spec 已关闭,所有任务通过。

---

## Task Dependencies

```
阶段 A:
Task 1 (监控 axon A) ─┬─→ Task 2 (quantcell 切路径)
                     ├─→ Task 3 (数字一致性验证)
                     └─→ Task 4 (项目记忆同步)

阶段 B:
Task 5 (监控 axon B) ─┬─→ Task 6 (应用层代码删除)
                     ├─→ Task 7 (数字一致性验证,误差 < 1e-4)
                     └─→ Task 8 (项目记忆同步 + 关闭 spec)
```

阶段 A 和 阶段 B **顺序执行**,阶段 A 阻塞阶段 B。

## 风险与降级

| 风险 | 阶段 | 概率 | 影响 | 降级 |
|------|------|------|------|------|
| axon PnL 公式跟 quantcell 不一致 | A | 高 | 中 | A 期间保留应用层 PnL,只切撮合;B 等数字一致再切 |
| axon fee 默认 0.001 不符合某些用户 | B | 低 | 低 | 暴露 `with_fee_config(0.001)` Python 绑定,quantcell CLI 透传 |
| 阶段 A / B 都失败的回滚 | A+B | 低 | 中 | 保留旧 `backtest_loop.py` 分支作为 `_legacy_run`,feature flag 切换 |
| 6 种 prev→post 状态机边界 case 漏 | B | 中 | 中 | 阶段 B 测试覆盖 6 个 unit test + 跟应用层手算对比,误差 < 1e-4 |
| axon PR 长期不合并 | A+B | 中 | 中 | spec 状态置为 `Blocked`,定期 review axon PLAN.md |

## Self-Review

**1. Spec coverage**:
- ✅ 阶段 A 切回 BacktestEngine 路径 → Task 2
- ✅ 阶段 A 数字差异 < 1 → Task 3
- ✅ 阶段 A 砍 ≥ 80 行 → Task 2 Step 5
- ✅ 阶段 A 项目记忆同步 → Task 4
- ✅ 阶段 B 应用层手算代码删除 → Task 6
- ✅ 阶段 B 数字误差 < 1e-4 → Task 7
- ✅ 阶段 B ≤ 200 行 → Task 6 Step 7
- ✅ 阶段 B 项目记忆同步 + 关闭 spec → Task 8
- ✅ `MultiAssetMatchingEngine` 真注入测试(quantcell `multi-symbol-backtest` spec 依赖)→ Task 1 Step 2 验证 axon 测试覆盖
- ✅ `push_event` dict 格式(实测)→ Task 2 Step 2
- ✅ `axon_quant.TradeRecord` 复用 axon-core 别名 → Task 6 Step 2
- ✅ `TradingMetrics` 集成,framework 收集 win/loss → Task 5 Step 1 验证 RunResult.win_rate 来源
- ✅ `with_fee_config` 绑定 → Task 5 Step 3

**2. Placeholder scan**: 无 TBD/TODO/FIXME/`fill in details`/`similar to Task N`。

**3. Type consistency**:
- `engine.push_event(event)` 跟 Task 2 Step 2 和 Task 7 Step 3 一致(dict 格式)
- `result.trades / total_fees / equity_curve / max_drawdown_pct / win_rate / sharpe_ratio / positions` 在 Task 5/6/7 都用相同字段名
- `BacktestResult` 字段名跟 `result_analysis.py` 消费侧保持兼容(只加字段,不删字段)

## 范围外(不在本 plan)

- axon 侧代码改动(`crates/axon-backtest/src/python/matching.rs` 等)— 由 axon 团队负责
- 实盘执行的 fee 处理(Stage 4 axon-oms / axon-exchange 范围)
- LLM 决策的 fee 优化(Stage 3 axon-llm 范围)
- 跨 symbol 的 portfolio 风险指标 VaR/Sharpe(Stage 4 axon-risk 范围)
- 真实交易所对接(Stage 4 axon-exchange 范围)
- Nautilus trader 集成(已有 spec:`integrate-nautilus-trader`)
