# 首页（/home）

## 前置
- 环境与 token 注入见 `../README.md` 第一节；无数据依赖
- 本页为导航中枢，多数验证项为只读
- 视觉基准：`docs/design/qc-prototype-demo.html#home` + `docs/design-spec.md` §5/§6.2/§6.3/§6.4/§6.5/§6.13/§6.17；数字口径只写接口能给出的真实数据，demo 静态演示值不照抄

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| H1 | 直接打开 `/home` | 页面渲染出主导航（首页/策略管理/回测中心 等菜单文本可见）；URL 保持 `/home`（不被踢回 `/login`） | L1 |
| H2 | 页面加载完成后 | `/notifications/inbox` 请求返回 200（历史雷区：曾因 401 把用户踹回登录页）；消息中心入口可见 | L1 |
| H3 | 观察系统连通性徽标 | 徽标存在且呈"连接中/已连接/离线"三种状态之一，页面不报控制台错误。注意：徽标=**交易所连通性探测**，非后端状态；浏览器预览链路无系统代理继承，显示离线不算失败，如实记录即可 | L1（外部依赖，不断言状态值） |
| H4 | 点击导航"策略管理" | 跳转 `/strategy-management` 且页面渲染（列表或空态提示） | L1 |
| H5 | 观察页头 | 标题 `qc-page-title` 16px/650 为「首页」；副标 `qc-page-sub`（11px mono 灰）形如「2026-11-20 星期五 · UTC+8 · 系统运行中 · 最后更新 19:38:12」——日期/星期来自本地时间、UTC 偏移来自系统时区，「系统运行中」仅在 `/system/metrics` 返回 connected 时出现，「最后更新」为真实轮询时刻；接口失败时对应段省略，不出现编造的静态文案 | L1 |
| H6 | 观察页头右侧动作钮 | 先见 11px 弱态 cap 标签「快速操作」（对齐 demo 828 `.pa-cap`，纯文本非按钮），随后恰好 3 个 30px 高、8px 圆角钮：主色「新建策略」（→ `/strategy-editor` 空白编辑器，对齐 demo 首钮）+ 默认「开始回测」（→ `/backtest/config`）+ 默认「打开策略智能体」（→ `/strategy-worker`，对齐 demo 第三钮）；命名口径：菜单 #2「智能体工作台」= `/agent`、菜单 #4「策略智能体」= `/strategy-worker`，不得串位；「运行中任务」卡的建任务钮仍是「新建策略智能体」（→ `/strategy-worker`）；主色钮底色为品牌橙（亮色 `rgb(234,88,12)`） | L1 |
| H7 | 观察 KPI 行 | 4 张等宽 `.qc-kpi` 卡（padding 12px 14px、圆角 10、`--card` 底、`--bd` 边）：label 11px 灰、数值 mono 22px/650、副注 10.5px；数值依次为运行中 worker 数（样本统计）、今日盈亏 %（正绿/负红/0 中性不上色）、回测总数（服务端 `total`）、研究会话总数（服务端 `total`）；数字全部来自真实接口，取不到时显示「—」而不是 0 | L1 |
| H15 | 观察 KPI1 副标 | 形如「共 6 · 运行中 2 · 已暂停 1」：共 = `GET /workers` 的 `total`，运行中/已暂停 = 同一次 `page_size=50` 样本内 `status==='running'/'paused'` 计数；**不出现「草稿」段**（worker 无草稿态，无源不写） | L1 |
| H16 | 观察 KPI2 口径 | 标题「今日盈亏」，数值为百分比（`+0.42%` 形态，`formatPercent` 2 位），副标「近 24h 已实现盈亏 ÷ 配置资金 · 不含手续费 · 较昨日同期 ±x.xxpp」；`0.00%` 为中性色（不上绿/红）。数据源：`GET /api/v1/workers/stats/pnl-overview`（分子 `SUM(worker_trades.realized_pnl)` 按 `entry_time` 近 24h，分母 `worker_capital.initial_capital` 缺失时回退 `workers.config.initial_capital`）；分母为 0 时后端返回 `pnl_pct: null`，UI 显示「—」 | L1 |
| H16a | 核对 KPI2「较昨日同期」段 | 同一响应里的 `prev_pnl_pct` = 昨日**同期**窗口（`now-48h ~ now-24h`，同分子同分母）的百分比；段内数值 = `pnl_pct − prev_pnl_pct`（**百分点差**，不是百分比变化，`toFixed(2)` + `pp` 后缀）；`curl` 取 `pnl_pct`/`prev_pnl_pct` 后手减应一致（如 1.20 − 1.00 = `+0.20pp`）；涨绿（`qc-cell-up`）/跌红（`qc-cell-down`）/0 中性不上色；**任一侧为 `null`（分母 0）时整段不渲染**，不得写 `0.00pp`；措辞固定「较昨日**同期**」（滚动窗口，不是自然日），**不得**写成「较昨日」或「较昨日收盘」 | L1 |
| H17 | 观察 KPI3 副标 | 形如「完成 83 · 运行中 2079 · 失败 930」：三段均取 `GET /backtest/list?status=<completed\|running\|failed>&page_size=1` 的服务端 `total`（running 含 in_progress），不是本页 96 行样本计数；三次请求任一失败时退回「历史回测记录」静态副标，不写 0 假值 | L1 |
| H8 | 观察四个区块 | 网格顺序：运行中任务（8 列宽）＋系统状态（4 列）、最近回测（6 列）＋最近研究（6 列）、底部快速操作全宽卡；每块是 `.qc-card`（圆角 10、`--bd` 边），卡头 13px/650，卡头右侧有 mono count-chip 与「查看全部 →」链接（11px info 蓝下划线 hover）。**预览行数= demo 口径（2026-11-26）**：运行中任务 3 行、最近回测 3 行（chip「共 N 条」+ 查看全部承接完整列表）、最近研究 4 行；≤767 才收单列（demo 无 1199 档，1021 一类窄桌面保持 12 列拼排，2026-11-26 撤掉旧 ≤1199 单列降档）；1440×900 全屏看板 `qc-main` 无滚动条（内容压在可视区内，不需要滚） | L1 |
| H9 | 「运行中任务」行点击与标签 | 行内 strategy 名 mono 加粗 + `#id` 弱色 + 交易模式 tag（实盘=主色 tint 全圆 tag、模拟=info tint、无配置=中性）；第二行为 策略类型 · 策略名 · 标的 · 周期（10.5px 弱色）；右侧 盈亏 mono（正绿/负红）+ 运行时长（running 且有 `started_at` 时显示 `14h 22m` 形态）+ 状态 chip（运行中=info 带呼吸点、失败/中断=down、暂停=warn、停止/初始化=quiet）；点击整行跳 `/strategy-worker/:id` | L1 |
| H10 | 「系统状态」行点 | 4 行业务读数（交易引擎 / Exchange / 行情数据源 / LLM Provider），每行 = 8px 状态点 + 名称 12px/550 与同行 mono id 10px 徽标 + 副说明 10.5px + 右值 mono 10.5px，行间 1px dashed 分割、首行无；id 徽标统一灰色小字、值为中性技术短词（引擎=`kernel`、交易所名、数据源=`kline`、LLM=provider 名；**内部品牌名 `axon-kernel` 不入 UI**——2026-11-26 裁定）；卡头右侧「4 项」count-chip + 24px 刷新图标钮，卡底 dashed 分线上方为「最后更新 HH:mm:ss」真实刷新时间。全部取 `/system/metrics` 的 `engine/exchanges/dataSource/llm` 块：引擎 tick 均值、Exchange 公共端点往返延迟（失败时右值「—」、点转红）、行情库 bar 数与最新 bar 时间、LLM provider 名/模型 + 近 5 分钟调用数与 p95（429 时点转黄）。无 worker、无 LLM 调用、无探测结果时点显灰圈、右值「—」，不得显示 0 或示例数字 | L1 |
| H11 | 「最近回测/最近研究」行 | 回测行：策略名 mono + 「区间 · 周期」（`2026-10-21 → 2026-11-20 · 15m`，区间取 `GET /backtest/{id}/summary` 的 `backtest_config.start_time/end_time`，周期取 `interval` 或列表 `intervals[0]`；summary 无起止时间的任务退回「创建时间 `MM-DD HH:mm`」+ 周期，`invalid` 这类脏周期不渲染）+ 状态 chip（完成 ok/运行中 info 点/失败 down）+ 收益率（正绿负红，失败或空显示「—」）；研究行：标题 + 类型 chip（factor=因子 / model=模型 / strategy=策略，info tint）+ 状态 chip + 「x 前」相对时间；分别点击跳 `/backtest/detail/:id`、`/research/:id` | L1 |
| H18 | 观察「最近回测」卡脚注 | 行列表下方 dashed 分线内有说明「回测失败不降级为 Hold；LLM 决策缺 replay 记录即报错终止」（对应 `strategy/llm_replay.py` 的 `ReplayMissError`：不降级 heuristic、不返回空串）+ 右侧「回测中心 →」链接跳 `/backtest`；无回测行时不渲染该脚注 | L1 |
| H12 | 空态与加载态 | 首次加载未返回前，四个区块显示灰色骨架条（`--bge` 底、6px 圆角、无 shimmer），KPI 数值显示「—」，不白屏；无数据时区块内渲染图标块空态（46×46 圆角块 + 主文案 + 操作 mini 按钮），按钮可跳创建入口：任务→新建、回测→发起回测、研究→新研究 | L1 |
| H13 | 主题切换走查 | 暗/亮分别观察：卡片底/边、KPI 数值色、chip 三色 tint、系统状态点光环均随 token 切换，不发灰不串色；颜色类属性 160ms 过渡无布局跳动 | L1 |
| H14 | 「快速操作」卡 | 底部全宽卡内 6 个 24px mini 钮（**单行 6 列**，2026-11-26 由 3 列 2 行压单省一排高度；≤991px 收 2 列）：行情图表/智能体工作台/回测/因子分析/策略研究/数据管理，图标 14px 弱色，点击分别跳对应路由 | L1 |
| H19 | 观察「最近研究」卡脚注 | 卡底部出现弱色说明行「轮次与最优指标只存于会话；在详情页采纳 trial 才写入因子库 / 策略库 / 模型注册表」，右侧「策略研究」链接点击跳 `/research`；无研究会话时整行不渲染（不留占位） | L1 |

## 历史雷区
- **401 踢登录**（已修）：`notifications/inbox` 曾 401 硬跳 `/login`。H2 就是针对它的回归哨
- **"系统离线"徽标误读**：根因是 exchange 探测未配代理，属环境类非 bug。验证时区分"请求已发出且 UI 状态如实"与"请求挂了"
- **HTTP 200 但页面空白**：若 `/api/*` 全 200 而 DOM 空白，先查控制台 JS 错误再查 chunk 加载（dist 与壳内嵌不同步的典型症状）
- **副标编造状态**（防回归）：页头副标里的「系统运行中/最后更新」必须来自 `/system/metrics` 与真实轮询时刻——不能学 demo 写死「引擎心跳正常 · 数据同步于 19:38:12」
- **回测 KPI 口径**：第 3 张 KPI 数字用 `GET /backtest/list` 返回的服务端 `total`，不是页面拿到的样本数组长度；运行中 worker 数是 `page_size=50` 样本统计，worker 超过 50 时偏小（已知取样上限，见代码 ponytail 注释）
- **KPI2 不许编造**：`realized_pnl` 是配对**毛**盈亏（`worker/paper_trade_sync.py` 模块头：手续费不挤入盈亏），所以副标只写「不含手续费」，不写 demo 的「已扣手续费」；`worker_capital.current_capital` 无写入方 → 分母用配置资金，不冒充「当前权益」。**「较昨日同期」不走 `worker_performance` 表**（该表全库无写入方）：昨日同期的已实现盈亏由 `worker_trades` 按窗口 `now-48h ~ now-24h` 直算，与今日同分子同分母，因此只能叫「同期」（滚动 24h 窗口），**不得**写成「较昨日 / 较昨日收盘」（那是自然日口径，无源）
- **KPI3 分布不能拿样本凑**：任务目录有 3000+ 条，96 行样本只覆盖 ~3%，用样本计数会与 `total` 自相矛盾；分布必须走 `status` 过滤的 `total`
- **回测行区间无源时的表现**：`/backtest/list` 行不带起止时间，`summary.backtest_config` 来自 `backtest_tasks` 表且新任务常无行（返回 `{}`）→ 此时行内退回创建时间，属预期降级，不是丢字段
- **看板一屏的两根定海针**（2026-11-26）：① ≤1199 的单列降档是看板滚动条元凶——1021 窄桌面下内容堆到 1344px（可视 694），demo 在同宽是 12 列拼排 ≤850，降档断点已改 ≤767，**别为「窄一点就单列」把断点改回去**；② antd 全局 `line-height:1.57` 比 demo 的浏览器 normal(≈1.2) 每行撑高 3-4px，六个卡累计 ~30px 就够 1440×900 溢出，页面级已统一 1.35——新增行元素记得挂进该 line-height 选择器组，并保持预览行数 3/3/4（demo 口径）
