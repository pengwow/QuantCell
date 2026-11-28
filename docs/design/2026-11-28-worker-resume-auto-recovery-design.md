# Worker resume 对账失败自动归档重启（以交易所为准）设计

日期：2026-11-28
状态：已定稿（用户确认）

## 背景与问题

实盘 worker 重启后走 resume 链路：Rust `live_driver.rs` 重演 journal → 与交易所快照对账 →
`resume_guard` 拒绝（持仓/现金差/幽灵单任一存在即 Err）。此时 worker 落 error，
文案为"恢复守卫拒绝继续交易，请人工核对持仓与资金后重试 resume"，必须人工点
「归档」后手动重启。

worker_3 实例（2026-11 报告 `backend/data/live/worker_3.reconcile.json`）表明这类失败
多数是**可自动处置**的：venue 在宕机期间成交而本地 journal 漏记（missing_fills），
现金差 = 手续费 + 资金费（LiveSink 本就不记 funding）。此时 venue 是事实源，
「归档 + fresh start（adopt venue）」本来就是人工路径的正确动作。

## 决策

采用业内「重启即以交易所为准，不搞硬人工门」：

> resume 对账守卫拒绝后，自动归档旧 journal 并以交易所为准 fresh start（adopt）。
> 不做差异归因分级，不改 Rust，不重建 .so。

代价（用户明示接受）：重启前的手工交易/未知动账会被"以交易所为准"静默吸收。
可见性由追加式审计日志 + 频次告警兜住；运行期周期对账（现有）继续作为重启后的兜底。

## 设计

### 触发条件

`backend/worker/strategy_manager.py` 实盘驱动线程（约 L1108 起）resume 调用
（约 L1127 `driver.resume(str(journal))`）抛错时：

- 错误文本以 `恢复守卫拒绝继续交易` 开头（Rust live_driver.rs L445 固定前缀）
  → 走自动恢复；其余启动失败行为不变（落 error 告警）。
- 频次止损未触发（见下）。
- 配置开关 `resume_auto_recovery_on` 为 true（默认 true，与现有 `*_on` 旗标风格一致）。

### 处置序列（全在 Python 侧）

按顺序：

1. 记日志（logger，结构化字段 worker_id / 处置原因 / 报告路径）。
2. best-effort 撤单：尝试撤销该 worker 当前品种的全部在挂单；网关不支持撤单
   或撤单失败 → 记 warn，继续处置（不构成阻断）。
3. 归档：复用 `strategy_manager.archive_journal_files(worker_id)`（L1744），
   journal 与 `.reconcile.json` 一并移入 `archive/` 子目录。
4. 重启：走现有正常 start 路径。journal 已不存在 → 自动 fresh start，
   引擎以交易所持仓 + 基准现金锚定（现有 `existing_positions='adopt'` 机制）。
5. 审计：向 `backend/data/live/worker_{id}.auto_recovery.ndjson` 追加一行
   `{ts, worker_id, verdict:"adopted", reconcile_report}`。
   ponytail：不做 DB 表；追加文件 + 窗口计数足够，升级路径是 worker_state 表。

### 频次止损（仅防 crash loop，非人工确认门）

自动处置前读取 ndjson，24h 滑动窗口内已 ≥3 次 → 本次**不自动**，
worker 落 error + 告警，人工仍可手动点启动。目的：worker 与交易所之间出现
无法收敛的分歧（如共享账户持续被第三方动账）时，不允许系统无限循环归档。

### 前端与文案

- 自动处置成功后推送沿用现有 worker 事件/日志通道，文案如
  「对账不一致，已归档并按交易所为准自动重建」。
- worker 卡片 error 文案仅在止损触发时出现；无须新增路由
  （docs/testing/MANIFEST.md 预计不变，提交前跑 check-coverage 确认）。

### 明确不动

- Rust 侧 `resume_guard` / `live_driver.rs` / `reconcile.rs`：行为代码零改动
  （错误文案仍含"请人工核对"字样，以 Python 侧事件文案为准，Rust 文案改造不属本设计）。
  唯一例外见「风险与边界」：为锁定错误前缀契约补一条 Rust 测试断言（非行为改动）。
- `backend/worker/reconciliation.py`、periodic 对账、LLM replay、RL journal 路径：零改动。
- 漏成交回填重演：不做（历史 PnL 缺口靠 archive 文件可查）。

## 测试计划

- Python 单测（backend/tests/unit/worker/ 或最近似现有目录）：
  1. resume 错误前缀判定 → 触发 vs 不触发；
  2. 处置序列依序发生（mock archive_journal_files / start）；
  3. ndjson 频次达标后不再自动，worker 落 error；
  4. 开关关闭时行为等同现状。
- 手工验证：docs/testing/ 对应页面（实盘 worker）新增验证项 + 历史雷区记录；
  `node docs/testing/check-coverage.mjs` 全绿。

## 风险与边界

- 共享账户/手工交易被静默吸收：由审计文件 + 频次告警兜住可见性（已接受）。
- fresh start 时交易所仍有可能的 ghost 单成交：与现有人工归档路径暴露面相同；
  best-effort 撤单是相对人工路径的增强。事后漂移由运行期周期对账冻结兜底。
- 错误前缀属于 Rust↔Python 的弱契约：Rust 改文案会静默破坏自动恢复，
  在 Rust 测试中加一条断言锁定该前缀（本设计范围内顺带加，不属于行为改动）。
