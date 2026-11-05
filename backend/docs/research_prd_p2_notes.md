# AI 研究 P2 局限说明（PRD 补充）

> 仓库内没有独立的 PRD 文件，本文件记录 P2 阶段的已知局限与决策，供 PRD 合并维护。
> 对应的实现细节同步写在 `backend/research/models.py` 与 `backend/research/service.py` 注释里。

## 1. 回放（POST /research/sessions/{id}/trials/{trial_id}/replay）

- 只重跑**评估**：复用原 trial 的代码 + 会话配置里的数据窗口/评估参数，
  走 factor 场景的 `FactorService` → `FactorSandbox`，不另造执行器。
- **LLM 生成不可复现**：`model / prompt_hash / temperature` 只是原样带到新 trial 做 provenance，
  不参与执行；回放行的 `token_used / llm_calls` 恒为 0（没有发起 LLM 调用）。
- **corr(SOTA) 不可重算**：依赖评估当时的最优因子序列，未持久化；回放结果中该值为空，
  对比视图只展示原值并标注“不可重算”。
- 缺字段口径：`symbols / interval` 缺失或原 trial 无代码 → 409；
  缺 `start / end / candle_type / test_ratio / wf_folds` → 200 + `partial=true`，
  明确列出缺失项并按引擎默认值执行，不静默套用。
- 判定一致的口径：IC_IR 差异 ≤ `1e-6` 且样本外标记未变化；差异值如实落库，
  不做“截断成一致”。
- 回放行固定 `loop_idx=0`，不占用正常轮次编号，避免撞
  `(session_id, loop_idx, candidate_idx)` 唯一索引。

## 2. 批量对比（POST /research/sessions/{id}/trials/batch）

- 一次只接受 2–5 条、且必须同属一个会话；重复 id 会 422，跨会话混选按 404 处理。
- 硬门 `unknown` 原样透传，后端不做 pass/fail 归一化，前端显示“无法判定”。
- 代码 diff 只渲染差异片段（相对第一条 trial 的行级 LCS），不整段渲染。

## 3. 事件顺序（多 worker）

决策：**明确降级为“最终一致”，不改 seq 生成机制**。

- `research_events.seq` 直接复用自增主键，代表写库顺序，不是事件发生顺序。
- 正常情况下同一会话只有一个 runner 线程写事件（resume 前的
  `_ensure_no_active_job` + 进程内 Control 约束），单会话内 seq 与发生顺序一致。
- 多 backend 进程同时操作同一会话是异常场景：`job_manager` 是进程内的，跨进程
  看不到对方的 job。此时 seq 仍是全序，但可能与 wall-clock `ts` 出现毫秒级倒挂；
  前端按 seq 增量拉取/排序，得到稳定的最终一致视图，`ts` 仅作参考。
- 不采用 DB 侧 `max(seq)+1` 或会话级锁：两者都只能保证“写入时刻有序”，
  SQLite 下还会把同一会话的所有写串行化，收益不足以抵消复杂度。
- 保留上限：每个会话只保留最近 `EVENTS_RETENTION` 条，不做全量归档；
  若未来迁移到消息队列/流式存储，应以事件表为迁移起点。
