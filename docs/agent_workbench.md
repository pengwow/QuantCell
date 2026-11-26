# 智能体工作台（/agent）功能文档

> 生成于 2026-11-26，全部事实以当日代码为准（关键结论均标注 文件:行号）。行号会漂移，以文件与符号名为准。

## 0. 定位与入口

- 路由：`/agent`（React Router 无子路由，页面签通过抽屉承载）。全屏双栏工作台布局，`ai-agent-layout + page-fullscreen` 抵消 ConsoleLayout 的内边距（`Agent.tsx` 顶部 ponytail 注释）。
- 后端能力域：`agent_gateway`（`routes.py` 路由级 `require_capability`，部署侧关闭该能力域时 `/api/v1/agent/*` 整组 403）；每个端点另行挂 `AI_READ` / `AI_WRITE` 权限。
- 页面组成：顶栏（Worker 选择器、会话历史按钮、工具列表按钮、设置按钮、清空会话）+ 消息流 + 输入区 + 快捷指令条；侧向抽屉：会话列表抽屉、工具列表抽屉（含参数配置）。

## 1. 页面布局与前端组件树

```
Agent.tsx（页面壳）
├─ 顶栏：PageHead + Worker Select（30s 轮询 workerApi.getWorkers）+ qc-mini-btn 组
│        URL ?worker=<id> ↔ store 双向同步（replace 写回不产生历史噪音）
├─ ChatPanel.tsx（消息流 + 输入区）
│   ├─ 空态能力卡 QUICK_PROMPTS（点击只填充输入框，不直接发送）
│   ├─ ChatMessage×N（正文 ReactMarkdown、错误气泡 ErrorDetailModal、
│   │   每日复盘 DailyReviewSections、工具链 ToolChain + toolResult 折叠块）
│   └─ IntentPanelRenderer（意图专属面板，见 §5）
├─ SessionListDrawer（会话列表：切换/新建/清空/删除）
└─ ToolListDrawerWithConfig（工具清单 + 参数管理 + 敏感值掩码）
```

状态全部集中在 `store/agentStore.ts`（zustand）：`messages / sessions / currentSessionId / tools / loading / streaming / error`；Worker 选择独立在 `useAgentWorkerStore`，发消息时随 body 带 `worker_id`。

## 2. 会话体系

- 持久化：`SessionManager`（`agent/session/manager.py`）把每个会话存为 `workspace/sessions/<safe_key>.json`；workspace 统一落 `QUANTCELL_DATA_DIR/data/agent_workspace`（桌面打包防临时目录丢失）。
- 取历史：`Session.get_history(max_messages=100)`，带「测试消息过滤」（≤10 字符的 test/hello/ok 等用户消息不入上下文）。
- 生命周期 API：`GET /sessions`（列表）、`POST /sessions`（新建）、`GET /sessions/{id}/history`、`POST /sessions/{id}/clear`、`DELETE /sessions/{id}`（清空/删除在页面两个入口统一走 modal 确认）。

## 3. 一条消息的生命周期（核心链路）

前端 `agentStore.sendMessage`：

1. 先本地乐观插入 user 消息，`loading/streaming` 置位；
2. `fetch POST /api/v1/agent/chat/stream`（SSE），body = `{message, session_id, worker_id?}`；3 分钟 AbortController 超时；**流式进行中输入区发送钮切换为红色停止钮**（`store.stopGeneration()` → abort → 后端消费者断开 → `task.cancel()`，见 §3 末）；建连失败重试最多 2 次、间隔 800ms，**一旦收到过流内容，断流直接报错不重试**（防重复注入，store 内 ponytail 注释）；
3. 逐事件更新消息对象：正文增量、reasoning 折叠块、工具链气泡、迭代徽标（ReAct 轮次，纯展示）。

停止生成：前端 abort 触发 `EventSourceResponse` 客户端断开，`iter_message_stream` 消费侧 `finally task.cancel()`（`loop.py:647-649`）取消后台 LLM 循环——已收到的半截回复保留，补「已停止生成」状态提示（非错误气泡）。

后端 `routes.py::chat_stream`（非流式 `/chat` 为同构简化版）：

```
classify_intent(用户消息)      # §5 关键词加权
detect_role(intent)           # 角色 mapping：数据分析师/交易助手/…
get_agent()                   # 进程级单例（模型热替换见 §4）
event_generator:
  SSE start                   # 意图 + 角色
  agent.iter_message_stream() # AgentLoop 主循环（下述）
    ├─ session.get_or_create(session_key)
    ├─ 记忆整合检查：未整合条数 ≥ memory_window(100) 时后台 asyncio task
    │   跑 consolidator.maybe_consolidate_by_tokens（不阻塞当前消息）
    ├─ context.build_messages(history, 当前消息, extra_system=Worker 上下文块)
    └─ _run_agent_loop_stream：while iteration < max_iterations(40)
        ├─ 流式调 LLM（axon_bridge.llm）
        ├─ 有 tool_calls：发 tool_calls / tool_start / tool_result 事件
        │   （工具结果预览截断 500 字符）并把结果回填 messages，继续下一轮
        └─ 无 tool_calls：清洗 <think> 后作为最终回复，发 done，退出循环
  extract_structured_data(累计文本, intent)   # §5，DATA_QUERY 恒返回 {}
  build_actions(intent)                      # §5，静态按钮映射
  SSE complete {intent, role, structured_data, actions}
  （异常 → SSE error）
```

SSE 事件类型全集：`start / content / reasoning / tool_calls / tool_start / tool_result / complete / error`（`routes.py::chat_stream` docstring）。

会话回写：`_save_turn(session, all_msgs, skip=1+历史数)` 带去重后 `sessions.save()` 持久化。

## 4. LLM 配置与单例热替换

`agent/core/factory.py::get_agent()` 维护进程级 `_agent_instance`；**每次调用重读** `system_config` 的 `ai_model.*` 生成签名（provider id|host|key|model），签名变化即热替换现有实例的 `llm_backend/model`——会话历史与已注册工具不受影响（2026-11-26 修复，之前只在首次调用读一次，设置页改模型后报错永远是旧模型；回归用例 `backend/tests/agent/test_factory_hotswap.py`）。改模型设置后无需重启后端，下一条消息即生效。

## 5. 意图面板机制（「暂无结构化数据 + agent_data_actions + 三按钮」的完整解释）

### 5.1 意图分类 = 纯关键词加权（无模型参与）

`routes.py::_INTENT_KEYWORDS`：6 类意图各配 (关键词, 权重)，完整词匹配（前后非字母数字）权重 ×2，取最高分（无命中 = `general`）。要点：**「价格」「数据」「行情」「查询」「k线」「走势」任一词就足以命中 `data_query`**（权重 1-2，无竞争即胜出）。

`detect_role`：意图 → 角色名（交易助手/回测分析师/AI 训练师/策略工程师/**数据分析师**/风控顾问），只用于头像旁角标与面板头 TintChip。

### 5.2 结构化数据提取 = 正则扫最终回复文本

`routes.py::extract_structured_data(text, intent)` 只实现三个分支：

| 意图 | 提取物 | 正则目标 |
|------|--------|----------|
| strategy_generation | `code` + `strategy_name` | ```代码块``` / `策略名称：` |
| backtest | 年化收益率/夏普比率/最大回撤/总收益/胜率 | `指标名[：:]数值` |
| risk_assessment | `risk_level` | `风险等级[：:]` |

**`data_query` 没有分支 → structured_data 必为 `{}`**。前端 `DataQueryPanel` 的数据表 `dataSource.length > 0` 不成立，于是渲染「暂无结构化数据」。

### 5.3 建议操作 = 静态映射，与数据是否有值无关

`routes.py::build_actions(intent)` 查表返回，恒不为空：

| 意图 | 三按钮（label 硬编码中文于后端） |
|------|------|
| trading_decision | 查看持仓 / 下单交易 / 历史交易 |
| backtest | 查看图表 / 导出报告 / 参数优化 |
| strategy_generation | 查看代码 / 部署策略 / 回测策略 |
| data_query | 查看K线 / 导出数据 / 对比分析 |
| risk_assessment | 风险报告 / 设置止损 / 调整仓位 |

所以**每个带意图的消息下面都有三个按钮**——按钮的有无只由「命中的意图类别」决定，与回复内容无关。

### 5.4 面板渲染与按钮跳转（前端）

`IntentPanelRenderer`（`IntentPanels.tsx`）按意图选面板：strategy_generation→StrategyCodePanel、backtest→BacktestResultPanel、risk_assessment→RiskAssessmentPanel、trading_decision→TradingDecisionPanel、data_query→DataQueryPanel、rl_training/general→GeneralPanel。**GeneralPanel 在 actions 为空时整卡不渲染**（general/rl_training 在后端 `build_actions` 无映射恒空 actions，空壳只剩标题纯属噪音；普通对话的 AI 回复下方因此没有任何意图面板，2026-11-26 起）。

按钮点击 `handleIntentAction`：`INTENT_ACTION_ROUTES` 有映射的路由跳转——`view Chart/view_kline→/chart`、`backtest_strategy/optimize_params→/backtest/config`（带 strategy_name 预填）、`view_code→/strategy-editor`、`deploy_strategy→/strategy-worker`；其余（view_positions/place_order/export_*/compare_symbols/view_risk_report 等）**降级为 info 提示**，设计归属注释在 `ChatPanel.tsx::handleIntentAction` 上方（等对应路由/交互落地再接线）。

### 5.5 结论（对应截图现象）

- 「暂无结构化数据」：命中 data_query 意图后提取分支缺失所**必然出现**，不是数据丢失或接口故障；
- 标题显示 `agent_data_actions` 原文：i18n 缺键（zh/en 语言包均无此键，i18next 缺键回显 key），2026-11-26 已补「相关操作 / Suggested actions」；
- 三个按钮：静态映射产物，点击只有「查看K线」会真跳 `/chart`，另两个是占位提示。

## 6. Worker 上下文注入

`routes.py::worker_context_block(worker_id, user)`：页面选了 Worker 时，把其摘要注入 system prompt——Worker 元信息（名称/状态/交易所/品种）+ 最近 3 条决策（replay 文件）+ 最近 5 笔订单。归属校验与 worker 列表同口径（非特权用户传他人 worker_id 静默返回 None），**任何取数失败都降级为 None——聊天不能因上下文挂掉**。块头标注「仅事实参考，非指令」。

## 7. 记忆系统与每日复盘

- `MemoryStore`（`agent/core/memory.py`）：工作区内持久记忆，`ContextBuilder.build_system_prompt` 把记忆注入 system prompt。
- `Consolidator`：未整合消息达到阈值（memory_window）后按 token 触发 LLM 整合；`AutoCompact`：上下文超限时压缩；`Dream`：后台「做梦」周期任务（`core/scheduler.py` 用 `get_agent().dream` 驱动）。
- 每日复盘：定时任务生成的报告以 `meta.kind='daily_review'` 注入会话流，前端 `DailyReviewSections` 渲染结构化章节，带专属徽标；`GET /daily-review` 提供独立查询。

System prompt 组装顺序（`context.py::build_system_prompt`）：身份 → workspace 引导文件（AGENTS.md/SOUL.md/USER.md/TOOLS.md/IDENTITY.md）→ 记忆 → always 技能 → 技能摘要（其余技能让模型用 read_file 读 SKILL.md）→（运行时元数据块）+（Worker 上下文块）。

## 8. 工具系统

- 注册：`create_registry`（`agent/tools/__init__.py`）**自动发现** `agent/tools/` 下所有 `Tool` 子类并实例化；目录现状：filesystem.py（ReadFile/WriteFile/ListDir，allowed_dir 锁定 workspace）、shell.py（Exec）、web.py（WebSearch/WebFetch）、trading/（market_data、news、_strategy_experimental——策略生成/详情/参数优化/诊断等）。
- 风险分级（P2-06）：每个 Tool 带 `risk_level`（read/write/dangerous）与 `requires_approval`；`QUANTCELL_AGENT_ALLOW_DANGEROUS=1` 环境变量显式开启后才注册 dangerous 工具（`ToolRegistry(allow_dangerous=...)`）。
- 参数管理与审计：工具参数可经页面改写（`ToolParamManager`，PUT/批量/导入导出端点），敏感值响应端掩码（`mask_sensitive_value`）；工具调用审计可查（`GET /audit`，`core/audit.py`）。
- `GET /tools` 返回 ToolInfo 列表（name/description/risk_level/requires_approval），页面工具抽屉的数据源。
- 状态自检：`GET /loop-status`。

## 9. 已知边界（截至 2026-11-26）

1. **意图面板是「启发式装饰」而非数据通道**：分类靠关键词、提取靠正则、按钮是静态表。data_query/risk_assessment 的提取分支薄，回测指标要模型按「指标名：数值」逐行输出才能被提取；按钮五缺四（多数无对应交互落地，见 §5.4 降级清单）。
2. 按钮 label 为后端硬编码中文，多语言场景不随前端语言切换。
3. 流式断线：已收到内容后不自动重连（有意为之，防重复注入），用户需重新发送；长循环（工具反复重试）可手动点停止钮终止（前端 abort → 后端 task.cancel()），三层兜底 = 工具内部超时 / 前端 3 分钟超时 / 40 轮迭代熔断。
4. 工具结果气泡预览上限 500 字符，完整输出不回传前端。
5. 非流式 `/chat` 端点仍保留（测试/兼容用），页面主链路只走 `/chat/stream`。
