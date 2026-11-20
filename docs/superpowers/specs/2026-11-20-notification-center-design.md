# 消息中心优化设计：异步任务通知闭环 + 统一通知封装

日期：2026-11-20
状态：已评审通过（方案 A：任务终态埋点 + 统一通知 Hub）

## 1. 背景与目标

用户触发回测、RL 训练等长耗时异步任务后切换页面，任务完成/失败/异常终止时无任何提醒，用户需要自己回到对应页面翻找结果，甚至遗忘任务存在。本设计建立站内通知闭环：任务终态自动推送站内通知，点击直达任务详情页。

**目标**：

1. 任务终态（成功/失败/异常终止）自动推送站内通知，覆盖全部五类长耗时任务
2. 通知支持点击跳转至任务详情页
3. 通知状态管理：单条已读 + 已处理/待处理
4. 统一通知封装模块，新任务类型低成本接入
5. 进程重启导致的异常终止可补偿补发通知

**明确不做**（边界）：

- 不发通知的场景：用户主动 stop/cancel（本人操作）；任务开始/进度事件（进度由现有页面轮询/WS 承担）；同步接口（请求-响应天然可见）
- 不统一五类任务的状态机与存储（方案 C，长期方向，见 §8）
- 不改用户体系：维持单管理员共享收件箱（无 user_id 隔离），与现状一致

## 2. 现状评估与缺失点

**已具备**：

- 后端 `common/notifications/`：`NotificationService.send_notification` 统一入口，投递前落库收件箱（[service.py:229](../../../backend/common/notifications/service.py)），渠道含 email/企微/飞书/WebSocket（[channels.py](../../../backend/common/notifications/channels.py)）
- 收件箱：SQLite `notifications` 流水表 + `notification_state` 全局已读水位单行表（[inbox_models.py](../../../backend/common/notifications/inbox_models.py)）
- 前端：铃铛组件（NotificationInbox）+ `/notifications` 收件箱页（游标分页/全部已读/删除），WS 实时桥 NotificationBridge（[App.tsx:198](../../../frontend/src/App.tsx)）已实现 toast + 未读数增量
- 唯一真实通知来源：指标信号提醒循环（core/lifespan.py）

**缺失点**：

| # | 缺失 | 影响 |
|---|------|------|
| 1 | 五类异步任务终态均不产生站内通知（`record_inbox_notification` 无任何任务回调调用） | 核心痛点：任务完成后无感知 |
| 2 | `notifications` 表无 task_type/task_id/detail 字段 | 通知无法关联任务、无法跳转 |
| 3 | 只读状态只有全局 id 水位（`notification_state.last_read_id`） | 无单条已读、无已处理/待处理 |
| 4 | RL 训练任务纯内存 registry（进程重启即丢）、因子 job 同样纯内存 | 异常终止时无从发通知 |
| 5 | 前端通知条目点击无任何行为 | 通知与任务页面割裂 |

**任务状态存储现状**（五种范式）：回测（内存 tracker + `backtest_tasks` 表 + JSON 文件，routes UUID 与 service 内部 ID 双轨）、RL（纯内存，queued→running→done/failed/cancelled，全局并发=1）、因子（内存 dict + 事件流）、采集（`TaskBusiness` 落库 + 启动重载）、研究（`research_sessions` 等三表落库 + 多进程租约心跳）。

## 3. 场景清单与通知内容规范

| # | 场景 | 触发时机 | level | 标题模板 | 跳转目标 | 埋点位置 |
|---|------|---------|-------|----------|----------|----------|
| 1 | 回测完成 | 后台线程成功终态 | success | 回测完成：{symbol} {strategy} | `/backtest/detail/{task_id}` | backtest/routes.py `run_backtest_async` 收尾 |
| 2 | 回测失败 | 后台线程异常终态 | error | 回测失败：{symbol} {strategy} | 同上 | 同上 |
| 3 | RL 训练完成 | train async 终态 done | success | RL 训练完成：{model_id} | `/model-hub?tab=train` | rl_task_runner 终态处 |
| 4 | RL 训练失败 | failed | error | RL 训练失败：{model_id} | 同上 | 同上 |
| 5 | 因子计算完成/失败 | FactorJobManager job 终态 | success/error | 因子计算完成/失败 | `/factor-analysis` | factor/job_manager.py 终态处 |
| 6 | 数据下载完成/失败 | TaskManager 收口函数 | success/error | 数据下载完成/失败：{task_type} | `/data-management` | collector/utils/task_manager.py `complete_task`/`fail_task` |
| 7 | 研究会话完成/失败 | 会话终态 | success/error | 深度研究完成/失败：{session.name} | `/research/{id}` | research/loop.py 终态处 |
| 8 | 任务中断（补偿） | 服务重启扫描发现僵尸任务 | warning | 任务已中断（服务重启）：{title} | 对应详情页 | 五个模块的 `compensate_interrupted_tasks()` |
| 9 | 指标告警 | 已有 alert 循环 | 按规则 | 不变 | 暂无 | 现状保留 |

**内容规范**：

- `content`：一行结果摘要；失败/interrupted 附错误原因（截断 ≤200 字符）
- `detail`（JSON）：耗时、关键指标（收益/Sharpe/epoch 等）、跳转所需附加参数
- `task_id` 口径 = 前端详情页路由参数：回测用 routes 层 UUID（backtest_tasks.id 同口径），研究用 session_id，RL 用 task uuid
- 手动 stop/cancel 不发通知（用户在页面上主动操作，无信息增量）

**幂等约定**：通知埋点必须有单一出口（如回测收在 `run_backtest_async` 一处，不散落 service 内部多个终态分支）；RL/因子走影子表状态机（终态 UPDATE 仅在状态仍为非终态时生效）兜底防双发。

## 4. 数据结构设计

一个 alembic migration，两件事：

### 4.1 `notifications` 表扩展（改 backend/common/notifications/inbox_models.py）

```python
class InboxNotification(TimezoneAwareBase):
    # 现有 id/title/content/level/source/created_at 保留
    task_type = Column(String(30), nullable=True)    # TaskType 枚举值；NULL=非任务通知
    task_id   = Column(String(64), nullable=True)    # 跳转目标 ID，口径=详情页路由参数
    detail    = Column(Text, nullable=True)          # JSON：结果摘要、错误原因、附加参数
    read_at       = Column(DateTime(timezone=True))  # NULL=未读；替代全局水位
    processed_at  = Column(DateTime(timezone=True))  # NULL=待处理；仅任务类通知有处理态
```

- 存量数据 `read_at = created_at`（视为已读，不惊扰老通知），`processed_at` 保持 NULL
- `notification_state` 水位表停用不删（避免破坏性迁移），在迁移文件中注明
- 未读判定 = `read_at IS NULL`；「全部已读」= 批量 UPDATE 置 `read_at=now()`（保留既有「水位只前进」语义：已处理不接受全部已读覆盖，`processed_at` 不受影响）；「清空已读」= DELETE `WHERE read_at IS NOT NULL`；单曲删/分页接口签名不变

### 4.2 新增 `async_tasks` 影子表

只为 RL 训练、因子计算两类纯内存任务提供重启持久化（其余三类已有自己的表）：

```python
class AsyncTaskRecord(Base):
    __tablename__ = "async_tasks"
    task_id   = Column(String(64), primary_key=True)   # 与各模块任务 ID 同口径
    task_type = Column(String(30), nullable=False, index=True)
    status    = Column(String(20), nullable=False, index=True)  # queued/running/succeeded/failed/interrupted
    title     = Column(String(200), nullable=False, default="") # interrupted 补偿时组装通知用
    detail    = Column(Text)                                    # JSON
    created_at / updated_at
```

RL 在 `services/rl_task_runner.py::submit_train_task`、因子在 `factor/job_manager.py::FactorJobManager.submit` 时写一行；状态翻转时同步更新。**内存 registry 仍是运行时权威（SSE 订阅链路不动），DB 只是生命周期影子。**

## 5. 模块架构

### 5.1 统一通知 Hub：`common/notifications/task_notices.py`（新文件）

```python
class TaskType(StrEnum):
    BACKTEST = "backtest"; RL_TRAIN = "rl_train"; FACTOR = "factor"
    DATA_DOWNLOAD = "data_download"; RESEARCH = "research"

class TaskOutcome(StrEnum):
    SUCCEEDED = "succeeded"; FAILED = "failed"; INTERRUPTED = "interrupted"

def notify_task_event(
    task_type: TaskType, task_id: str, outcome: TaskOutcome,
    title: str, content: str = "", detail: dict | None = None,
) -> None: ...
```

内部流程：

1. 落库（record_inbox_notification 扩展版，带 task 字段，read_at=None）
2. WebSocket 推送 `type=notification`（复用现有 WebSocketChannel → 前端 toast + 铃铛即时可见，payload 带任务元数据）
3. `FAILED`/`INTERRUPTED` 额外通过 `NotificationService` 走设置页已启用的外部渠道（邮件/企微/飞书——坏消息值得离开站内）

约束：同步函数，可在任务线程直接调用（复用 websocket manager 的线程安全 queue_message 与 use_db_session）；任何一步失败只记日志不抛出（通知不拖垮任务主流程）。

### 5.2 启动补偿

依赖方向单向：`任务模块 → task_notices → (inbox + channels)`。Hub 不 import 任何任务模块；补偿查询分散到各任务模块：

各任务模块暴露 `compensate_interrupted_tasks() -> list[补偿通知载荷]`（查各自的表 → 僵尸非终态行标 `interrupted` → 返回载荷），`core/lifespan.py` 启动时逐个调用后统一 `notify_task_event`。标注 `interrupted` 的目标存储：回测 `backtest_tasks`（status∈pending/running → interrupted）、采集 `TaskBusiness`（同步内存 dict）、研究 `research_sessions`（非终态且 heartbeat 超阈值，防多进程误杀；终态集合以 research 模块实际写入值为准，实施时核实）、RL/因子 `async_tasks`（status∈queued/running）。

```mermaid
flowchart LR
    subgraph 任务模块（各 1~3 行埋点）
        BT[backtest routes<br/>run_backtest_async]
        RL[rl_task_runner]
        FC[factor job_manager]
        DL[collector task_manager]
        RS[research loop]
    end
    subgraph common/notifications
        HUB[task_notices.notify_task_event]
        INBOX[inbox.py / inbox_models.py]
        CH[channels: WebSocketChannel<br/>+ 外部渠道]
    end
    subgraph 启动补偿（core/lifespan.py）
        COMP[五模块 compensate_interrupted_tasks]
    end
    subgraph 前端
        TOAST[NotificationBridge toast onClick 跳转]
        BELL[NotificationInbox 铃铛]
        PAGE[InboxPage /notifications]
    end
    BT & RL & FC & DL & RS --> HUB
    COMP --> HUB
    HUB --> INBOX
    HUB --> CH
    CH --> TOAST & BELL
    BELL & PAGE & TOAST -->|点击 navigate| TASKPAGES[任务详情页]
    BELL & PAGE -->|POST /inbox/id/read| INBOX
```

### 5.3 收件箱 API 扩展（common/notifications/routes.py）

- 新增 `POST /notifications/inbox/{id}/read`：置 `read_at`；任务类（task_type 非空且 processed_at 为空）同时置 `processed_at`。点击跳转 = 已读 + 已处理一次完成
- `GET /inbox` 增加过滤参数：`task_type`、`unread`（bool）、`pending`（bool，待处理）；返回项在时间戳列之外附 `read`/`processed` 布尔字段（由 `read_at`/`processed_at` 派生，前端不做时间戳判空）；删除接口保留

## 6. 前端设计

### 6.1 路由映射注册中心（新文件 `frontend/src/tasks/taskRoutes.ts`）

```typescript
// 新任务类型接入点：注册一个 builder 即获得点击跳转能力
export const TASK_ROUTE_BUILDERS: Record<string, (id: string | null, detail?: Record<string, unknown>) => string> = {
  backtest: (id) => `/backtest/detail/${id}`,
  rl_train: () => `/model-hub?tab=train`,
  factor: () => `/factor-analysis`,
  data_download: () => `/data-management`,
  research: (id) => `/research/${id}`,
};
```

### 6.2 改动点（均为增量）

1. 类型 + [notificationStore](../../../frontend/src/store/notificationStore.ts)：`InboxNotificationItem` 增加 `task_type/task_id/detail/read/processed`；新增 `markRead(id)` action 与 `filter` 状态
2. `InboxItemRow`（铃铛下拉与收件箱页共用组件，[NotificationInbox.tsx](../../../frontend/src/components/NotificationInbox.tsx)，改一处两处生效）：任务类条目整行可点击 → `markRead(id)` + `navigate(route)`；未读条目视觉标记微调
3. [NotificationBridge](../../../frontend/src/App.tsx) toast 加 `onClick`：任务类点击 toast 同样跳转
4. 收件箱页顶部过滤 Segmented：`全部 / 未读 / 待处理`
5. i18n 文案 key；同步更新 `docs/testing/pages/` 验证文档并保持 `check-coverage.mjs` 全绿

## 7. 实现步骤与验收标准

### 实现步骤概要

1. DB 迁移（notifications 扩列 + async_tasks 建表 + 存量回填）
2. inbox 读写改造（单条已读/过滤/对齐 read_at 语义）+ routes API 扩展
3. `task_notices.py` Hub + 单测
4. 五处埋点（RL/因子含影子表写入）
5. 五个 `compensate_interrupted_tasks()` + lifespan 挂载
6. 前端（taskRoutes 注册中心 / store / 点击跳转 / 过滤 / toast onClick）
7. 测试（pytest 单测 + bun run build）+ docs/testing 验证文档更新
8. 新任务类型接入指引（追加到本文件 §10）

### 验收标准

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | 闭环：触发回测→切走→完成后铃铛红点+toast→点击直达详情页→条目已读+已处理 | 浏览器手工 + Integration 测试 |
| 2 | 异常：RL 训练中 kill 后端→重启→收到「已中断」warning→可点击跳转 | 手工演练 + 补偿单测 |
| 3 | 失败通知 content 含错误原因摘要 | 单测断言 |
| 4 | 兼容：存量告警通知行为不变；全部已读/清空已读/删除正常 | pytest 单测（覆盖水位 watermark 替换后的语义等价性） |
| 5 | 可扩展：新任务类型接入 = 后端 1 处埋点 + 前端 1 个路由映射条目 | 接入指引可用性 |
| 6 | 门禁：`uv run pytest tests/unit/notifications/ -q` 全绿；`bun run build` 通过；`node docs/testing/check-coverage.mjs` 全绿 | CI/本地 |

## 8. 演进方向（本次不实施）

- 方案 C（统一 TaskRegistry 根治五类任务存储范式分裂）作为长期方向保留
- 通知模型可外扩：user_id 隔离、多租户、「已处理」分化为显式确认动作（当前点击即处理）
- 铃铛可增加分类分栏/汇总视图（当前仅预留 task_type 字段与过滤参数）
- 指标告警补跳转（股价上下文 DataGridView → 具体指标页）

## 9. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 通知落库/推送失败拖垮任务主流程 | Hub 内部 try/except 全量吞错只记日志（与现 record_inbox_notification 一致） |
| 迁移把存量通知误标未读 | 回填 read_at=created_at；迁移前备份由用户自行决断（单管理员自部署） |
| 重启补偿误判多进程在跑的研究会话 | heartbeat 阈值（默认 10 分钟）判定 |
| toast 风暴（批量因子任务） | toast 依赖现有 antd notification 队列；Hub 不做合并（与 WS manager「不同 topic 不做同 topic 合并」的现状一致，见 websocket/manager.py 注释） |
| 双击/并发点击导致重复接口调用 | 单条 read 接口幂等（已读再置同值无副作用） |
| 回测详情页对 failed 任务可能缺渲染 | 实施时验证 `/backtest/detail/:id` 对失败任务的展示；若不支持，失败通知跳转回退 `/backtest` 列表页（在 taskRoutes builder 内以 detail 参数区分） |

## 10. 新任务类型接入指引

后续新增业务场景接入站内通知，共三步，无需改动通知模块本身：

1. **后端埋点**：任务终态出口处调用
   `notify_task_event(TaskType.新类型, task_id, TaskOutcome.SUCCEEDED/FAILED, title, content, detail)`
   - `TaskType` 枚举在 `common/notifications/task_notices.py` 增加一个成员
   - 若该任务是纯内存生命周期，提交/状态翻转时同步写 `async_tasks` 影子表，并提供 `compensate_interrupted_tasks()` 挂入 lifespan（有落库的任务只需提供该函数扫自己的表）
2. **前端跳转**：`frontend/src/tasks/taskRoutes.ts` 的 `TASK_ROUTE_BUILDERS` 增加一条 `task_type -> 路由` 映射
3. **文案**：i18n 增加通知标题所需 key；`docs/testing/pages/` 若新增页面路由则在 MANIFEST 登记

不需要：改通知表结构、改收件箱接口、改铃铛/收件箱组件、重写已读逻辑。
