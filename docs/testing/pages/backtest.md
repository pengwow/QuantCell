# 回测中心（/backtest、/backtest/config、/backtest/detail/:backtestId、/backtest/replay/:backtestId）

## 前置

- 环境与 token 注入见 `../README.md` 第一节；全部请求前缀为 `/api/v1`（`apiRequest` baseURL）。
- 四条路由共用 `BacktestLayout`，页头标题/返回按钮由各子页 `PageContainer` 提供。
- 列表页 `/backtest` 零种子可跑：无记录时走空态。
- 详情/回放需要**有效 backtestId**，取自下面任一来源（不要手写假 id，除非专门验 B21/B28）：
  - **API 预置/取现成记录**：`GET /api/v1/backtest/list` 返回 200，取 `backtests[0].id`（记录为空时先走 config 页发起一次回测）。
  - **由 config 页发起一次**：`/backtest/config` 选策略+标的+时间范围 → 「运行回测」，等进度弹窗走完或直接「终止回测」；两种方式任务都会落库，之后回到 `/backtest` 点该行「查看」进入详情。
  - 拿到 id 后可直开 `/backtest/detail/<id>`、`/backtest/replay/<id>`。
- **列表视图取决于系统设置「默认展示类型」**（`useViewType`，页面无切换器）：列表/表格视图与卡片视图的断言不同，逐项里已分别写明。
- config 页发起回测属重操作，依赖本地行情数据（预检 `GET /api/v1/backtest/precheck-data`）与 K 线下载，凡涉及真实下载/新数据的项标「按需」。
- 每项验证前刷新页面重置状态（README 第六节：重复触发会让请求互相 abort）。

## 验证项

### /backtest（回测列表）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| B1 | 打开 `/backtest` | 页头标题「回测中心」，副标为**双段计数**「任务表 N 条 · 历史共 M 条 · 引擎 kernel / legacy / python（默认 kernel）」：N = 当前页实际行数（`tasks.length`），M = `GET /api/v1/backtest/list` 无筛选时的真实 `total`（副标 M 不随筛选抖动）；右上「发起回测」主色钮 +「返回首页」默认钮；工具栏有搜索框（占位「搜索策略名称或ID」）、状态 chips「全部/完成/运行中/失败」与排序下拉；`GET /api/v1/backtest/list` 带 `page/page_size/sort_by/sort_order` 参数返回 200；无「加载回测列表失败」类 toast | L1 |
| B2 | 无历史记录时观察表格（空态） | 列表视图下九列表头「策略/标的 · 周期/回测区间/状态/收益率/最大回撤/订单/耗时/操作」全部可见（列序对齐 demo `#view-backtest`，独立的「时间/类型/标的/周期」列已下线），表体为图标块空态（「暂无回测任务」+「发起回测」mini 按钮，非 antd 灰图）；卡片视图下出现同款空态卡片、分页显示「共 0 条」，首屏不白屏 | L1 |
| B3 | 有 ≥1 条记录时观察表格（预置数据态） | 出现数据行，列序为 **策略→标的·周期→回测区间→状态→收益率→最大回撤→订单→耗时→操作**：策略列行首有展开三角（`.qc-cell-caret`，收起 ▸ / 展开旋转 90° 并转主色）、策略名 mono 截断（悬停出全名 Tooltip）、紧随一枚轻量类型徽章（9px 字号，比状态 chip 小一档）；RL 任务的 `strategy_name` 带 `rl_model:`/`rl_ensemble:` 前缀时为「来源 chip（RL 模型 主色 / RL 集成 蓝色）+ 模型名」两段式（沿用原模型中心「RL 回测历史」页签口径），无前缀任务仍为纯文本；标的·周期列见 B3i；状态为绿色「已完成」/蓝色带呼吸点「运行中」/红色「失败」/中性「等待中」chip 之一、收益率右对齐（正值绿/负值红/空「—」）、最大回撤右对齐但用中性前景色（幅度值不按符号染色，避免 0.00% 显示成亏损）、耗时列右对齐 mono 弱色并显示真实秒数（B3j）、操作列有查看/删除两个 24px 图标钮 | L1 |
| B3a | 观察「回测区间」列（表头「回测区间」，位于「标的 · 周期」与「状态」之间） | 单元格形如 `2025-09-01 → 2026-11-18`，两侧日期为 `YYYY-MM-DD`（后端 `start_time/end_time` 前 10 位），mono 弱色、单行不换行；展开任一 completed 行，该值与展开面板头 sub 段的区间（B4a）一致；任务行缺 `config.start_time` 的旧记录整格显示「—」（不拿创建时间冒充区间） | L1 |
| B3b | 观察「订单」列（表头「订单」，右对齐、位于「最大回撤」之后） | completed 且摘要为 v2 的任务显示整数（如 `236`），数值与展开面板「交易次数」KPI 及 `GET /api/v1/backtest/<id>/summary` 的 `metrics.total_trades` 一致；running/failed 或 v1 旧摘要任务显示「—」而非 `0`；数字为 mono 右对齐，无千分位以外修饰 | L1 |
| B3g | 观察策略列里的「类型」徽章（不再有独立类型列） | 每行策略名后跟着一枚类型徽章：`规则`=info 蓝、`RL`=pri 主色、`LLM`=warn 橙，字号 9px / 内边距 2px 5px（比状态 chip 轻一档）；取值来自后端 `/backtest/list` 的 `strategy_kind`，与 `curl /api/v1/strategy/overview` 同名策略的 `kind` 逐条一致（同一 `_strategy_kind` 口径）；`rl_model:`/`rl_ensemble:` 前缀的历史任务 → `RL`（模型中心直发不落策略文件）；**策略文件已删的历史任务 → 弱色「—」，不得按名字前缀猜类型**；展开该行后，面板头部的类型 chip 与列内徽章一致；卡片视图下卡片体首行「类型」右侧出现同一 chip | L1 |
| B3i | 观察「标的 · 周期」列 | 单标的行为 `BTCUSDT · 1h`（标的 mono 600 主色、周期弱色，单行不换行）；2 个标的用逗号连接（`BTC/USDT, ETH/USDT · 1h`）；≥3 个标的折叠为「首个标的 +N」徽章（N = 总数-1，`quiet` 中性 chip），悬停出全部标的全名 Tooltip；**自选组任务**（`/backtest/list` 行 `pool_id` 非空）显示 `【自选组】<pool_name> · N 个标的`，组名查不到（池已删）时退回「自选组」、不编造名字；全量标的与周期同时在 `title`/Tooltip 中；老记录无 `symbols` 显示「—」 | L1 |
| B3j | 观察「耗时」列（右对齐，位于「订单」之后、「操作」之前） | completed 且 DB 有 `started_at/completed_at` 的行显示真实执行时长（`42s` / `3m 05s` / `1h 07m` 形制，mono 11px 弱色）；`running`/`failed` 缺起止或差值 ≥48h（陈旧任务，前端按 `formatElapsedCompact` 省略）显示「—」而非 `0s`；数值与 `curl /api/v1/backtest/list` 返回的 `elapsed_seconds` 一致，并与该行 `/summary` 的 `elapsed_seconds` 口径相同（同源 DB 起止） | L1 |
| B3h | 工具栏「类型」下拉切到 `规则` / `RL` / `LLM` | 类型是**服务端过滤**（`GET /api/v1/backtest/list?kind=rule|rl|llm`），不是本地筛当前页：切档后分页条「共 N 条」= 后端返回的 `total`，选 `全部类型` 时不带 `kind` 参数；`RL` 档下所有行类型 chip 均为 `RL`、`规则`/`LLM` 档同理；切档后页码归 1；结果为空时走空态（B3f 的「清除筛选」可复位）；`curl '.../list?kind=llm'` 若库内无 LLM 策略返回 `total: 0` 属正常（不造假行） | L1 |
| B3c | 对照页头副标与列表计数 | 副标两段数字语义不同：首段「任务表 N 条」= 当前页行数（切分页/页大小后随之变化），次段「历史共 M 条」= 全量任务数；点状态 chips 或搜索收窄结果时次段 M 不变（仅分页条「共 N 条」变化） | L1 |
| B3d | 点一条**失败**任务行（本进程内失败、progress 快照仍在） | 展开面板在头部下方出现红色「失败原因」（有 stage 时形如「失败原因 · execution」），下一行 mono 弱色为该任务的 `error.message` 原文（可换行，不截断成一句话结论）；`GET /api/v1/backtest/progress/<id>` 返回 200 且 `error.message` 与展示一致；服务重启后 progress 内存快照丢失的旧失败任务只显示状态 chip、不显示任何编造的诊断文案 | L1 |
| B3e | 点一条**运行中**任务行 | 展开面板头部 sub 追加「已运行 <时长>」（如 `已运行 1h 07m`，由 `created_at` 到当前的差值计算；≥48h 的异常时长不显示）；下方出现「回测进度 NN%」（主色数字）+ 6px 高主色进度条（`role="progressbar"`，宽度 = `overall_progress`）；进度条与百分比与 `GET /api/v1/backtest/progress/<id>` 的 `overall_progress` 一致；不出现「预计剩余时间」「中途成交/中途权益」等无源字段 | L1 |
| B3f | 搜索一个不存在的关键字或选无结果的状态 chip（空态态） | 空态块内除标题/说明文案外出现「清除筛选」mini 按钮；点它后搜索框清空、chips 回「全部」、**类型下拉回「全部类型」**、排序回创建时间倒序、日期范围清空，并按默认参数重拉第一页（`GET /api/v1/backtest/list` 无 status/kind/keyword/start_time）；工具栏「重置」钮同时保留 | L1 |
| B4 | 单击某数据行 | 该行**就地展开**（不是列表下方常驻卡、不发生路由跳转）：行打选中底色（primary 5% tint + 左侧 3px 主色条），展开面板出现在该行正下方（`.ant-table-expanded-row > td` 内的 `.qc-exp-panel`），行首三角旋转 90° 转主色；再点同一行收起；点另一行先收起旧行、只保留一行展开（单行互斥）；操作列眼睛钮进 `/backtest/detail/<id>`、删除钮走 Popconfirm，两者点击不触发行展开（`stopPropagation`）；**页面初次加载不自动展开任何行** | L1 |
| B4a | 展开一个已完成任务，观察展开面板 | 面板外层 `.qc-exp-panel`（1px 边 + ~10px 圆角 + 10px/12px 内边距，底色与表格展开行统一），内层 `.bt-summary` 不再叠第二层卡框；头部「回测详情」13px/650 + 策略名 mono + 与行一致的类型/状态 chip + mono 弱色 sub「创建 MM-DD HH:mm · <起> → <止> · <周期> · 耗时 …」（创建时间已从独立列移到这里，各段缺则自动省略，≥48h 的陈旧耗时不显示）；中部 `.qc-kpi-grid` 5 列：总收益率/夏普比率/最大回撤/交易次数/胜率，数值与 `GET /backtest/<id>/summary` 及详情页口径一致（正绿负红、0 中性不染色、缺失槽位整张不渲染不造数）；KPI 下方权益曲线块（`.bt-curve`，8px 圆角 + 内边距 12/12/8 + 三条虚线格线）：折线+渐变面积按走势染色（末>首绿 / 末<首红 / 平线中性不画面积），右上「期末 NAV」取组合真实 `final_equity`，x 轴 8 档等分真实时间戳刻度（跨度 ≥90 天用 YY-MM，否则 MM-DD，连续重复折叠）；底部虚线上边的 mono 配置脚注「初始资金 … · 手续费 …% 单边」（DB `backtest_config` 有值才显示） | L1 |
| B4a1 | 点一个 2 天区间的已完成任务 | x 轴刻度退化为日粒度且不重复（如「05-01 / 05-02 / 05-03」而非 8 个「26-05」）；权益块点数 ≤200（服务端均匀采样保首尾），曲线形态与该任务回测区间走势一致 | L1 |
| B4a2 | 暗色主题下重复 B4a | 权益块背景为暗色页面底、边框弱化、跌势折线为暗色主题红、刻度为弱色，不出现白底块 | L1 |
| B4b | 展开运行中/失败任务，观察展开面板 | KPI 区不渲染（无假 0）：运行中只有头部（chip 带呼吸点）+「已运行 …」sub + 真实进度条（B3e），无进度快照时只剩头部；失败任务展示红色「失败原因」+ mono `error.message`（B3d），取不到快照则仅头部；两者都无配置脚注时不渲染脚注；首次点旧任务（v1 摘要）后端一次性读结果文件可能有 1–2s 骨架屏，之后走任务文件 v2 + 前端缓存毫秒级 | L1 |
| B4c | 展开某行后翻页 / 改搜索 / 切状态 chip / 改日期 / 改排序 | 上述任一操作都会自动收起展开面板（列表重载即清空展开 key，不跨页/跨筛选残留）；回到原页再次展开该行仍秒开（单行轻摘要缓存保留，不发第二次 `/summary` 请求） | L1 |
| B4d | 直开 `/backtest?strategy=<已存在策略名>`（或从策略管理点「累计回测 N 次 →」，见 `strategy-management.md` S29） | 搜索框预填该策略名、工具栏出现来源提示「策略 <名> ×」；列表是该策略的任务（服务端 `keyword` 过滤，翻页/排序照常）、分页条「共 N 条」= 后端 `total`；副标「历史共 M 条」仍是**无筛选**口径的真实全量数（首屏带筛选时页面会补一次无筛选计数请求，不得显示 0）；提示不影响状态 chips / 类型下拉的独立筛选 | L1 |
| B4e | 展开任一行，看面板头部下方的「策略档案」行 | 盘内出现类型 chip（`rule`/`rl`/`llm`，与行内徽章同源于后端 `strategy_kind`）与右对齐「查看策略 →」；点它跳 `/strategy-management?focus=<策略名>`，落到策略管理后搜索框预填该名、该行就地展开并滚动定位（策略已删则不展开、不造行）；**策略文件已删的历史任务**（`strategy_kind = null`）显示「该策略不在策略列表（可能已删除）」且无链接按钮（不得留死钮或编造类型）；`rl_model:`/`rl_ensemble:` 前缀的模型中心直发任务显示「RL 模型任务 · 策略档案见模型中心」且无策略链接 | L1 |
| B4f | 带 `?strategy=` 进来后点提示 chip 的 ×，或在搜索框改成别的关键词 | 提示 chip 消失、地址栏 `strategy` 参数被移除、列表回到未带策略筛选的第一页（搜索词清空、chips/类型/日期/排序不动）；只改搜索词（未点 ×）时来源提示同样撤掉（它只代表「由策略详情带过来的那一次筛选」），搜索按新词重查 | L1 |
| B4d | 键盘操作 | Tab 能聚焦到数据行（行 `tabIndex=0`、`aria-expanded` 随展开态变化）；聚焦行上 Enter 或 Space 切换展开/收起（不跳详情页）；Esc 收起当前展开行（焦点在输入框内时不抢键）；删除仍只能走操作列的 Popconfirm | L1 |
| B4e | 展开一条自选组任务（或 ≥3 标的任务） | 展开面板头 sub 第一段是「创建 MM-DD HH:mm」（与任务 `created_at` 一致）；行内「标的 · 周期」列在自选组任务上为 `【自选组】<pool_name> · N 个标的`（`pool_id` 非空即此形态），≥3 标的非自选组任务为「首个标的 +N」徽章；面板指标/曲线与该任务 `/summary` 真实值一致，不因形态不同换一套数据 | L1 |
| B4f | 切到卡片视图后点卡片（对照 B4/B4a） | 卡片与列表是同一份数据的两种排版，点开必须是**同一块详情面板**：面板出现在被点卡片所在视觉行的正下方（该行最后一张卡之后，16px 行距），跨整行宽度（≈ 网格宽减左右 8px 槽，不窄成单卡宽），同行其他卡不被挤走/换行（1440 宽下同行仍 4 张，首行卡位置不动，面板顶边 ≥ 该行卡底边）；面板内容与列表视图点开同一任务的面板 `innerText` 归一空白后**逐字相同**（`.qc-exp-panel` 只包一层，不叠第二层）；再点同一卡片收起，Esc 收起；点卡内眼睛钮跳 `/backtest/detail/<id>`、删除钮只弹确认，都不触发展开；切分页/改搜索/切状态 chip/改排序后卡片面板收起；首载不自动展开 | L2 |
| B5 | 点击「发起回测」 | 跳转 `/backtest/config`，页头「回测配置」；点「返回首页」跳转 `/home` | L1 |
| B6 | 在搜索框输入一段不存在的关键字后回车 | 服务端收到 `keyword` 参数，结果收窄为空态「没有匹配的回测任务」+ 说明文案（`.qc-empty` 图标块，非 antd 灰图），计数「共 0 条」；点「重置」后恢复、搜索框清空 | L1 |
| B6a | 点状态 chips「完成 / 运行中 / 失败」 | 选中 chip 主色 tint；每次点击 `GET /api/v1/backtest/list` 带 `status=completed/running/failed` 且页码归 1；点「全部」清除 status 参数；「运行中」chip 由后端同时匹配 `in_progress` | L1 |
| B6b | 列表底部 | 分页条为 1px 上边线的自绘条：左「共 N 条 · 每页 [12|24|36|48|96]」、右页码钮（28px，当前页主色 tint）+「跳至 N 页」；切档位立即按新 `page_size` 请求；空态搜索时表格空态替换掉 antd 灰图 | L1 |
| B6c | 工具栏「时间范围」RangePicker 选 2026-11-01 ~ 2026-11-03 | `GET /api/v1/backtest/list` 带 `start_time=2026-11-01&end_time=2026-11-03`，展开任一行后其面板头的「创建 MM-DD HH:mm」落在区间内、计数「共 N 条」为过滤后真实值（本地库当前约 228）；日期含端点（止日当天创建的任务在内）；清空控件或点「重置筛选」后恢复全量；格式非法的日期串后端返回 422 | L1 |
| B29 | 展开一条 running 任务后不再点击任何行，观察 15s+ | 展开面板「已运行 …」sub、进度条与百分比每 15s 自动更新一次（源仍是 `GET /api/v1/backtest/progress/<id>`，Network 面板按 15s 周期出现该请求）；切到另一行 / 收起 / 任务转终态后轮询停止（45s 内不再出现该请求），手动点行仍可立刻刷新一次 | L2 |
| B30 | 点一条 `strategy_kind=llm` 的**失败**任务行，再切到 `/backtest/config` 选中 `mode=llm` 的策略 | 列表行内摘要的失败块下方出现弱色说明（LLM 回放未命中不降级、任务直接终止）；`/backtest/config` 选中 `mode=llm` 策略时「策略参数配置」卡底部出现同一句说明；非 LLM 任务不出现该提示 | L1 |

### /backtest/config（回测配置 / 发起）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| B7 | 打开 `/backtest/config` | 页头「回测配置」+ mono 弱色副标（形如「默认 runner = kernel（统一内核）· 初始资金 1,000,000 USDT · 手续费 0.1% 单边」，初始资金/手续费取表单实时值）；右上「← 返回」默认钮 +「运行回测」主色钮（30px 高）；三张卡标题「回测范围」「成本与账户」「策略参数配置」可见，前两张并排等分、第三张通栏；`GET /api/v1/strategy/list`、`GET /api/v1/config/`、`GET /api/v1/data-pools/collection/symbols`、`GET /api/v1/factor/list-detail` 均返回 200 | L1 |
| B8 | 观察表单 | 字段标签全部可见：策略名称、标的、时间范围、K 线周期、交易模式、手续费率（单边）、初始资金、资金使用方式、回测因子；「K 线周期」为分段器（mono 裸值 1m/5m/15m/30m/1h/4h/1d，不丢档位）；「资金使用方式」为分段器（各标的独立资金池/组合共享资金池），单标的时禁用态；未选策略时参数卡占位「请先选择策略以配置参数」；「交易模式」与「回测因子」下方有 11px 弱色说明行 | L1 |
| B8a | 改「手续费率」或「初始资金」输入 | 页头副标数字随之实时变化（mono 千分位/百分数），不改输入即不跳变 | L1 |
| B8b | 展开「标的」下拉并搜索 | 与全站同一个 `SymbolSelect`：上部自选组组项在前、下部裸标的后；组项为「组色圆点（8px 圆）+ 组名 + 弱色『N 标的 · 自选组』计数」，圆点颜色取自数据管理页该组的自定义色（未设色回落 info 蓝），不出现 ⭐ emoji/星标图标；搜索输入组名或 symbol 均能命中对应项 | L1 |
| B8c | 下拉里选一个自选组，再看已选 chips | 选组**当场**展开为组内全部标的分立 chip（不再显示 `pool_` 组 chip），去重且保持顺序；删掉其中一个 chip 只影响该标的；提交（走 B11）后的回测任务标的 = 展开后的标的列表（详情页副标可见），下游资金池 `pool_id` 等逻辑不受影响 | L2 |
| B9 | 在「交易模式」选「现货」，再改选「永续合约」 | 现货下「成本与账户」卡内不出现「杠杆与保证金」区块；切到永续合约后该区块出现（同卡内、「回测因子」下方），未选标的时区块内提示「请先在上方选择标的」 | L1 |
| B10 | 选一个策略，观察策略下拉与参数区 | 策略下拉项可见策略名与描述；选中后「策略参数配置」卡出现该策略的参数输入项，且卡头右侧出现 mono 弱注「来自策略档案 <策略名> · 可覆盖」，或显示「该策略没有可配置参数」；**多标的时参数表单下方出现「<标的> · 覆盖参数」按钮组（Badge 显示各标的覆盖项数，初始 0）** | L1 |
| B10a | 选 grid 策略 + 两个标的，点 BTC 的「覆盖参数」 | Popover 逐字段表单（顶部「留空 = 继承公共参数」注），BTC 填 lower/upper 后 Badge=2；点「运行回测」后 `POST /api/v1/backtest` 的 `strategy_config` 带 `strategy_params_by_symbol`（键 `BTC/USDT`）；回测完成后详情页「配置信息」卡「策略参数」chip 组下方出现「覆盖参数」分组列出 `BTC/USDT：{"lower":…,"upper":…}`；另一标的走公共参数（或 ref 推导），两标的回测结果（成交价分布）随覆盖分化；清空覆盖字段后该键不提交 | L2 |
| B11 | 选策略+标的+时间范围（默认近 30 天）后点页头「运行回测」 | 按钮进入 loading 态（校验不过时会停在表单并标红必填项，不发请求）；随后先弹「回测进度」弹窗（预检失败时会自动关掉），同时发 `GET /api/v1/backtest/precheck-data` 200；数据齐备时随后发 `POST /api/v1/backtest/run` 200，弹窗内出现「数据准备」「执行回测」「结果统计」三段，并持续轮询 `GET /api/v1/backtest/progress/<taskId>` 200；运行中且弹窗关闭时页头额外出现「查看回测进度」按钮。**收尾**：点弹窗「终止回测」并确认（toast 出现「回测已终止」/终止相关提示），或等三段走完后 toast「回测已成功完成！」。任选其一，不要中途直接关浏览器 | L2（按需：依赖本地 Parquet 行情数据） |
| B12 | 走完一次 B11 后刷新 `/backtest/config` | 表单被上次提交的配置回填（标的/周期/手续费/初始资金/交易模式有值）而非空表单——这来自 localStorage `lastBacktestConfig`，属预期行为 | L1 |
| B13 | 预检返回缺失数据时（`precheck-data` 返回 `all_available=false`） | 弹出标题「数据缺失提醒」的弹窗，正文含「以下 N 个品种×周期缺少本地数据，回测前需要下载」，缺失项以橙色标签「<symbol> · <interval>」列出，底部按钮「取消」「下载并回测」；点「取消」后不发 `POST /api/v1/backtest/run` | L2 |
| B14 | 在「数据缺失提醒」弹窗点「下载并回测」 | 创建下载任务（`POST /api/v1/data/download/crypto` 200），随后每 2s 轮询 `GET /api/v1/data/task/<taskId>` 200，弹窗内出现进度条与逐品种「<symbol> · <interval>  xx% / 下载完成」；下载完成后自动回到「回测进度」弹窗。仅在需要真实下行网络时执行，可点弹窗关闭中止前端轮询（后端任务可能继续） | 按需 |
| B14a | 走完一次 B14 下载闭环后，确认「下载并回测」的回测真的吃到了数据：后端日志检索 `成功加载 Parquet 文件: .*backend/data/source/crypto/.*/klines/` 与下载日志中「合并后共 N 行」路径一致（均为 `backend/data/source/crypto/...` 单文件，不再出现 `~/.quantcell` 路径）；进度弹窗「数据准备」段不再循环出现下载后仍缺失 | L2（按需） |
| B15a | 视觉抽查（≥1280 宽视口） | 两卡等分且卡间距 12px；卡片 10px 圆角、无卡头分隔线；字段 label 为 11px mono 弱色；控件高 32px、8px 圆角；分段器内钮 24px 高、选中档为 primary 12% 淡底 + 主色字；无横向滚动 | L1 |

### /backtest/detail/:backtestId（回测详情）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| B15 | 直开 `/backtest/detail/<有效id>` | `GET /api/v1/backtest/<id>` 返回 200；页头「<策略名> - 回测详情」，下方 mono 弱色副标「<标的,逗号连接,> · <周期> · <起> → <止>」只写真实数据（缺项自动省略、不渲染假 0）；右上出现「回放」主色钮 +「导出报告」默认钮（30px 高）；「配置信息」卡为 .qc-card（10px 圆角、无卡头分隔线），字段 label 说明同前，周期/回测时间/初始资金为 mono 数值，状态为「已完成/运行中/失败/等待中」chip；卡内「杠杆与保证金」「策略参数」各为 chip 组（未启用保证金时出弱色注「未启用保证金」）；无 antd bordered 表格边框 | L2（需有效 backtestId，见前置） |
| B16 | 观察「回测概览」指标卡 | 至少「总收益率」「最大回撤」「夏普」等 KPI 卡为 §6.4 三层结构：11px 弱色 label → mono 22px/650 数值（涨/盈绿、亏红、中性不染色：最大回撤是幅度值，恒不按符号染红）→ 悬浮图标有口径说明；显式为 null 的指标显示「—」；卡片 auto-fill 网格排列（1440 宽下多列、不横向滚动）；多品种任务卡头右侧出现「品种」下拉（含「全部」+ 各品种） | L2 |
| B17 | 观察「权益曲线」卡片 | 有曲线时渲染出折线图（不只有空白卡片、控制台无图表初始化报错）；无数据时显示 `.qc-empty` 图标块「暂无权益曲线数据」（非 antd 灰图） | L2 |
| B18 | 观察「交易详情」卡片 | 标题「交易详情」+ 卡头右侧「筛选」小按钮；展开后筛选区是内嵌面板（bge 底 + 1px 边 + 8px 圆角：标的/方向/日期范围 + 重置）；计数「共 N 条」为弱注行；有完整交易时 TradeTable 出现「时间/方向/开仓价/平仓价/数量」等列；round-trip 为空但有逐笔成交时显示蓝色信息条 + 逐笔表（时间与价格/数量 mono、方向为绿「买入」/红「卖出」chip、数值右对齐、底部自绘分页条）；两者都无时显示 `.qc-empty` 图标块空态（无成交/旧引擎文案见雷区） | L2 |
| B19 | 观察「决策详情」卡片（仅当该回测结果为 LLM/cascade 策略时出现） | 卡片标题「决策详情」；统计行为弱注「共 N 条决策」+ 三组 chip：「决策者」S1 蓝/S2 主色/规则绿（计数 mono）、「动作」开多绿/开空红/持有中性、「降级兜底」前 5 原因中性 chip；表格为 DataTable：时间列 mono（悬停出原串 Tooltip）、动作为 chip、置信度 mono 右对齐（空「—」）、决策者 chip、降级原因空「—」；分页条为自绘 .qc-pg-bar（每页固定 200 条 + 跳页）；点行内「详情」开抽屉，`GET /api/v1/backtest/<id>/decisions/detail?seq=..&fingerprint=..` 返回 200 | L2（按需：依赖该记录含 decisions） |
| B20 | 点「导出报告」 | `GET /api/v1/backtest/<id>/report` 返回 200 并触发浏览器下载一个 `.html` 文件，文件名含「回测报告」与 id 前 8 位 | L2 |
| B21 | 直开 `/backtest/detail/not-a-real-id`（无效 id） | 页面显示 `.qc-empty` 图标块空态「未找到回测数据」+ toast「加载回测详情失败」，不白屏、不无限转圈 | L2 |
| B22 | 点「回放」 | 跳转 `/backtest/replay/<id>`（若多品种可能带 `?symbol=` 查询参数），见 B23 起 | L2 |
| B31 | URL 直达 `/backtest/detail/<id>`，该任务 status=failed 且本进程内失败（progress 快照仍在） | 页首（「配置信息」卡上方）出现「失败原因」错误块：红字标题「失败原因」+ `stage`（有值时形如「失败原因 · execution」），下一行 mono 弱色为 `error.message` 原文（可换行、不截断）；服务重启导致 progress 快照丢失时**整块不渲染**（只剩状态 chip，不留空块/占位文案） | L2 |

### /backtest/replay/:backtestId（逐 bar 回放）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| B23 | 直开 `/backtest/replay/<有效id>` | `GET /api/v1/backtest/<id>/symbols` 200、`GET /api/v1/backtest/<id>/replay?symbol=<symbol>` 200；页头「回测回放」+ 数据加载后 mono 弱色副标「<品种> · <周期>」（未加载不渲染占位）；控制卡为 .qc-card：「货币对」下拉有选中值，播放/暂停为 48px 圆形主色钮（primary 光环）、停止=红色图标钮、「单步前进」「快进10步」图标钮可点（图标无文本，用 tooltip/aria-label 定位），速度下拉默认 `1x`；右下角当前时刻为 mono 时间胶囊（1px 边框圆角） | L2（需有效 backtestId） |
| B24 | 点播放，等若干秒 | K 线图区域出现蜡烛柱并向右推进（不是空白画布）；进度滑块左侧的当前序号递增（mono）、第三行当前时间戳 mono 推进且百分比 `%` 变大（蓝色 mono）；鼠标悬停滑块时 tooltip 显示「第 N / M 根K线」+ 该 bar 时间 | L2 |
| B25 | 点「停止并重置」 | 进度回到第 1 根（滑块左侧序号为 1、百分比 `0%`），播放按钮回到播放态 | L2 |
| B26 | 拖动进度滑块到中段/末段 | 「交易详情」卡片计数「共 X 条记录 (总 Y 条)」中 X 随位置单调增大（只显示当前时间点之前的成交），下方表格随之增长，无控制台报错 | L2 |
| B27 | 多品种回测（`symbols` 返回多于 1 个）时观察右上角 | 出现「品种视角 / 全局视角」分段器（§6.9 几何，不要人为加样式类）；切到「全局视角」后 `GET /api/v1/backtest/<id>/replay/portfolio` 返回 200 并渲染组合视图：口径说明蓝色信息条；时钟卡 .qc-card（周期为 mono chip、主播放钮带 primary 光环、右下 mono 时间胶囊）；账户状态卡为 KPI 网格（mono 22px：总权益/可用/保证金中性、累计/当日盈亏涨绿亏红、当前回撤为幅度值恒中性不染红）；「行情背景」与「组合权益曲线」卡头右侧分别为品种下拉与曲线图；「当前持仓」表为 DataTable（数量/均价/最新价/市值 mono 右对齐、方向为绿「多」/红「空」chip、浮盈亏涨绿亏红 mono）；「跨品种成交流」计数为弱注、新成交行有信息蓝短暂高亮。单品种任务不出现该切换器（如实记录即可，不算失败） | L2 |
| B28 | 直开 `/backtest/replay/not-a-real-id`（无效 id） | 当前实现：后端对不存在 id 返回 200 + 空 symbols（见雷区），页面停在空骨架（控件无数据、进度静止 0%）不白屏不报错；仅当请求在传输层失败（后端拒绝/超时，axios 30s）才出「错误」提示条 + toast「加载回放数据失败，请稍后重试」 | L2 |
| B31 | 配置页填好时间范围与周期（如近 30 天 · 15m） | 交易模式卡底部出现 mono 弱态行「预计运行约 N bar（估算：起止 ÷ 周期，未计缺 bar）」；周期 1h→15m 或拉长区间时 N 同步变大；清空任一日期 → 该行不渲染（属预期，不显示 0） | L1 |
| B32 | 交易模式切「永续合约」，看「杠杆与保证金」的 extra | extra 文案含「引擎尚未把乘数计入名义价值，币本位为近似账务」（对齐 demo 2243-2245/2704 警示）；现货模式无该字段，不得把警示句挂到现货 hint | L1 |
| B33 | 展开一条 completed 回测行，数行内摘要卡 | 摘要含 7 张卡：总收益/夏普/最大回撤/成交/胜率/盈亏比/交易日（11-25 起）；旧任务缺 `profit_factor`/`duration_days` 时对应卡不渲染（缺失跳过，不显示 0 充数）；盈亏比 0.92 类中性值不上红绿 | L1 |
| B34 | 回测详情 → 回放页（单品种视角）打开「价格计划」开关 | 档位横线叠加在 K 线上、端点铺满回放区间，与既有成交标记形成「计划 vs 实际」对照；切到组合视角线自动清除，切回单品种重画；关闭开关即清线无残留；preview 失败（无 price_plan 策略）静默不画线、不弹错误 | L2 |

### 作业池观测（后端 API `/api/v1/jobs/queue`）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| B29 | 空闲态请求 `GET /api/v1/jobs/queue` | 返回 200 且 `code=0`；`data` 含 `queued`/`running`/`cores`/`blocked` 四个键，`pools` 下有 `backtest`/`rl_train`/`hpo_trial` 三池；未跑过作业的池 `created=false`、计数为 0；连续请求两次 `created` 仍为 false（查询不会触发建池） | L1 |
| B30 | 发起一次回测后立刻再请求 `/api/v1/jobs/queue`，并用该 taskId 搜后端日志 | `pools.backtest.created=true`，`queued + running ≥ 1`；后端日志可搜到同一 `job_id=<taskId>` 的 `event=enqueue` → `event=start` → `event=finish`（失败/终止分别为 `fail` / `cancel`），单个 job_id 即可串联全链路 | L2（按需：需真实发起回测） |
| B31 | `cd backend && .venv/bin/python -m cli jobs selftest`（命令行，不起 API 服务） | 退出码 0，9 项自检全部 PASS：真并行区间相交、worker 复用、终态计数保留、排队满拒收 `JobPoolFullError`、`cancel_queued` 语义正确、`shutdown(wait=False)` 不留孤儿进程 | L1（CLI 自检） |

## 历史雷区

- **回测按标的参数覆盖（2026-11-28）**：`strategy_config.strategy_params_by_symbol`（键 `BTC/USDT` 规范化形态）随 `backtest_config` 一并入库（`backtest_config_dict["strategy_params_by_symbol"]`），详情页与任务文件都能溯源。合并唯一出口 `strategy/param_resolver.py`（公共 < 覆盖，`None/''` 不覆盖）；独立/共享资金池两路径都逐标的解析。**无覆盖时维持单一实例复用**（回归口径：loader 只调 1 次），加新回测路径时别顺手改成永远逐标的加载，也别写第二套合并
- **详情堆在表格下方导致用户发现不了 → 已改行内展开**（2026-11-23）：旧实现点行只在表格**底部**渲染一张摘要卡，行多时要滚到最下方才能看到，且翻页后面板与行脱节。现改为 antd `expandable` 行内展开（`expandedRowKeys` 单键数组互斥、`expandRowByClick`、`showExpandColumn: false`，三角自绘在策略列），面板随行移动；翻页/筛选/搜索/日期/排序重载会清空展开 key（面板不跨页残留），但 `/summary` 缓存不清（重新展开秒开）。别再往表格下方塞常驻卡。
- **列表新增 `pool_id / pool_name / elapsed_seconds` 三字段**（2026-11-23）：`pool_id` 来自任务文件 `config.pool_id`（发起回测时原样入库），`pool_name`/`elapsed_seconds` 由 `routes.attach_list_extra_fields` 按页内 id 一次批量查（`data_pools` / `backtest_tasks`），不是 N+1；查询失败或字段缺失一律 `null`（前端「—」/「自选组」），不要为了好看回填 0 或空串。改列表筛选/排序/分页逻辑时别把这段补字段挪进循环。
- **「类型」列必须走后端 `strategy_kind`**（2026-11-21）：类型是策略文件 AST 的判定结果（`strategy_type`=RL，或参数 `mode="llm"`），前端**不得**用 `strategy_name` 前缀/后缀猜（`ml_`、`rl_` 命名纯属用户自由，前缀只对 `rl_model:`/`rl_ensemble:` 这两种模型中心直发的任务成立）。策略文件已删但历史任务还在时后端返回 `null`，页面显示「—」——这是真实值，不要为了「好看」回填 rule。
- **类型筛选在服务端、且与列同源**（2026-11-21）：`kind` 过滤发生在 `get_result_list` 的排序/分页**之前**（`kind` 非法值由 FastAPI `pattern` 挡成 422），所以「共 N 条」是真实过滤后总数，不是当前页剩余行数。别把它退化成前端 `tasks.filter()`——那样翻页后每页条数会缩水，且已删策略的行（kind=None）会行为诡异。`strategy_kinds()` 按策略文件 mtime 缓存解析结果，改完策略文件重新加载进程才需担心旧值（mtime 变了会自然重解析）。
- **「策略档案」行的存在性判断只用后端 `strategy_kind`**（2026-11-24）：该字段由策略文件 AST 判定，`null` 表示策略已删且无记录，此时显示「该策略不在策略列表（可能已删除）」且不给链接——不要按名字去 `strategy/list` 里碰运气匹配，也不要给 `rl_model:`/`rl_ensemble:` 前缀任务造策略链接（那些是模型中心直发的任务，档案在模型中心）。反向入口 `?focus=` 只在策略管理的首载 effect 里消费一次，且必须等 overview 数据到位后再展开（首轮 `items` 为空，提前清标记会导致永不定位）
- **展开面板曾整体无样式（已修）**：`BacktestList.tsx` 历史上从未 `import './backtest.css'`（列表老样式全走 global 原语故未暴露），本次新增 `.bt-summary` 后类名命中但规则不加载——表象是「面板裸奔无 chrome」，且极易误判为 vite 缓存/HMR 问题。凡在 BacktestList 加布局级新类，先确认该 import 还在。
- **展开面板全 0.00% 是真数据不是 bug**：`backend/data/backtest_tasks/` 里确有零交易完成任务（如 dd55bf6f，metrics_summary 全 0），面板如实渲染且 0 中性不染色；判断染色 bug 时先核对该任务文件值，别拿它当回归样本验证正负染色。
- **行内曲线是采样不是全量**：`/summary` 的 `equity` 是服务端均匀采样 ≤200 点保首尾（`_sample_equity_curve`），首次点击 completed 旧任务会完整读一次结果 JSON 并回写任务文件 `equity_sampled`（空数组 = 已查无曲线的哨兵，别删字段否则每次点击都重新大 IO）；详情页才是全分辨率曲线。要提精度改采样上限而不是前端插值。
- **URL `?status=` 列表页不消费，`?strategy=` 消费**（2026-11-24 修订）：BacktestList 只认 chips 触发的状态 state，`navigate('/backtest?status=completed')` 不会筛选（首载恒为全部）。`?strategy=<name>` 是唯一被消费的列表参数 —— 它只在**首载**作为搜索词初始化（`useState` 初值），之后以工具栏的来源提示 chip 表达；清掉 chip / 改搜索词时同步从地址栏移除该参数。要新增 URL 过滤参数就照这个形状写，别指望受控 state 自动跟随 URL 变化。
- **列表页 Delete 键直接删除（已修）**：此前代码在 `keydown` 里对选中行直接调删除接口、不弹确认。现已移除键盘删除，删除只能走操作列图标钮的 Popconfirm 确认（访客禁用）。B 系列验证按鼠标路径即可；若在别的页面复现"按键即删"，属于新 bug。
- **列表未走服务端分页（已修）**：此前 `getBacktestList()` 不带参数、前端拉全量后过滤+假分页（记录数上千时首屏拉全量）。现已接入 `page/page_size/status/keyword/sort_by/sort_order`，B1/B6a 的请求参数断言是本条的回归哨。日期范围筛选一度因后端无过滤参数而从工具栏移除，现已补回：`/backtest/list` 支持 `start_time/end_time`（created_at 日粒度、含端点、格式 `YYYY-MM-DD`，非法 422），工具栏恢复 RangePicker（demo 工具栏无此控件，属显式需求扩展），B6c 为回归哨。
- **RL 回测历史已并入本页（页签下线）**：模型中心第四个页签「RL 回测历史」已删除，旧 `?tab=history` 走 ModelHub 的 replace 重定向落到 `/backtest`。回测中心默认列表本就返回全量任务（`/backtest/list` 缺省 `source=None`），RL 任务靠策略列来源 chip 区分，不再有「只看 RL」的独立视图；`source=rl` 仍是 `/backtest/list` 的有效参数（OpenAPI 有描述、单测 `test_backtest_list_source_filter.py` 守护），要按来源筛时前端传它即可，别重新造页面。
- **回测自动下载→回测读取三口径曾脱节**（2026-11-27）：完整性检查查 DB（毫秒/纳秒错配恒报缺）、独立下载器落 DB 副本 + 另写 `~/.quantcell/data/kline` 按日分片（无人读的死存储）、回测读 source 单文件 parquet 被绕过 → 下载完成仍报不完整 死循环。现已统一：检查切 parquet 口径、skip 检查查 source 文件、下载同时落 DB 副本并合并进 source 单文件、get_source_data_dir 跟随 `QUANTCELL_DATA_DIR` 重定向；`~/.quantcell` 分片写入已删除。存量分片不迁移（spec 决策）。

- **副标「任务表 N 条 · 历史共 M 条」是两段口径**：N = 当前页行数（`tasks.length`，翻页/切页大小即变），M = 无筛选请求刷新的全量 `total`（带 status/keyword/日期筛选时不动）——这不是不同步 bug；B6a 的筛选只应改分页条/计数的「共 N 条」而保留 M。
- **失败原因是内存态快照**：展开面板的「失败原因」/运行中进度条数据来自 `GET /backtest/progress/<id>`，progress tracker 只存进程内存（`progress_tracker.py` 无落盘），服务重启后旧任务的失败原因查不到 → 前端按「无源不渲染」处理，只留状态 chip。验证 B3d/B3e 必须用**本次进程内**刚失败/正在跑的任务；"旧失败任务没有原因"不是丢样式。
- **「区间」/「订单」列来自任务行而非结果 JSON**：`/backtest/list` 行的 `start_time/end_time` 取任务文件 `config`（与 DB 行同源），`total_trades` 取 `metrics_summary.metrics`（v2 摘要）。v1 旧摘要没有 `metrics` 字典 → 订单显示「—」，要补就得让该任务走一次 summary 升级（点行即可），列表加载时不会批量读大结果文件。
- **config 页会静默回填上次配置**：`localStorage.lastBacktestConfig` 在提交时写入、进入时回填标的/时间/周期/手续费/初始资金/交易模式。第二次进入时"空表单"类断言必然失败，属预期；要净环境先 `localStorage.removeItem('lastBacktestConfig')` 再刷新。
- **进度弹窗的「关闭/取消」≠ 终止回测**：关闭只停前端轮询，后端任务若已创建会继续跑完并落库（代码注释明确如此）。真要停必须点弹窗内「终止回测」并确认（`POST /api/v1/backtest/stop`，后端限时等线程退出，超时返回 `forced`）。副作用：被"取消"的任务之后会出现在列表里，正好可拿来当详情/回放的种子 id。
- **发起有 30 秒硬超时**：`/backtest/run` 30s 未返回会 abort 请求并报「回测启动超时，请检查网络连接或代理配置」。打包 onefile 冷启动或首屏加载大 K 线时可复现，重试一次即可，别当功能缺陷。
- **预检下载轮询最长 10 分钟**（每 2s 一次 `/api/v1/data/task/<id>`），关弹窗只 `abort` 前端轮询，后端下载任务可能仍在跑——再点一次「下载并回测」可能产生重复下载任务。
- **旧回测记录没有 fills_detail / decisions**：交易详情会落到「该回测由旧版本引擎生成，无成交明细」，与"策略根本没成交"的文案不同但视觉上很像；`决策详情` 卡片则整块不渲染。取种子 id 时优先用本次新跑的记录，否则 B18/B19 的断言会"看起来缺项"。
- **回放 K 线空白（已修）**：klinecharts 未监听 `viewChanging` 时，图表要等切换货币对才出现，表现为"打开回放一直空白"。B24 就是这条的回归哨；若 B24 空白但接口 200，先看控制台 klinecharts 报错再判定。
- **导出报告是整页自包含 HTML**：含全量成交与权益曲线，大区间/多品种回测的文件可达数十 MB，下载与浏览器渲染都会明显变慢，属已知体积特性而非卡死。
- **config 页「资金使用方式」分段器的值是 per_symbol/shared**：demo 原型画的是「固定/复利」，那是不同的概念——本页沿后端契约（各标的独立资金池 / 组合共享资金池），别按 demo 文案"对齐"。
- **config 页提交按钮在页头**：`PageContainer` 的 actions 在 `<form>` 外，按钮走 `onClick={() => form.submit()}` 触发，与 `htmlType="submit"` 同一条校验链路（校验不过会停在表单并标红）。找提交入口别只盯表单底部；运行中按钮会 disabled，重复点击不会产生第二个任务。
- **决策抽屉宽度 prop 曾写错（已修）**：`DecisionDetailDrawer` 误用 `size={680}`（Drawer 只接受 number `width`），该 prop 被忽略、抽屉回退默认 378px。已改 `width={680}`；B19 打开抽屉时宽度应为 680px。该抽屉被 Worker 决策页/策略研究页共用，改它的内联样式时注意别引入 backtest.css 的类（那些页面不加载该文件）。
- **详情/回放页头副标缺项自动省略**：副标由真实数据拼接（标的 · 周期 · 区间/品种 · 周期），任何一项缺失不渲染假「0」或占位；回放页数据未加载时整体不显示副标，属预期不是丢样式。
- **决策表每页固定 200 条（前端切片）**：决策详情表是本地分页（3 万条全渲染卡浏览器），页码切换不发请求；「共 N 条」的 N 是 decisions 全量数。别把它当服务端分页断言请求参数。
- **无效 id 的回放接口不报 404（后端契约缺口）**：`GET /backtest/<不存在的id>/symbols` 返回 200 + 空 symbols（`backtest.routes get_backtest_symbols` 只 WARN 不抛），前端收到「成功但空」就走静默骨架，永远到不了错误提示分支；B28 的「错误」提示条只能由传输层失败（超时/拒绝）触发。要改先动后端返回码，前端分支本身是好的。
- **详情页旧 cascade 记录会把整页打白（TradeTable 契约缺口，非本区代码）**：历史 LLM/cascade 回测的 round-trip trades 里没有 `quantity` 字段（只有 entry/exit fill 结构），共享组件 `TradeTable.formatQuantity` 对 undefined 调 `.toFixed` 抛错且无错误边界 → 决策详情卡也一起渲染不出来；回测详情的决策 chip / 分页条只能在"RL/规则或有健康 trades 的新记录"上验证。修法在 TradeTable 兜 null 或后端补字段，别在本区绕。
- **progress 拉取失败必须保留旧快照**（2026-11-23）：`getBacktestProgress` catch 后返回 `null`，前端按「不清空、不弹错」处理（B29 的 15s 轮询会反复打到这个分支）。把 null 当空数据处理会让进度条在服务重启瞬间归零/隐藏，比停在旧值更误导；只有该任务转终态或收起展开才允许清空
- **LLM replay 提示是静态说明不是错误**：`strategy_kind=llm` 任务失败时的弱色说明与 config 页参数卡底部那句是同一句常量文案（未命中回放不降级、直接终止），不要与 B3d 的红字「失败原因」混为一层样式；非 LLM 任务不渲染（B30）
- **作业池心跳看门狗曾失效（已修）**：旧代码把超时判定挂在「无快照」的 elif 分支后，worker 卡死时快照文件仍在 → 永不判超时。现判定独立于快照存在性。副作用：数据准备等长静默阶段必须持续产出进度，>75s 无快照更新会被判 interrupted（`回测进程超过 75 秒无进度更新`）；B30 若遇到该文案，先查长静默阶段是否缺进度埋点，别当看门狗误杀。
- **作业池随应用退出清理（已修）**：lifespan 现在显式 shutdown 回测/RL/HPO 三池，`wait=False` 会 terminate 在跑 worker。Ctrl+C 后在跑回测被强杀属预期（此前 spawn worker 会变孤儿继续跑，重启后与新池抢核）。
- **灰度开关三态（已修）**：`QUANTCELL_JOB_POOL_ENABLED=false` 现在能覆盖 config.toml `[jobs].enabled=true`；只有未设置（None）才回落 config。此前 bool 默认 False 导致环境变量关不掉 config 打开的池。
- **绑核区间按池切分（已修）**：配了 `[jobs].cores` 时回测池取前半核、HPO 池取后半核（单核区间两池共享各 1 并发），不再两池绑同一批核互抢；`/jobs/queue` 里各池 `cores` 与配置文件不完全一致属预期。未配绑核时保持 cpu-1 默认，由 OS 调度。
- 2026-11-27 回测自动下载闭环：检查口径曾查 DB（毫秒/纳秒错配恒报缺）、下载写 `~/.quantcell` 分片无人读、下载段 ±1h 缓冲跨天不完整；现统一为 source 单文件 Parquet（检查=下载=回测同源），下载段天对齐。
