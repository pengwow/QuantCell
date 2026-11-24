# demo ↔ 现网 对齐差距清单

> 基准：`docs/design/qc-prototype-demo.html`（下称 demo）为唯一视觉/信息架构基准。
> 现网证据一律给 `文件:行`；demo 证据给行号。
> 本清单只记**可验证差异**，不是待办工单——每项标了数据可行性，落不落地由优先级决定。
>
> **2026-11-22 复检**：第一轮（11-21）的「已落地」项已逐条回验；本版**只保留当前仍存在的差距**，
> 已对齐项折叠为每页末尾一行「已消项」，防止下一轮重复审计。复检同时推翻了旧清单 3 处「无源」误判
> （见「旧判修正」），它们是当前性价比最高的一批活。
>
> **2026-11-23 A 档落地**：把「纯前端/后端已就绪」那一批一次清完（agent 逐节点耗时 + 每日复盘渲染、
> backtest 15s 轮询 + 详情 failed 块 + LLM 不降级文案、strategy 预选首行/版本 0 条/时间格式/AI chip、
> worker 详情「停止」+ 持仓事实条 + 已暂停筛选 + 返回钮、model-hub 双闸 + 重训台账 + 新建训练、
> chart OHLC 条 + MA 图例、research 双入口转回测 + 深链 + 结论卡 + Top5、home 研究卡脚注）。
> 唯一**判定翻转**：worker「暂停/继续」不是前端缺口——后端根本没有 pause/resume 路由，已移入 B 档。
> 
> **2026-11-23 demo 策略智能体页修订**：审计发现该页 demo 本身不合理，先改 demo 再谈对齐：
> 主从同屏拆成「列表页 + 详情页」两视图（对齐现网 `/strategy-worker` 与 `/:id` 两路由）；
> 删掉无后端的「暂停/继续」；删掉用于 worker 的 ReAct 步进器 + 工具链（那是 `/agent` 的语义，
> worker 产出的是逐 bar `Action`，不是工具调用）；「今日 pnl」改回现网真实的「累计盈亏」；
> 详情页签改为真实六页签（总览 / 交易 / 决策 / 风控 / 参数 / 日志），总览用
> `stats/overview + positions` 的真字段，决策页签改成录制行 + `s1_raw / s2_thinking` 展开。

## 口径

| 标记 | 含义 |
|---|---|
| `已有` | 接口/表/SSE 事件里现成字段，补 UI 即可 |
| `需聚合` | 要 join/取最新/补一个透传字段（写明了源表与字段），不造数 |
| `无源` | 当前系统算不出 → **只允许省略或显示「—」，不得编造** |
| 刻意增量 | 现网比 demo 多的能力（行内摘要卡、权益曲线、卡片视图、类型筛选、版本历史列表等），**不算差距**，后续审计勿重复计 |

「反缺口」：现网有、demo 无的件，列在每页末尾，避免下一轮误当成缺失去补。

## 旧判修正（2026-11-22 复检发现旧清单判错）

| 旧判 | 复检结论 | 证据 |
|---|---|---|
| `/agent` 工具节点耗时「无源」 | **有源**：SSE `tool_result` 已带 `elapsed`，前端消费时丢弃 | `backend/agent/core/loop.py:432` → `frontend/src/pages/agent/store/agentStore.ts:312-318`（注释自己写着 `{name, result, elapsed}`） |
| `/agent` 定时任务入会话流「需产品决定」 | **后端已定案并落地**：每日复盘写入 default 会话且 history 带 meta；缺的只是前端识别 | `backend/agent/core/daily_review.py:423-443`、`backend/agent/api/routes.py:543-548`；前端 `agentStore.ts:577-594` 丢 meta |
| `/strategy-worker` 决策「reasoning 无源」 | **部分有源**：`s1_raw / s2_raw / s2_thinking` 随决策详情返回 | `frontend/src/types/backtest.ts:218-229`；逐轮 ReAct rail / tool trace 仍无源 |
| `/model-hub` 双闸状态、重训台账「需聚合」 | **端点已存在**，`/agent` 页已在消费，模型中心未接 | `backend/api/rl_routes.py:373-392`（candidates/pending_promotions/promotions + 双闸） |
| `/research` 一键转回测「无源」 | **已实现**，但粒度与 demo 不同（trial 行内直发任务，非会话级「生成可调配置」） | `backend/research/routes.py:382-464`、`ResearchDetail.tsx:479-505` |
| `/strategy-management` 版本历史「无源」 | **已实现**：快照表 + `/versions` + overview `version_count` | `backend/strategy/models.py:84-98`、`routes.py:87-105` |
| `/backtest` 订单列「需聚合（metrics.total_trades）」 | **口径暗差**：该值是 fills 成交笔数，不是含撤单的订单数；引擎已算 `orders_accepted/rejected`，只是 formatter 没注入 | `result_formatter_service.py:524-526` vs `engine_service.py:1351-1352` |

## 复检总览（数值为 2026-11-23「A 档纯前端」落地后的余量）

| 页 | 仍缺（条） | 其中「纯前端/后端已就绪」 | 最刺眼 |
|---|---|---|---|
| `/home` | 3 | 1 | 运行中行的「今日 +%」仍是累计 USD（需按 worker 拆 24h） |
| `/chart` | 1 | 0 | 副标口径项建议按现网真值裁（时区可切换 / WS 延迟无源） |
| `/agent` | 4 | 2 | ReAct 步进卡仍只有「迭代 X/Y」徽标；工具参数仍裸 JSON |
| `/strategy-worker` | 0 | 0 | 已全部落地（列表三列 + paused 计数 + 行点击进详情） |
| `/strategy-management` | 1 | 0 | footer「默认 runner：kernel」是硬编码 |
| `/strategy-editor` | 0 | 0 | 已全部落地 |
| `/backtest`(+detail) | 4 | 2 | 订单列口径不符（值是 fills）；详情配置卡缺手续费/runner |
| `/backtest/config` | 3 | 1 | 参数只读行需后端扩标记；预计 bar 数仍是纯前端估算 |
| `/factor-analysis` | 5 | 2 | 半衰期列；副标样本/IC 口径未落 |
| `/research`(+detail) | 3 | 0 | 列表摘要 ic/cov 与研究员署名需后端补两字段 |
| `/data-management` | 6 | 1 | kline 水位卡没有补齐入口；最新 bar 只到日粒度 |
| `/model-hub` | 4 | 1 | 关联 worker / shadow 战绩需聚合；常驻详情块仍走 Drawer |

## 无 demo 基准的页面（不当缺失）

`/login`、`/notifications`（InboxPage）、`/model-management`、`/setting/*`（9 个子页）、`/backtest/replay/:id`。
其中 `/backtest/replay/:id` 与 `/data-management/market-replay` 是现网自有的回放能力，demo 无对应视图。

## 页面地图

| demo view（行） | 现网路由 | 组件 |
|---|---|---|
| `#view-home` 814 | `/home` | `pages/home/HomePage.tsx` |
| `#view-agent` 1451 | `/agent` | `pages/agent/Agent.tsx` + `components/` |
| `#view-sagent` 942 | `/strategy-worker` | `pages/worker/Worker.tsx` |
| `#view-sagent-detail` 1080 | `/strategy-worker/:workerId` | `pages/worker/WorkerDetail.tsx` |
| `#view-strategy` 1679 | `/strategy-management` | `pages/strategy/StrategyManagement.tsx` |
| `#view-strategy-editor` 2232 | `/strategy-editor`、`/strategy-editor/:name` | `pages/strategy/StrategyEditor.tsx` |
| `#view-backtest` 1213 | `/backtest`、`/backtest/detail/:id` | `pages/backtest/BacktestList.tsx`、`BacktestDetail.tsx` |
| `#view-backtest-config` 2292 | `/backtest/config` | `pages/backtest/BacktestConfig.tsx` |
| `#view-charts` 1732 | `/chart` | `pages/chart/ChartPage.tsx` |
| `#view-factors` 1770 | `/factor-analysis` | `pages/factor/…` |
| `#view-research` 1890 | `/research` | `pages/research/ResearchList.tsx` |
| `#view-research-detail` 2281 | `/research/:id` | `pages/research/ResearchDetail.tsx` |
| `#view-data` 1967 | `/data-management`、`/data-management/market-replay` | `pages/data/DataManagementPage.tsx`、`KlineReplayPage.tsx` |
| `#view-models` 2050 | `/model-hub`（4 页签） | `pages/model/ModelHub.tsx` + `components/` |

---

## 1. 首页 `/home`（demo 821–946）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 运行中任务行右侧「今日 +x.xx%」 | 879/886/893 | `HomePage.tsx:530-537` 仍是累计 `total_profit` USD | `需聚合`：单 worker 24h 已实现盈亏 ÷ 配置资金；`/workers/stats/pnl-overview` 只有全局合计，需按 worker 拆 |
| KPI4 副标研究分布 | 863-864 | `HomePage.tsx:442-443`「N 个进行中」 | `需聚合`：demo 的分类轴（因子/参数扫描/实验）不存在，只能按现网 `scenario`（factor/strategy/model）出分布 |
| 最近研究卡脚注（说明行 + 「打开研究页 →」） | 943 | `HomePage.tsx:757` 卡底无 foot（回测卡有 `:680-692`） | `已有`：照抄回测卡形态；但 demo 正文提「一键转回测」需改写（会话级入口仍缺） |
| KPI 区 cap 小标签（如「快捷操作」） | 828 | `PageContainer.tsx:46-68` actions 只有钮组 | `已有`（纯文案标签） |

**已消项**：KPI2 今日盈亏 %+较昨日同期（`HomePage.tsx:402-417`）、KPI1 状态分布（`:387-393`）、KPI3 回测分布（`:428-433`，服务端 total）、回测行「区间·周期」（`:658-661`）、回测卡脚注（`:680-692`）、**研究卡脚注**（`HomePage.tsx:758-770`，`home_research_foot` + 「策略研究」链接）、系统卡四行形态（`:574-601`，指标内容仍为运维项）。

**反缺口**：运行中行直达 `/strategy-worker/:id`（`:490`）、三卡空态带动作钮、底部快速操作卡。

## 2. 行情图表 `/chart`（demo 1732–1768）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 页头副标「UTC 时区 · WS 延迟 <1s」 | 1736 | `ChartPage.tsx:654`「币安 USD-M · 数据模式」 | **建议不改**：时区是现网可切换的真设置（ChartTimezoneModal），写死 UTC 反而不真；WS 延迟 `无源` |

**已消项**：页头现价块（品种 · UTC 收盘时间 · 22px mono 价 · 涨跌 chip）、删除「切换品种/刷新」两钮（切品种走图卡顶栏，见 `ChartPage.tsx:656-658` 注释）、品种切换形态、周期档位（现网 11 档超集）、**OHLC 十字光标联动条**（`components/chart/OHLCStrip.tsx`，图卡正下方，默认末根 / hover 跟随 / 移出回末根 / 两档窄屏降级）、**常驻 MA 图例 chips**（`ChartShell.tsx` 图例 useMemo + `ChartPeriodBar` `indicatorLegend`，按活跃指标真实线色渲染，无指标整区不渲染；未照 demo 字面写死 MA7/MA14——现网 sma 单 length 默认 MA20）。

**反缺口**：全套图工具栏（指标/预警/时区/设置/截图/全屏/实时开关）、订单簿 + 成交流水 + 回测成图标记、品种搜索弹窗。

## 3. 智能体工作台 `/agent`（demo 1369–1595）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| ReAct 步进卡（rail + 容量条 + SSE 计数 + iter-next） | 1414-1446、1490-1493 | `ChatPanel.tsx:196-206` 只有「迭代 X/Y」徽标；SSE `iteration_start`/`complete` 在（`agentStore.ts:262,322-337`） | `需聚合`（前端可做计数/容量条；demo 的步骤命名 `无源`） |
| 工具节点参数摘要 + 展开体 | 1460-1488 | `ChatPanel.tsx:128-149` 参数裸 `JSON.stringify`，结果另有折叠块 `:239-243` | `已有`（参数摘要是前端提取，非后端字段） |
| 「转回测验证」预填 | 1506 | `ChatPanel.tsx:167-174` 只 `navigate('/backtest/config')` | `已有`（策略名/参数可带 state 预填） |
| 迭代足迹口径 | 1528-1553 | `FirstScreenCards.tsx:39-110` 当前会话逐条回复、x 轴为时刻；demo 是近 12 天按日聚合 | `需聚合`（跨会话按天需 audit 聚合；history 不带 iteration，落地时已声明降级） |

**已消项**：页头（会话 id / 单轮上限 / 两个跳转钮，`Agent.tsx:220-237`）、右栏首屏「迭代足迹 + Dream」两卡（`FirstScreenCards.tsx:39-243`）、Dream 倒计时（`:144-146,229-236`）、**工具节点逐节点耗时**（SSE `tool_result.elapsed` 按 `data.name` 回填到 `toolCalls[i].elapsed`，`agentStore.ts:391-414` → `ChatPanel.tsx:155-167`，无值不渲染）、**每日复盘结构化入流**（history 保留 `meta`，识别 `meta.kind='daily_review'` → 出处 chip「定时任务 · 每日复盘」+ 按 `report.sections` 渲染概览/Worker/异常/风控/模型，空节跳过）。

**反缺口**：Worker 选择器 + 状态 chip、`?tab=&worker=` 持久化、工具参数抽屉、删除需输确认词、自迭代每日闭环、意图面板。

## 4. 策略智能体 `/strategy-worker(+/:id)`（demo 942–1211）

> demo 已在 2026-11-23 修订为 `#view-sagent`（列表）+ `#view-sagent-detail`（详情）两视图，
> 与现网两路由一一对应；同批差异已全部落到现网（见下「已消项」），本节暂无未消差距。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| —（无未消项） | — | — | — |

**已消项（2026-11-23）**：
- 列表列形制：名称后弱化 `#id`、独立「类型」chip（rule=info / rl=pri / 缺字段 `—`）、「运行时长」列（running 算到当前，有 `stopped_at` 算定值，其余状态 `—`，纯前端，`frontend/src/pages/worker/workerRuntime.ts`）。
- 页头副标与「总任务」卡副标补「已暂停」计数，四项状态之和 = 任务数（`wt_sub_list` / `wt_kpi_sub_tasks` 增 `paused` 占位符）。
- 决策页签行点击进详情：整行点击与操作列「详情」同效（打开既有四页签抽屉，不另建渲染路径），`_seq` 为空的行不响应。
- 卡片视图类型 chip 改读 `strategy_info.strategy_type` 兜底（此前根层 `strategy_type` 为空导致卡片无类型 chip）。
- 主从同屏 → 两路由；详情「暂停/继续」→ demo 已删（后端无路由，前端也不该有）；「今日 pnl」→ 改回真实「累计盈亏」；ReAct 步进器 + 工具链 → 从 worker 页移除（`/agent` 保留）。

**反缺口**：六个页签全部可用（demo 只画总览 / 决策，其余标「原型未包含」）、8 张 KPI 卡（demo 总览 5 项）、批量子集操作、列表/卡片双视图、行内启停、分享/归档弹窗、URL 直达详情。

**本轮发现的 demo 定性问题（已修，记档防复发）**：
- 策略智能体不是 ReAct 智能体：worker 的「决策」是逐 bar 的 `Action(action_type, confidence, target_position)` 加 cascade 录制行，**没有工具链、没有迭代上限**——把 `/agent` 的步进卡搬过来会误导实现方向。
- 后端只有 `start / stop / restart`，demo 里任何「暂停 / 继续」都是无源件。
- worker 列表页与详情页的数据密度（订单表、持仓表、日志）放不进 296px 侧栏，主从同屏只能承载「决策预览」，与现网六页签详情互斥。

## 5. 策略管理 `/strategy-management`（demo 1597–1730）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 首屏不预选首行（详情块空转） | 1630 + 1716 | `StrategyManagement.tsx:62` 初值 `''`，`:657` null 直接返回 | `已有`（首载后默认取第一行 name；hint 文案「点击行查看参数详情」冷启动时无从兑现） |
| 版本 0 条时 footer 整段消失 | 1727 | `:688-702` 仅在 `versionCount > 0` 渲染 | `已有`（0 时渲染禁用态文案，与 demo「版本历史 0 条」语义一致） |
| footer「默认 runner：kernel」硬编码 | 1727 | `:667` 写死常量；现网 runner 可真切换 kernel/legacy/python | `需聚合`（源 `engine_config['runner']`，回测配置接口可透传） |

**已消项**：七列（类型/周期/标的/状态/Worker/最近回测 + 策略名）+ 点行常驻详情块（`:654-705`）、页头「发起回测」、副标真实计数（`:307-320`）、状态 chips（`:324-334`，草稿态按决策省略）、`GET /strategy/overview` 三表聚合、`?tab=backtests` → replace、策略名 200px 截断 + 悬停全名、**版本历史**（表 + `/versions` + 折叠列表 `:604-652`）、**首屏预选首行**（兜底 effect `:300-309`，空列表不选、用户选择不被抢）、**版本 0 条仍保留 footer 段**（弱态文字）。

**反缺口**：排序 Select、行删除（icon + Popconfirm）、卡片视图、版本历史折叠列表（demo 只有计数文案）、全局分页开关。

## 6. 策略编辑器 `/strategy-editor(/:name)`（demo 2150–2207）

**已消项**：页头四钮顺序/primary、编辑器+预览 tabs、状态栏四段、预览档案/数据源/参数/因子、去回测带策略名、**副标与档案行时间统一 `MM-DD HH:mm`（完整时间进 tooltip）**、**AI 弹窗「kernel 兼容契约」chip**（`AIChatModal.tsx:719-726`）。其余均为超集（Monaco、参数/因子 CRUD、模板上传、AI 流式弹窗）。

**反缺口**：Monaco 真编辑器、tabs 图标、档案创建/更新只读行、重新解析钮、参数 chip 化真 CRUD、因子库联动。

## 7. 回测中心 `/backtest` + 详情（demo 1131–1350）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 「订单」列口径 | 1168/1195（236 = 成交 229 + 撤单 7） | `BacktestList.tsx:626-634` 值为 `metrics.total_trades` = fills 笔数（`result_formatter_service.py:524-526`） | `需聚合`：引擎已产出 `orders_accepted/orders_rejected`（`engine_service.py:1351-1352`，多品种聚合键也含），formatter 未注入 → 注入两键后**订单列 + KPI「成交/撤单」+ 详情卡三处同时解锁** |
| KPI sub 行（成交/撤单、交易日、盈亏比） | 1233-1237 | 详情页用 29 张独立卡超集覆盖（`metricCards.ts:101-131`），无 sub 形制；行内摘要 5 卡未含 `profit_factor`/`duration_days` | 前两项随上一条解锁；`profit_factor/duration_days` 已在 `summary.metrics`，`已有`（行内摘要加两卡） |
| 详情页配置卡缺手续费 / runner | 1253 | `BacktestDetail.tsx:514-553` 8 项无 commission、无 engine_type | commission `已有`；engine_type 任务文件有但 `BacktestDetailData` 未带 → `需聚合`（一处透传） |
| 配置脚注「滑点」 | 1252-1254 | 全链路无字段（grep slippage 0 命中） | `无源` |

**已消项**：区间列、订单列存在、双段副标（`BacktestList.tsx:1003`，第三段「引擎 kernel/legacy/python」比 demo 更实）、**运行中进度 15s 自动轮询**（`BacktestList.tsx:129-170`，终态立即停、null 保留旧快照）、**详情页 failed 错误块**（`BacktestDetail.tsx` 页首失败块，取不到 `error.message` 整块不渲染）、**LLM replay 不降级提示**（列表失败块 + 配置页 `mode=llm` 判定，`bt_llm_replay_note`）、失败原因 `error.message`、空态「清除筛选」、**类型列 + 工具栏类型下拉**（服务端 `kind`，纯超集）。

> **类型列等价性（复检裁定）**：demo 回测中心**没有类型 chip**（静态列头 7 列无类型，JS 种子 10 行策略列均为裸文本，类型只藏在名字前缀；`TYPE` 映射 2644 属策略管理页）。现网独立「类型」列 + 服务端 `kind` 下拉是对 demo 的增量，与策略列内的 `rl_model:`/`rl_ensemble:` 来源 chip 职责互斥（来源≠类型）。**无需任何对齐动作。**

**反缺口**：行内摘要卡、行内权益曲线（≤200 点采样）、标的列、RL 来源 chip、键盘导航、卡片视图、删除确认、创建日期范围筛选、8 档排序。

## 8. 回测配置 `/backtest/config`（demo 2210–2278）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 参数只读行（entry/sl 纯文本） | 2269-2275 | `BacktestConfig.tsx:529-554` 全部可编辑；`StrategyParam` 无只读标记 | `需聚合`（后端扩 `readonly` 标记才做，否则保持现状） |
| 预计运行 bar 数 | 2276 | 无 | `已有`（timeRange + interval 均在表单，前端推算并标「估算」） |
| 乘数/币本位账务警示 | 2243-2245 | `BacktestConfig.tsx:1289` 只讲现货/永续与资金费 | `已有`（并入 extra 文案；引擎侧确未把乘数计入名义价值） |
| 资金模式「固定/复利」 | 2254-2256 | `:1330-1342` `per_symbol/shared` | **不照抄**（两条不同轴线，硬加会与 `capital_mode` 契约冲突） |

**已消项**：页头副标 runner（`:1124-1130` 逐字对位）、标的选取（Select multiple 超集）、手续费读出侧百分化（`bc_subtitle` + 行内脚注）、交易模式 hint 基础段、**LLM replay 不降级提示**（选中 `mode=llm` 策略时参数卡底部，`bt_llm_replay_note`）、标的下拉自选组标识统一（组色圆点与数据管理页该组自定义色同源，回测配置 / Worker 创建 / 编辑三处共享 `utils/symbolOptions`，⭐ 与固定警示色星标已废；数据管理采集表单的组值前缀一并统一为 `pool_`）。

**反缺口**：保证金规格输入、数据预检下载、进度弹窗、`lastBacktestConfig` 回填。

## 9. 因子分析 `/factor-analysis`（demo 1770–1888）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 「半衰期」列 | 1796（`62 bar`） | 全仓无 `half_life`；`inspection.decay` lag 序列只在图表里（`FactorResultView.tsx:133-155`） | `需聚合`（由 decay 推导，仅对已有快照因子；否则裁列） |
| 副标「样本 1h 全品种 · IC 为 RankIC（日频）」 | 1774 | `FactorAnalysis.tsx:109-121` 只有生命周期三段计数；文件头注释自述「接口未提供口径，不写」 | `已有`（对有待值快照的因子读 `params.interval` / `ic.method`） |
| 详情承载：表下常驻块 + IC 时序小图 | 1867-1887 | `FactorAnalysis.tsx:164-178` Drawer 68% + 四页签；IC 时序在分析页签里 | D 档（数据已有；最小切口是把 IC 时序提到概览顶） |
| 「批量回测」 | 1777-1778 | `:129-139` 只有「新建因子」 | `无源`（无 因子→回测 编排链路） |
| 「加入组合」+ 贡献权重 | 1883-1885 | 无组合权重概念 | `无源` |

**已消项**：「覆盖率」列（`FactorLibraryPane.tsx:269-279`，与概览卡同口径）、IC 着色（现网语义阈值分档，决策不改）、「入库」时间（退化呈现为「最近快照」列）。

**反缺口**：分析/对比页签、IC 衰减图、因子代码面板、合成因子成分权重。

## 10. 策略研究 `/research`、`/research/:id`（demo 1890–1965 / 2281–2329）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 列表摘要 `ic=` / `cov=` | 1920/1929/1938 | `ResearchList.tsx:473-490` 只有 icir | `需聚合`（列表端已批量取 best trial，`session_to_dict` 只序列化 `ic_ir`，补两字段即可） |
| 副标「研究员 liupeng」 | 2286 | `owner_id` 已落库（`research/models.py:25`），API 未透出 | `需聚合`（`session_to_dict` 加一行；可读名需查用户表） |
| 「产物」块 + 下载 | 2305-2311 | 无产物文件概念（strategy 场景的产物是落库策略 .py） | `无源`（文件级产物/下载不存在） |

**已消项**：`一键转回测` 全链路已存在（trial 级）、**列表卡片「转回测」入口**（按会话 `best_trial_id`，无最优轮次禁用、点击时校验 `has_code`）、**详情页头会话级入口**（已有任务就地变「查看回测」）、**成功后跳 `/backtest/detail/{task_id}` 深链**（拿不到才退回列表）、**「结论」md 卡**（best trial 的 hypothesis/judge.reason/metrics/config，缺字段整段省略）、**「Top 5 轮次」按 OOS Sharpe 降序**（无 Sharpe 不入榜、不足 5 条按实际条数）、前置校验与复用提示（`has_code` 预禁用 + 幂等 promote，比 demo 更实）、页头「回测中心」钮、类型体系（按现网 scenario×mode 为准）。

**反缺口**：trial 对比选择、异常列、`promoted_factor_name` 复用提示、扩展轮次。

## 11. 数据管理 `/data-management(+/market-replay)`（demo 2021–2266）

> 行号提示：本次把数据管理补齐为四页签后，`#view-data` 及其后各视图行号整体后移；本节以外的行号引用仍为补齐前的旧值。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| kline / fundingRate 水位卡无「补齐」入口 | （demo 无此钮，现网反向补充） | `ArchiveWatermarkStrip.tsx:121` 按 `FILLABLE_KINDS` 过滤，四卡里 kline/fundingRate 两张刻意不显钮（点会 400，数据池路径） | `已有` 但需给正确入口：kline 增量只能走采集页签表单，**主数据源反而没有首屏入口** |
| 「最新 bar」只到日粒度 | 水位卡（小时级 + 「落后 2h」） | `archive_service.py:334-336` 把 footer timestamp 截成日期，`lagDays` 按天 | `需聚合`（footer 有 timestamp min/max，后端改口径即可） |
| 水位卡第二行（采集方式/频率/口径/限频降速） | 水位卡内 kv 行 | 无 | `无源`（无采集健康源） |
| 「存储报告」弹窗 | 页头钮 + 弹窗 | 无弹窗，改为常驻卡 | 形态差；合计 `已有`，保留策略/上次压缩/特征缓存 `无源` |
| 存储卡「LLM replay 记录」行 | 存储用量卡 | watermark 只 walk `data/source` | `需聚合`（`backend/data/llm_replay` 目录 du） |
| 页头「立即同步」 | 页头 primary 钮 | `DataManagementPage.tsx:3906-3909` 仅 title/subtitle | `无源`（无「增量同步全部」语义；卡内补齐已部分替代） |
| page-sub「本地 parquet · 保留 180 天」 | 页头副标 | `:3908`「数据类型 N 类 · 已接入标的 N 个」 | 10 类 `已有`；180 天 `无源`（无保留策略） |
| 标的简况无「所属自选组」 | sym 面板 kv 行「所属自选组」：列出该标的所属**全部**组（组色点 + 组名，未加入显示「未加入任何自选组」），随管理弹窗改名/换色/增删组成员实时重绘 | `DataManagementPage.tsx:2753-2825` `renderSymbolDetail` 只有价格/涨跌/采集口径等格，无组归属 | `已有`（`FavoriteGroup.symbolIds` 反查 + 组 `color`，前端即可，零后端改动） |

**已消项**：首屏数据源水位四卡（健康 dot / 累计 bar / 落后 chip / 标的数）、存储用量条形卡、**存储用量卡默认折叠为一行（整条卡头可点 + 键盘可切；「合计 X」为 demo `.s-chip` 带框 chip + 三角 caret 展开右旋；展开为 `.cmp` 形制：虚线上边分隔、11px 行、7px `--info` 蓝条、mono 10.5px 数值、卡脚注「来源 GET /data/archive/watermark」）**、**全页统一 14px 格线（页签条 / 卡头 / 卡内内容 / 表格首列同一条 x）**、**四页签收进同一张卡壳（页签条即卡头，卡身零内距）**、同步任务表（进度条 + 失败红字 + 子任务展开）、状态 chips + 服务端分页、**四页签结构（行情标的 / 数据采集 / 数据质量 / 历史行情浏览）**、**自选组侧栏**（组切换过滤双形态、管理自选组的新建/重命名/删除、默认组禁删、批量添加自选、★ 收藏）、**行情标的页签两栏布局 + 质量/计价 chips + 8 档排序 + 底部「批量数据采集」卡（已选标的 × 数据类型 × inc/full → 真发 `POST /data/download/crypto`）**、**数据采集页签改单列（表单卡 → 工具栏 → 任务卡）并新增「模式 inc/full」字段**、**质量页签按拍板重排**（概览卡 6 KPI：评分 / 良好 / 警告 / 异常 / 未检测 / 上次检测 + 运行检查；清理工具降为检查结果卡头的次级按钮；7 维明细保留）、**归档浏览改检索式**（归档检索卡 → 归档摘要卡 → 归档明细表，左树移除）、**批量数据采集表单**（数据类型多选 · 市场 · 交易所 · 周期 · 起止日期 · 增量/全量 + 勾选批次下发）、**采集任务五态与子任务展开**（运行中/已完成/失败/等待/已取消，失败带 error 与重试）、**质量页签**（质量评分 + 良好/警告/异常/未检测概览 + 运行检查 + 7 维子页签与逐维证据：缺失列/缺失时间段/缺失记录/缺失 N 条/缺少 N 天历史或最新数据/覆盖率/价格逻辑异常）、**归档摘要**（检索条件 + 起止/条数/文件数/损坏日期 + 浏览 + 删除确认）。

**管理自选组按 demo 形制重做**：右侧抽屉 + 独立「新建/编辑」弹窗两套入口合并为一个 `#mWl` 式弹窗——每行「组名输入（失焦/回车即时改名）+ 6 色块（点即改色，选中=描边环+白勾 `aria-pressed`）+ N 标的 + 批量添加 + 删除（默认组禁用）」，底部「新名称 + 取色 + 关闭 + 新建组」，侧栏「新建自选组」打开同一弹窗并聚焦新建框；旧组描述字段不再有编辑入口（demo 无此字段，页面也不展示）。

**demo 侧同步**：`#dm-symbols` 工具栏补「计价货币 chips（全部/USDT/BTC/ETH）+ 8 档排序下拉」，排序真实重排行与卡、与搜索/质量/自选组为交集；8 个选项文案逐字对齐 `i18n/zh-CN.json`。

**反缺口**：归档行「行情回放」只到弹窗说明（demo 无回放画布，正式页跳 `/data-management/market-replay`）、质量检测与归档数字为确定性伪数据（不落库）、自选组与任务表刷新回播种态、归档条数未按标的缺口扣减。

## 12. 模型中心 `/model-hub`（demo 2050–2147）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 模型卡「关联 worker」 | 2083 | `UnifiedModelTable.tsx:529-552` 无 | `需聚合`（命名约定 `rl_paper_<model_id>` / `rl-<model_id>` 确定，加一次前缀 join 即可） |
| 模型卡「shadow 战绩」 | 2105 | 卡片无；lifecycle 台账有 `_shadow_win_streak`（family 粒度） | `需聚合`（family↔model 关联 + 目标天数 `required_shadow_win_days` 暴露） |
| 模型卡「异常捕获」「归档原因」 | 2094/2116 | registry 行无这两个字段 | `无源` |
| 行选中 → 表下常驻详情块（含 reward 曲线 + 对比条） | 2075-2078 + 2122-2146 | 行点击只高亮，详情走 Drawer | D 档；reward 曲线 `无源`（同步训练只回最终 metrics），对比条 `需聚合`（同窗口径无保证） |

**已消项**：卡片视图 Sharpe 染色（`UnifiedModelTable.tsx:96-102`）、角色 chips 七枚（超集）、Drawer 的 spec/features/files 分区、**副标双闸段**（`GET /rl/lifecycle/state`，字段不完整或缺席时不渲染）、**重训台账**（只读 Modal：候选/待审晋升/晋升记录，失败显示错误不出空表）、**页级「新建训练」**（`?tab=train` 深链，无排队语义）。

**反缺口**：第四页签「模型集成」（EnsembleWorkbench）、Drawer 分区、算法下拉筛选。

---

## 横切结论

### A. 纯前端就能清掉的（后端零改动）——**2026-11-23 已整批落地**

1. ✅ `/agent` 工具节点逐节点耗时（`toolCalls[i].elapsed`）+ 每日复盘 meta 渲染（出处 chip + `report.sections`）。
2. ✅ `/backtest` 运行中 15s 轮询；详情页 failed 错误块；列表 + 配置页「LLM replay 不降级」文案。
3. ✅ `/strategy-management` 首屏预选首行 + 版本 0 条保留 footer；`/strategy-editor` 时间格式统一 + AI 弹窗契约 chip。
4. ✅ `/strategy-worker` 详情页「停止」+ 事实条持仓三件 + 状态筛选「已暂停」+ 页头返回钮（「暂停/继续」需后端路由，未做）。
5. ✅ `/model-hub` 双闸副标 + 重训台账 Modal + 页级「新建训练」。
6. ✅ `/chart` OHLC 联动条 + 常驻 MA 图例。
7. ✅ `/research` 列表卡片 + 详情页头「转回测」、成功跳任务详情、结论 md 块、Top5 按 OOS Sharpe。
8. ✅ `/home` 研究卡脚注。
9. ⏳ 仍未做（留待下一轮）：`/backtest/config` 预计 bar 数（标「估算」）与乘数/币本位账务警示；`/strategy-worker` 决策流「思考折叠」（`s2_thinking` 有真值）。

### B. 一次后端聚合解决一页

1. `/backtest`：`result_formatter_service` 注入 `orders_accepted/orders_rejected` → 订单列口径、成交/撤单 KPI、详情卡同时修正（引擎已算好）。
2. `/research`：`session_to_dict` 补 `best_trial.ic_mean/coverage` 与 `owner_id`（列表端已批量查到，只差序列化）。
3. `/strategy-management`：footer runner 改读 `engine_config['runner']`。
4. `/backtest` 详情：`BacktestDetailData` 透传 `engine_type`。
5. `/home` + `/strategy-worker`：按 worker 拆 24h 已实现盈亏（今日 % 口径）。
6. `/data-management`：watermark 改 timestamp 粒度（小时级落后语义）+ 把 `llm_replay` 目录计入存储卡。
7. `/model-hub`：模型→worker 反查、shadow 战绩目标值。
8. `/strategy-worker`：「暂停/继续」需后端先补 `lifecycle/pause|resume` 路由 + 泵线程暂停语义（现网只有 start/stop/restart，前端 `agentApi.pauseAgent/resumeAgent` 是死代码）。

### C. 明确不做（无源，做了就是造假）

草稿态 · 版本历史（**已做，移出**）· OOS 口径 · 滑点 · AI 诊断结论 · 中途权益/预计剩余 · 资金模式「固定/复利」· ML 类型细分 · 交易类系统指标（引擎耗时/交易所延迟/LLM p95）· WS 推送延迟 · 因子「加入组合/权重」· 因子「批量回测」· 研究产物下载 · 模型 reward 曲线 · 异常捕获/归档原因/训练耗时 · 数据特征缓存/保留策略/上次压缩 · 采集方式与限频描述 · 半衰期（需聚合，可裁）· 训练「排队」语义。

### D. 形态级大改，需单独立项

1. `/strategy-worker` 决策流：表格 → ReAct 气泡流（逐轮 reasoning/tool trace 仍无源，属能力缺口）。
2. `/agent` ReAct 步进卡（rail + iter-next，步骤命名无源，可先做计数/容量条）。
3. `/strategy-worker` 主从同屏（现为两路由）。
4. 详情承载：因子/模型从 Drawer/选中高亮改为表下常驻详情块（demo 三处一致范式）。
5. `/research` 会话级「转回测」语义（demo 是生成可调配置 → 回测中心，现网是直发任务）。
