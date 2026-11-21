# demo ↔ 现网 对齐差距清单

> 基准：`docs/design/qc-prototype-demo.html`（下称 demo）为唯一视觉/信息架构基准。
> 现网证据一律给 `文件:行`；demo 证据给行号。
> 本清单只记**可验证差异**，不是待办工单——每项标了数据可行性，落不落地由优先级决定。

## 口径

| 标记 | 含义 |
|---|---|
| `已有` | 接口/表里现成字段，补 UI 即可 |
| `需聚合` | 要 join/取最新（写明了源表与字段），不造数 |
| `无源` | 当前系统算不出 → **只允许省略或显示「—」，不得编造** |
| 刻意增量 | 现网比 demo 多的能力（行内摘要卡、权益曲线、卡片视图、键盘导航、批量操作等），**不算差距**，后续审计勿重复计 |

「反缺口」：现网有、demo 无的件，单独列在每页末尾，避免下一轮误当成缺失去补。

## 本轮已落地（2026-11-21）

| 页 | 已补 | 数据口径 |
|---|---|---|
| `/chart` | 页头右上现价块：`品种 · UTC 收盘时间` + 22px/650 mono 价格 + 涨跌 chip | 末根 close，涨跌 = 末根/前根 − 1；<2 根整块不渲染 |
| `/strategy-management` | 删「回测记录」页签；七列（类型/周期/标的/状态/Worker/最近回测）；点行常驻详情块；页头「发起回测」；`?tab=backtests` → replace | 新增 `GET /strategy/overview`：workers × strategies × backtest_tasks 三表聚合，状态 = worker 投影 |
| `/backtest` | 区间列、订单列、双段副标、失败原因、运行中进度条、空态重置钮 | 区间/订单由任务行 config + 摘要透传；进度取 `overall_progress`；失败取 `error.message` |
| `/home` | KPI2 改「今日盈亏 %」、KPI1/KPI3 副标改真实分布、回测行带区间·周期、回测卡脚注 | 新增 `GET /workers/stats/pnl-overview`（24h 已实现盈亏 ÷ 配置资金）；KPI3 取服务端 total |
| `/factor-analysis` | 「覆盖率」列 | `last_metrics.coverage` |
| `/model-hub` | 卡片视图 Sharpe 染色 | 复用表格列同一阈值函数 |
| `/agent` | 右栏首屏恢复「迭代足迹 + 记忆自迭代(Dream)」两卡（8 页签下移保留）+ 轻量页头（会话 id / 单轮上限 / 两个跳转钮） | 足迹柱 = 当前会话 SSE `iteration_start`/`complete` 聚合（history 不带 iteration，故不做跨会话「近 12 轮」）；Dream 取 `/agent/memory`；无 `next_run_at` 时不出倒计时 |
| `/data-management` | 首屏「数据源水位」四卡 + 「存储用量」条形卡 | 新增 `GET /data/archive/watermark`：一次 os.walk 聚合两族布局（`_meta.json` 权威 + 无 meta 的 parquet footer 兜底），时间列名与单位逐文件判 |

尚未动：`/strategy-worker` 的形态级改造（决策流 bubble 需扩录制 schema，见 D 档）、回测配置只读参数行、「上次压缩 / 特征缓存 / 立即同步全部」等无后端语义项。

## 页面地图

| demo view（行） | 现网路由 | 组件 |
|---|---|---|
| `#view-home` 821 | `/home` | `pages/home/HomePage.tsx` |
| `#view-agent` 1369 | `/agent` | `pages/agent/Agent.tsx` + `components/` |
| `#view-sagent` 949 | `/strategy-worker`、`/strategy-worker/:workerId` | `pages/worker/Worker.tsx`、`WorkerDetail.tsx` |
| `#view-strategy` 1597 | `/strategy-management` | `pages/strategy/StrategyManagement.tsx` |
| `#view-strategy-editor` 2150 | `/strategy-editor`、`/strategy-editor/:name` | `pages/strategy/StrategyEditor.tsx` |
| `#view-backtest` 1131 | `/backtest`、`/backtest/detail/:id` | `pages/backtest/BacktestList.tsx`、`BacktestDetail*` |
| `#view-backtest-config` 2210 | `/backtest/config` | `pages/backtest/BacktestConfig.tsx` |
| `#view-charts` 1732 | `/chart` | `pages/chart/ChartPage.tsx` |
| `#view-factors` 1770 | `/factor-analysis` | `pages/factor/…` |
| `#view-research` 1890 | `/research` | `pages/research/ResearchList` |
| `#view-research-detail` 2281 | `/research/:id` | `pages/research/ResearchDetail` |
| `#view-data` 1967 | `/data-management`、`/data-management/market-replay` | `pages/data/DataManagementPage.tsx`、`KlineReplayPage` |
| `#view-models` 2050 | `/model-hub`（3 页签） | `pages/model/ModelHub.tsx` + `components/` |

---

## 1. 首页 `/home`（demo 821–946）

**最刺眼**：KPI2 口径完全不同（demo「今日盈亏 +0.42%」vs 现网「策略累计盈亏 $」）；四张 KPI 副标 demo 全是状态分布，现网三张是静态文案；系统状态卡是运维指标不是交易指标；回测行缺「区间 · 周期」。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| KPI2 今日盈亏 % | 852-855（含「较昨日 +0.08%」） | `HomePage.tsx:281-289` 累计盈亏绝对值 USD | 今日盈亏 `需聚合`（worker overview 24h 窗）；「较昨日」`无源` |
| KPI1 副标状态分布 | 849「共 24 · 运行 5 · 已暂停 7 · 草稿 4」 | `:277` 仅总数 | 暂停数 `需聚合`（workers.status）；草稿 `无源` |
| KPI3 副标回测分布 | 859「完成 121 · 运行中 5 · 失败 2」 | `:300` 静态「历史回测记录」 | `需聚合`（回测任务 status 计数） |
| KPI4 副标研究分类 | 864「因子 9 · 参数扫描 11 · 实验 7」 | `:310`「N 个进行中」 | 分类学不同（现网无「参数扫描/实验」） |
| 系统状态卡 4 行 | 898-904 引擎耗时/交易所延迟/bars/LLM p95 | `:441-468` CPU/内存/磁盘 | 交易类四项 `无源`；保留现网指标是诚实的 |
| 系统卡头右侧 | 899 count-chip「4 项」 | `:422-435` 刷新钮 | 形态差 `已有` |
| 最近回测行 | 910-918 名称 + 「区间 · 周期」 | `:525-528` 名称 + `MM-DD HH:mm` | `需聚合`（任务行 config 起止/周期） |
| 回测卡脚注 | 921 说明行 + 链接 | `:506-546` 无 | 文案 `已有` |
| 类型 chip 粒度 | 876/883/890 RL·PPO / 规则 / LLM / ML | `:346` 仅 RL / 规则 | LLM/ML 细分 `无源`（worker.strategy_type 两档） |

反缺口：运行中任务行点击直达 `/strategy-worker/:id`（demo 只到列表）、空态、底部快速操作卡。

## 2. 智能体工作台 `/agent`（demo 1369–1595）

**最刺眼**：demo 右栏是「迭代足迹 + Dream」两张分析卡，现网把两者收进 8 页签工作台的「自迭代」tab，首屏不可见；ReAct 过程只有一个「迭代 X/Y」小徽标；工具链无耗时、参数是裸 JSON。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 页头 | 1370-1379 会话 #id + 副标 + 「策略智能体 →」「← 返回首页」 | `Agent.tsx:217-282` 无页头，顶栏为会话/Worker 控件 | 导航钮 `已有` |
| 右栏形态 | 1528-1553 迭代足迹柱图（12 条 + 熔断线 40）+ 1555-1592 Dream 卡 | `WorkbenchPanel.tsx:26-35` 8 tab | 分区不同；「近 12 轮迭代次数」`无源`（audit 按天聚合） |
| Dream 卡 | MEMORY.md + cursor + 待处理 + 下次运行倒计时 | `SelfLoopTab.tsx:106-111,224+` 同数据无倒计时 | `已有`（倒计时形态缺） |
| 定时任务入会话流 | 1391-1404 | 会话流只有 user/assistant/tool | `需聚合`（job 记录已有，注入方式需产品决定） |
| ReAct 步进卡 | 1414-1446 rail + cap-bar + SSE 事件计数 + iter-next | `ChatPanel.tsx:196-206` 仅徽标 | SSE 数据现成，`需聚合`（前端聚轮次）；步骤命名 `无源` |
| 工具链节点 | 1460-1488 工具名 + 参数摘要 + 耗时 + 展开 | `ChatPanel.tsx:128-149` 裸 JSON 参数、无耗时 | 耗时 `无源`；摘要 `需聚合` |
| 「转回测验证」预填 | 1506 | `ChatPanel.tsx:167-174` 只跳页 | 预填 `需聚合` |

反缺口：Worker 选择器 + 状态 chip、`?tab=&worker=` 持久化、工具参数抽屉、删除需输入确认词、自迭代每日闭环、意图面板。

## 3. 策略智能体 `/strategy-worker(+/:id)`（demo 949–1128）

**最刺眼**：demo 决策流是聊天气泡式 ReAct（思考折叠 + 工具轨迹 + 耗时），现网是冷表格；详情页没有启停按钮；头部事实条缺持仓/均价/未实现（数据现成）。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 主从同屏 | 960-1127 左列表 + 右详情 | 拆成两个路由 `Worker.tsx:926-951` / `WorkerDetail.tsx:266+` | 结构差异，数据 `已有` |
| 页头副标 | 953「worker 泵运行中 3 · 暂停 1 · 统一内核驱动」 | `Worker.tsx:917-924`「任务 N · 运行 · 停止 · 错误 · 累计盈亏」 | 暂停数/固定文案 `已有` |
| 页头返回钮 | 956 | `:927` 无 | `已有` |
| 行内容 | 963-986 #id + 时长 + 今日 pnl | `:860-912` name/状态/exchange/interval/累计 pnl | #id `已有`；时长 `需聚合`；今日 pnl `需聚合` |
| 状态筛选含「已暂停」 | 981-986 | `:439-443` 只有 running/stopped/error | `已有` |
| 详情头部动作 | 997-1006 暂停 + 停止（二次确认） | `WorkerDetail.tsx:271-306` 分享/归档，启停在列表页 | `已有` |
| 决策流形态 | 1017-1111 ReAct 卡/思考折叠/工具耗时/iter-next | `WorkerDecisionsTab.tsx:69-128` 表格 | 表格行 `已有`；reasoning/tool trace `无源` |
| 头部事实条 | 1116-1125 持仓/均价/未实现/回撤/杠杆/风控次数/今日手续费 | `WorkerDetail.tsx:333-355` 周期/模式/盈亏/初始资金/杠杆/下单方式/最后更新 | 持仓类 `已有`（挪到首屏）；今日手续费 `需聚合` |
| 选中语义 | 963 aria-pressed 选中查看 | `:856-859` rowSelection 用于批量 | 语义差，`已有` |

反缺口：六页签全可用、批量操作、分享/归档、URL 直达详情。

## 4. 策略管理 `/strategy-management`（demo 1597–1730）— 用户点名页

**已决策**：「回测记录」tab 删除（回测统一在回测中心），连带退役 `?tab=backtests` 返回链路（`StrategyManagement.tsx:161-244`）。

**最刺眼**：缺「类型/周期/标的/状态/Worker/最近回测」六列；状态与「策略任务(Worker)」混在一起；点行无详情块（参数 KV + 去回测 + 创建 Worker）。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 页头「发起回测」 | 1608 | `:1315-1324` 只有「新建策略」 | `已有` |
| 页头副标 | 1601 六段计数 + 「点击行查看参数详情」 | `:630-638`「策略共 N · RL n · 规则 n」 | 运行/模拟盘/已暂停/未部署 `需聚合`；草稿 `无源` |
| 状态 chips 6 枚 | 1614-1621 | `:691-723` 只有搜索+排序 | 同上 |
| 「类型」独立列 | 1628/1632/1642/1652（规则/RL/LLM/ML） | `:533-542` 类型 chip 挤在策略名内，仅 rule/RL | LLM `需聚合`（parameters 的 mode=llm）；ML `无源` |
| 「周期」列 | 1633 | 无 | `需聚合`（workers.trading_config.interval） |
| 「标的」列 | 1634 | 无 | `需聚合`（workers.trading_config.symbols） |
| 「状态」列 | 1635 + 映射 2985（运行中 pdot / 模拟盘 warn / 已暂停 quiet / 未部署 info / 草稿 warn） | 无 | `需聚合`：workers.status × trading_mode；无 worker = 未部署 |
| 「Worker」列 | 1636（右对齐计数，0 灰） | 无 | `需聚合`（count by strategy_name） |
| 「最近回测」列 | 1637（+% up / 失败 down / 回测运行中·未回测 muted） | 无 | `需聚合`（任务表最新一条 status + total_return） |
| 行操作 | 1638 去回测 + 编辑（文字 mini-btn） | `:581-625` 图标钮（含删除/回测记录） | `已有` |
| 版本位置 | 仅详情块头 1721 | `:539` 列表名内 `v1.0.0` chip | `已有`（口径移到详情块） |
| 点行详情块 | 1716-1729：标题 + 状态 chip + 版本 + 参数 KV + 去回测/创建 Worker + footer「runner=kernel · 版本历史 N · 累计回测 N」 | `:738-741` 只有行高亮 | params KV `已有`；累计回测 `需聚合`；版本历史 `无源`（version 是单字符串） |

**列表列 → 数据源映射**

| 列 | 来源 |
|---|---|
| 策略 | `strategies.name`（`/strategy/list` 已带） |
| 类型 | `strategies.strategy_type`；LLM 由 `parameters` JSON `mode=llm` 推断；机器学习不做 |
| 周期 | `workers.trading_config.interval`（无 worker → 「—」） |
| 标的 | `workers.trading_config.symbols`（同上） |
| 状态 | running ×（paper→模拟盘 / live→运行中）；paused→已暂停；无 worker→未部署；草稿不做（`strategies.status` 无此语义） |
| Worker | `count(workers where strategy_name = name)` |
| 最近回测 | 任务表 `WHERE strategy_name=? ORDER BY created_at DESC LIMIT 1` 的 status + total_return |
| 操作 | 复用现网去回测（`:434-436`）+ 编辑（`:405-407`） |
| 详情块 | `params` KV 用 `/strategy/list`（或 detail）返回值；累计回测用任务表 count；版本历史不做 |

反缺口：排序 Select、行删除（带回滚确认）、卡片视图。

## 5. 策略编辑器 `/strategy-editor(/:name)`（demo 2150–2207）

**结论：基本对齐，无结构性差距。** 页头四钮顺序与 primary、编辑器/预览 tabs、状态栏四段、预览档案/数据源/参数/因子、去回测带策略名，均与 demo 一致或为超集（Monaco 真编辑器、参数/因子 CRUD、模板上传、AIChatModal）。

可选口径统一（纯文案）：
- demo 副标时间 `MM-DD HH:mm`（2157）vs 现网 `YYYY-MM-DD HH:mm`（`StrategyEditor.tsx:964-971`）。
- demo AI 弹窗标题挂「kernel 兼容契约」chip（2467），现网未挂。

反缺口（勿当缺失）：档案多创建/更新时间两行、「重新解析」钮、参数行 chip 化与增删、因子库联动。

## 6. 回测中心 `/backtest`（demo 1131–1350）

**最刺眼**：缺「区间」列；缺「订单」列（现位被最大回撤占据）；运行中无进度感；失败无原因展示。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 副标第二段「历史共 128 条」 | 1135 | `BacktestList.tsx:831` 仅一段（`overallTotal` 已是历史总数） | `已有`（文案） |
| 「区间」列 | 1158/1164 | 无（只在摘要卡 sub 出现 `:357-359`） | `需聚合`（`/backtest/list` 行补 start/end；summary 已回传同字段 `types/backtest.ts:142-147`） |
| 「订单」列 | 1168/1195 | 无；同位是最大回撤 `:484-489` | `需聚合`（metrics.total_trades） |
| KPI sub 行 | 1234-1237 成交/撤单、OOS 口径、交易日、盈亏比 | `:253-276` 只有 label + 值 | 成交拆分/盈亏比 `需聚合`；OOS 口径 `无源` |
| 配置脚注 | 1253 含滑点 / runner / kline 周期 | `:366-372` 仅初始资金 + 手续费 | 滑点 `无源`（契约无此字段）；runner `需聚合`（`summary.engine_type` 已有） |
| 失败结论句 | 1329 AI 诊断文案 | 无 | `无源`，不做 |
| 运行中详情 | 1258-1273 进度条 + 已运行/预计剩余 + 中途值 | 摘要卡对 running 基本空转 | 进度 `需聚合`（progress 接口现成）；中途值/预计剩余 `无源` |
| 失败详情 | 1276-1298 错误名 + 日志 + 建议 | 只显示 chip | `需聚合`（progress 接口 `error.message` `routes.py:1401`） |
| 空态动作 | 1215-1222 空态内「清除筛选」 | `:652-660` 动作在工具栏 | `已有` |

反缺口（**勿当缺失**）：行内摘要卡、权益曲线、标的列、RL 来源 chip、键盘导航、卡片视图、删除/批量。

## 7. 回测配置 `/backtest/config`（demo 2210–2278）

**结论：能力为 demo 超集，主要是形制与两条「不该照抄」的差异。**

| 差异点 | demo | 现网 | 判断 |
|---|---|---|---|
| 资金模式「固定/复利」 | 2254-2256 | `BacktestConfig.tsx:1330-1342` 独立资金池/共享资金池 | **不可照抄**：后端只有 `per_symbol/shared`，无 compound 轴；硬加第二开关会与 `capital_mode` 契约冲突 |
| 参数只读行（entry/sl） | 2269-2275 | `:1419-1465` 全部可编辑 | 需后端扩 `StrategyParam` 只读标记才做，否则保持现状 |
| 预计运行 bar 数 | 2276 | 无 | 前端推算即可，须标「估算」 |
| LLM replay 提示 | 2264 | 无 | 机制真实（未命中即失败不降级），补静态文案零风险 |
| 标的选取形制 | 2230-2236 pick chips + 添加 | `:1240-1261` Select multiple（数据池） | 现网能力更强，形制差 |
| 手续费呈现 | 2250 「0.05%」 | `:1300-1327` 小数输入，副标已百分化 | 口径差 |
| 交易模式 hint | 2243-2245 乘数近似账务警示 | `:1285-1295` 现货/永续说明 | 可并入 demo 的账务警示文案 |

反缺口：保证金规格输入、预检下载、进度弹窗、默认值回填。

## 8. 行情图表 `/chart`（demo 1732–1768）

> 右上价格块（demo 1738–1741 `.px-box`）**实现中**，不在此重复计数。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 页头副标 | 1736「UTC 时区 · WS 推送延迟 <1s」 | `ChartPage.tsx:615` 只有数据模式 | 时区 `已有`；WS 延迟 `无源`（无可信指标，不得写死） |
| OHLC 十字光标联动条 | 1765 `ohlc-row`（时间/O/H/L/C/涨跌/量，默认末根） | 仅图内 crosshair tooltip，页面级无条 | `已有`（`klineDataRef` 全字段在）——本页最大可落地差距 |
| MA 图例 chips | 1758-1761 MA7(info)/MA14(primary) | 无图例，指标在 ChartShell 指标系统内 | `已有`（纯展示件，需与指标配色对齐） |
| 交易对切换 | 1746-1751 卡头 `<select>` | 「切换品种」+ 搜索弹窗 | 形态差，`已有` |
| 周期档位 | 四档 15m/1h/4h/1d | `chartConstants.ts:13-35` 十档 | 现网超集 |
| 「28 根 · 内联渲染 · 非图表库」 | 1761 | 真图 500 根 | 原型自述文案，不适用 |

## 9. 因子分析 `/factor-analysis`（demo 1770–1888）

**结论：差距最小的一页。** 唯一纯展示遗漏是「覆盖率」列（`last_metrics.coverage` 实测在返回里）。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 「覆盖率」列 | 1796 | `FactorLibraryPane.tsx:200-319` 9 列中无覆盖率 | `已有`（`FactorOverviewPanel.tsx:67-72` 已消费同字段） |
| 「半衰期」列 | 1796 | 无 | `需聚合`（由 `inspection.decay` lag 序列推导），否则裁掉该列 |
| 副标「样本 1h 全品种 · IC 为 RankIC（日频）」 | 1774 | 刻意只写三段生命周期计数 | `已有`（有快照者读 params.interval/ic.method，仅对有待值因子显示） |
| 页头「批量回测」 | 1777-1778 | 只有「新建因子」 | `无源`（无 因子→回测 编排链路） |
| 详情承载 | 1867-1887 表下常驻块 + IC 时序小图 | Drawer 68% + 四 Tab | 数据 `已有`；最小切口是把 IC 时序图提到概览 Tab 顶部 |
| 「加入组合」+ 贡献权重 | 1883-1885 | 无 | `无源`（无组合权重概念） |
| IC 着色 | 按正负染 up/down | 语义阈值分档（good/mid/bad/flat） | 哲学不同，现网更强，不改 |
| 「入库 09-12」 | 1885 | 无创建时间字段 | `需聚合`（可退化为 `last_snapshot_at`） |

## 10. 策略研究 `/research`、`/research/:id`（demo 1890–1965 / 2281–2329）

**结论：差距最大的一页，且是能力缺口而非文案缺口。** demo 的三个卖点在现网都没有后端依托：一键转回测、产物下载、结论 md。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 「一键转回测」（列表 + 详情） | 1902/2290 + 底注 1964 | 前端两页与 `api/research.ts`、`backend/research/routes.py` 均无此端点 | `无源`（要做得先建「研究→回测配置」编排） |
| 「产物」块 + 下载 | 2305-2311 | 无产物概念（session 无文件字段） | `无源`（须新增产物落盘 + 下载链路） |
| 「结论」md 块 | 2295-2304 | 无 | `需聚合`（best trial 的 hypothesis/judge.reason/metrics/config 可前端拼装）——本页性价比最高的对齐项 |
| 副标口径 | 2286「参数 128 组 · 产物 3 个 · 研究员 liupeng」 | `ResearchDetail.tsx:526-529` 创建/轮次/最优 IC_IR | 参数组 `已有`（n_candidates）；产物、研究员 `无源` |
| 列表卡片摘要行 | 1920/1929/1938 `ic= · icir= · cov= · half=` | `ResearchList.tsx:473-490` 进度/最优 ICIR/成本三行 | `需聚合`（best trial 的 ic_mean/coverage） |
| 「参数扫描 Top 5」表 | 2314-2328 | 全量 trials 表 + 对比选择 | `已有`（需加按 Sharpe 排序视图；参数列仅对参数类场景有意义） |
| 类型体系 | 因子/参数扫描/实验/提示词 | mode(quick/deep) × scenario(factor/strategy/model) + 六态 | 立法学不同，以现网真实分类为准 |
| 搜索范围 | 标题 / 产物 | 名称 + ID 客户端过滤 | 现网更窄（后端无 keyword），`产物` 随功能一并缺 |

## 11. 数据管理 `/data-management(+/market-replay)`（demo 1967–2048）

**结论：结构不同层级。** demo 是单页四块流水（数据源水位卡 → 同步任务 → 存储用量），现网是四页签（品种/采集/质量/归档）；「同步任务表」已在采集页签内对齐得不错，缺的是首屏水位与存储用量。

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 顶层「立即同步」 | 1974 primary 钮 | 采集动作在 `?tab=collection` 表单内（`DataManagementPage.tsx:3151`） | `无源`（后端只有下载任务队列，无「增量同步」语义） |
| 「存储报告」弹窗 | 1975 + 2387-2401（保留策略/特征缓存/上次压缩/合计） | 无 | 体积 `需聚合`（目录 du + `_meta.json`）；「上次压缩」`无源`（无压缩/rollup job） |
| 数据源水位卡 ×4 | 1979-2008（健康 dot / 累计 bar / 最新 bar UTC / 落后 chip） | 无首屏；归档页签仅单选中品种 meta 四项 | 累计 bar `需聚合`（`_meta.json` total_rows 求和）；最新 bar 只能到日粒度；断连/限频 `无源` |
| 存储用量条形卡 | 2038-2047 | 无 | `需聚合`（du）；特征缓存/上次压缩 `无源` |
| 同步任务表（五列 + 进度条 + 失败红字） | 2021-2036 | `:1557-1640` 已对齐（进度条 `:1499-1509`、失败红字 `:1511-1516`） | `已有` |
| 状态 chips / 分页 | 2012-2017 四态 / 滚动加载 | `:3283-3301` 四态 / 服务端分页 20 | `已有`（分页口径差，行为等价） |
| page-sub | 1969「数据源 4 类 · 引擎放行 10 类 · 本地 parquet · 保留 180 天」 | `:3906`「数据类型 N 类 · 已接入标的 N 个」 | types=10 与引擎放行清单一致 `已有`；parquet/180 天属口径文案，须后端确认后写 |

反缺口：归档 K 线行内「行情回放」→ `/data-management/market-replay`（分块游标播放器），demo 完全没有。

## 12. 模型中心 `/model-hub`（demo 2050–2147）

| 差异点 | demo | 现网 | 可行性 |
|---|---|---|---|
| 页级「新建训练 / 重训台账」 | 2056-2059 + 2387/2415 弹窗 | 无页级钮；训练在「训练工作台」页签（`TrainingWorkbench.tsx:92-108`） | 训练 `已有`；重训台账 `需聚合`（`retrain_policy.py` 已有待审记录，缺列表 API） |
| page-sub「双闸关闭 · shadow 对照中 N」 | 2054 | `ModelHub.tsx:29-41` 只有角色计数 | `需聚合`（`AUTO_RETRAIN/AUTO_PROMOTE` env 真实存在，`retrain_policy.py:59-76`，缺只读端点） |
| 角色 chips | 2064-2070 五枚 | `UnifiedModelTable.tsx:178-186` 七枚 + 算法下拉 | 现网超集（「现役」= production，措辞差） |
| 模型卡 kv 行（关联 worker / 异常捕获 / shadow 战绩 / 归档原因） | 2083/2094/2105/2116 | `:523-544` 只有算法/状态/Sharpe/时间/大小 | 关联 worker `需聚合`（按 model_id 反查策略配置，现无接口）；其余三项 `无源`（registry 未落字段） |
| Sharpe 卡片染色 | 2082/2115 up/flat | `:529` 卡片无染色（表格列有） | `已有`（纯渲染） |
| 行选中 → 下方常驻详情块 + reward 曲线 + 对比条 | 2075-2078 + 2122-2146 | 点行只高亮（`:570-578`），详情走 Drawer（`ModelDetailDrawer.tsx:82-124`） | 详情数据 `已有`（walk_forward）；reward 曲线 `无源`（同步训练只回最终 metrics）；对比条 `需聚合` |
| 训练语义 | 2368「仅排队 + 双闸人工启动」 | `TrainingWorkbench.tsx:36-54` 同步长请求直跑 | **不可照抄**：现网无任务队列，UI 不得伪装排队 |

反缺口：第四页签「模型集成」（EnsembleWorkbench）、Drawer 里的 spec/features/files 分区。

## 横切结论

### 按落地成本分四档

**A. 纯展示补丁（数据全在，一天内可批量做）**
1. 策略管理：页头「发起回测」钮、副标口径重写；点行详情块（`params` KV 已在 `/strategy/list` 返回里）。
2. 回测中心：列表「区间」列（`/backtest/list` 行补 `start_time/end_time`，summary 已回传同字段）、副标第二段历史总数（`overallTotal` 已在 state）。
3. 回测中心：失败详情接 `error.message`、运行中接 progress 接口（后端都有，只是列表行没带）。
4. 行情图表：OHLC 十字光标联动条（`klineDataRef` 全字段在）、MA7/MA14 图例 chips。
5. 因子分析：补「覆盖率」列（`last_metrics.coverage` 实测在返回里）。
6. 首页：最近回测行带「区间 · 周期」；KPI3 副标按回测 status 计数（样本已拉 96 条）。
7. 模型中心：卡片 Sharpe 染色；page-sub 补双闸状态（需一个只读端点，10 行）。

**B. 要一次后端聚合（一个端点解决一页）**
1. 策略管理六列：`workers`（interval/symbols/status×trading_mode/count）× `strategies` × backtest 任务最新一条 —— 三张表一次 join，是本页改造的唯一硬依赖。
2. 数据管理：数据源水位（`_meta.json` total_rows 求和）+ 存储用量（du）。
3. 研究列表/详情：结论 md 块（best trial 的 hypothesis/judge.reason/metrics/config 前端可拼）、按 Sharpe Top N 视图。
4. 模型中心：模型→策略反查、重训台账列表、双模型对比。

### C. 明确不做（无源，做了就是造假）

草稿态（`strategies.status` 只有 active）· 版本历史 · OOS 口径 · 滑点 · AI 诊断结论 · 中途权益/预计剩余 · 资金模式「固定/复利」（后端只有 `per_symbol/shared`，两条不同轴线）· LLM/ML 类型细分 · 交易类系统指标（引擎耗时/交易所延迟/LLM p95）· WS 推送延迟 · 因子「加入组合/贡献权重」· 研究产物下载 · 模型 reward 曲线 · shadow 连胜/归档原因 · 数据压缩时间 · 训练「排队」语义。

### D. 形态级大改，需单独立项

1. `/strategy-worker` 决策流：表格 → ReAct 气泡流（依赖录制内容扩展 reasoning/tool trace，属**能力缺口**不是 UI 缺口）。
2. `/agent` 右栏：把「迭代足迹 + Dream」从 8 页签工作台搬回首屏。
3. `/strategy-worker` 主从同屏（现为两个路由）。
4. 研究「一键转回测」全链路（前端两页 + 后端端点皆无）。
5. 详情承载方式：因子/模型从 Drawer/选中高亮改为表下常驻详情块（demo 三处一致的使用范式）。
