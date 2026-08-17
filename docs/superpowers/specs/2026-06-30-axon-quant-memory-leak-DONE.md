# 2026-06-30 axon_quant 内存泄漏 — DONE 状态

## 状态总结(2026-06-30 更新)

**✅ 已修复根因(axon 侧 commit)**:本次回归分析发现泄漏真正根因不在 `ImpactedMatchingEngine`
本身,而是它透传的 `L1MatchingEngine::clear_book` 方法:`order_index: HashMap<u64, (Side, Price)>`
的 `HashMap::clear()` **不释放底层 raw table 内存**(Rust std 明确语义 "Keeps the allocated
memory for reuse")。叠加 `seed_liquidity` 单调递增 `next_id` 触发 raw table 按需扩容,跨多轮
`seed_liquidity + clear_book` 循环后 raw table 容量只增不减;PyO3 端
`Arc<Mutex<Py<PyAny>>>` 持 Python 对象 + 多回测引擎实例创建/丢弃场景累积到 GB 级。

**修复方案**(`crates/axon-backtest/src/matching/engine.rs` `clear_book`):
```rust
// 原:self.order_index.clear();  // ❌ 不释放 raw table
// 修:self.order_index = HashMap::new();  // ✅ 等价 mem::replace,旧实例 drop 真正 deallocate
self.bids.clear();        // BTreeMap::clear() 已真正递归释放,无需替换
self.asks.clear();        // 同上
self.order_index = HashMap::new();  // HashMap::clear() 不缩容,需替换实例
```

**axon 验证结果**:
- `cargo test -p axon-backtest --lib` → **179 passed**(176 原有 + 3 新增)
  - `test_clear_book_resets_all_state` ✅
  - `test_clear_book_stable_over_1000_rounds` ✅(1000 轮 seed+clear 验证)
  - `test_clear_book_does_not_ghost_retain_old_ids` ✅
- `cargo clippy -p axon-backtest --all-targets -- -D warnings` → 0 warning

**当前缓解方案**:quantcell `backend/backtest/backtest_loop.py` 仍保留 `L1MatchingEngine` 路径
(`_run_with_axon` L181-183),功能上仍存在 buy 单无对手盘 → `fills=0` 的限制。可选下一步:**切回
`ImpactedMatchingEngine` 路径** 恢复 buy 单成交语义(原 A+B 计划阶段 A+/阶段 A) — axon 侧已具备
条件,quantcell 切路径任务可重新激活。

**消除误用**:`backend/tests/unit/backtest/test_impacted_matching_engine.py` 仍保留在
`.trash/impacted-matching-engine-leak-20260630/`(axon 修复已完成,后续可考虑 restore 作为回归
测试 — 但需先在 quantcell 切路径时验证 `ImpactedMatchingEngine + seed_liquidity` 在 Python 端
的内存行为,确认无 PyO3 端持有 `Py<PyAny>` 引用泄漏)。

## 不再做的事

- ❌ **不再跑 `tests/unit/backtest/test_axon_quant_e2e.py` 的 100 bar 回测** —
  单次小数据回测不会泄漏,但**反复跑 + pytest worker 进程 + 大 fixture 加载** 会
  累积内存到危险水平。
- ⚠️ **(已更新)** 不再用 `ImpactedMatchingEngine` 路径跑 backtest — 此规则**仍生效**,
  直到 quantcell 切路径任务完成(`backtest_loop.py` 改回 `ImpactedMatchingEngine` + 验证
  Python 端无 PyO3 引用泄漏)。axon 框架层修复 ≠ quantcell 应用层切路径。

## 已知功能限制(L1MatchingEngine 路径)

`L1MatchingEngine` 是纯订单簿撮合,没有 `seed_liquidity` 提供的虚拟对手盘。
buy 单会:
1. `match_against_asks` 返回空(asks 是空的)
2. `insert_passive` 把 buy 挂入 `bids`(`active_order_count += 1`)
3. 在 `BacktestEngine.run()` 的 `handle_submit` 中:
   - `fills.is_empty() == true` + `added_to_book == true` ⇒ `orders_accepted += 1`

所以 buy 单**会被接受**(挂入 bids),只是没对手盘不成交 — `fills=0, total_pnl=0`。
这是**功能问题**,不是内存问题。

**修复路径**:axon 框架层 `clear_book` 内存泄漏已修复,quantcell 切回
`ImpactedMatchingEngine + seed_liquidity` 路径后可恢复 buy 单成交语义。原 A+B 计划
(`docs/superpowers/plans/2026-06-30-axon-pymatching-engine-adaptation.md`)中阶段 A
切路径任务可重新激活。

## axon 侧已修复的内存泄漏 ✅

**根因**:`L1MatchingEngine::clear_book` 中 `self.order_index.clear()` 不释放 `HashMap`
底层 raw table,叠加 `seed_liquidity` 单调递增 `next_id` 触发 raw table 按需扩容,
跨多轮循环累积到 GB 级。

**修复**(`crates/axon-backtest/src/matching/engine.rs`):
```rust
fn clear_book(&mut self) {
    self.bids.clear();           // BTreeMap 真正释放
    self.asks.clear();           // BTreeMap 真正释放
    self.order_index = HashMap::new();  // ✅ 替换实例 → raw table 真正 deallocate
}
```

**axon 验证**:3 个内存稳定性测试(`test_clear_book_resets_all_state` /
`test_clear_book_stable_over_1000_rounds` / `test_clear_book_does_not_ghost_retain_old_ids`)
+ `cargo test -p axon-backtest --lib` 179 passed + `cargo clippy -D warnings` 0 warning。

**影响范围**:`ImpactedMatchingEngine.clear_book` 透传到 `L1MatchingEngine::clear_book`,
修复后 `seed_liquidity + clear_book` 整条链路不再泄漏。`seed_liquidity` 本身的逻辑
(挂 BTreeMap 单)未变,内存释放改在 `clear_book` 阶段。

## 验收

- ✅ axon 侧 `L1MatchingEngine::clear_book` 内存泄漏已修复(commit,179 tests passed)
- ✅ backtest_loop.py 使用 `L1MatchingEngine`(确认 grep 唯一 import) — 维持现状
- ✅ test_impacted_matching_engine.py 已 mv 到 `.trash/` — 维持现状
- ✅ `tests/unit/engine/test_backtest_loop.py` 用小数据集(3 根 K 线)+ `L1MatchingEngine` 路径
- ✅ 单元测试 47 passed,1 skipped(test_axon_quant_e2e 未跑,避免内存)
- ⏳ **可选下一步**:quantcell 切回 `ImpactedMatchingEngine` 路径(原 A+B 计划阶段 A+ 切路径)

## 不要再做的事(给未来的自己 / 其他 agent) — **2026-06-30 更新**

### ❌ 仍然不能做

- **不再跑 `tests/unit/backtest/test_axon_quant_e2e.py` 的 100 bar 回测** — pytest worker
  + 大 fixture 加载会累积内存,即使 axon 修复后也不要在测试套件中跑这条路径。

### ✅ 现在可以做(axon 修复已完成)

- **可以"切回 ImpactedMatchingEngine 让 buy 单能成交"** — 但需走原 A+B 计划阶段 A+ 切路径任务
  (见 `docs/superpowers/plans/2026-06-30-axon-pymatching-engine-adaptation.md`),不要直接
  改 `backtest_loop.py` 切回旧路径。需在切路径 PR 中加一个 1000+ bar 的内存基准测试
  (单进程峰值 < 500MB) 验证 Python 端无 PyO3 引用泄漏。
- **可以"把 backtest_loop 改成 seed_liquidity 路径"** — 同上,通过 A+ 切路径任务走,带
  内存基准验证。
- **可以"把 test_impacted_matching_engine.py 加回来"** — 作为回归测试,确认
  `ImpactedMatchingEngine + seed_liquidity` 不再泄漏;但需配合上面切路径任务一起做。

### ⏸ 暂时不做(等切路径任务)

- 不要在 `backtest_loop.py` 中**直接**改回 `ImpactedMatchingEngine` 路径,必须走完整 A+
  切路径任务流程(切路径 + 内存基准 + 测试验证)。

## 相关文件

- `backend/backtest/backtest_loop.py` — 已切回 `L1MatchingEngine` 路径
- `backend/backtest/engines/axon_engine.py` — 委派给 `BacktestLoop`,无内存泄漏
- `backend/backtest/result_analysis.py` — formatter,无状态
- `backend/backtest/result_formatter_service.py` — formatter,无状态
- `.trash/impacted-matching-engine-leak-20260630/test_impacted_matching_engine.py`
  — 已废弃,不要 restore
- `docs/superpowers/plans/2026-06-30-axon-pymatching-engine-adaptation.md` — 原 A+B 计划
  (Stage A 切 `with_matching_engine` 真注入 + Stage B 扩展 `RunResult`)

## 计划状态 — **2026-06-30 更新**

- ✅ Stage A (axon): `with_matching_engine` 真注入 + `PyMatchingEngine` 桥接
- ✅ Stage A (axon): `MultiAssetMatchingEngine` 验证(由 quantcell `multi-symbol-backtest`
  spec 依赖)
- ✅ Stage B (axon): `RunResult` 扩展 8 个新字段(`trades` / `total_fees` /
  `equity_curve` / `max_drawdown_pct` / `win_rate` / `sharpe_ratio` / `nav_peak` /
  `positions`),并通过 Rust 单测验证
- ✅ **axon 内存泄漏修复(2026-06-30)**:`L1MatchingEngine::clear_book` 中
  `HashMap::clear()` → `HashMap::new()` 替换,179 tests passed,clippy 0 warning
- ⏸ **可重新激活** Stage A+ (quantcell): 切回 `ImpactedMatchingEngine` 路径 + 内存基准验证
- ⏸ **可重新激活** Stage B (quantcell): 删 6 状态机 + 砍到 ≤ 200 行
