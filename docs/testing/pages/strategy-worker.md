# 策略智能体（/strategy-worker、/strategy-worker/:workerId）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- `/strategy-worker`（列表）无数据依赖：**空列表是合法状态**，表内/卡片区显示「暂无Worker」
- `/strategy-worker/:workerId`（详情）需要列表里至少有 1 个 worker；一个都没有时 W2 记为「跳过（无 worker）」，不算失败
- 造数据（仅 L2 的行级操作需要）：策略库需先有策略（见 `strategy-editor.md`）→ 在 `/strategy-worker` 点「创建Worker」，名称用 `zz_test_probe_worker`，交易模式保持默认「**本地模拟**」，**不要点「启动」**（启动会接行情源，属外部依赖）。收尾：删除该 worker（确认框「确定删除此Worker？」→ 是）
- 列表页每 30 秒自动重拉一次，验证时以最后一次请求为准，不要用请求次数当断言

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| W1 | 直接打开 `/strategy-worker` | 页头为 §5 page-head 制式：标题「策略智能体」（16px/650）+ 副标 mono 11px 真值行「任务 N · 运行 N · 已暂停 N · 停止 N · 错误 N · 累计盈亏 $N」随列表实时口径变化（四项状态之和应等于任务数，paused 单独成档）；统计区为 §6.4 四张 `.qc-kpi`（label 11px 灰 + mono 22px/650 数字，「总盈亏」按方向染涨跌色、计数类恒中性），「总任务」卡副标同为含「已暂停」的五档口径；工具栏为 §6.6 单行（搜索框 + 状态筛选 + 右侧计数「显示 x-y / 共 z」+「刷新」与「创建Worker」30px 钮）；列表视图表头为 4 列：**名称**（行首三角 `.qc-cell-caret` + 名称 mono 截断 + 弱化 `#id` + 状态 chip + 名称格内 9px 类型徽章 rule=info「规则」/ rl=pri「RL」/ 取不到显示 `—`，同一格第二行弱化次级信息「策略名 · 交易所 · 周期」单行省略并带 title）、**累计盈亏**（mono 右对齐涨跌色，0 中性）、**运行时长**（mono 弱文本）、**操作**（「详情」文字钮 + 眼睛图标「就地展开」+「更多」下拉）；独立的「类型」「交易所」「周期」列已移除；空表显示 `.qc-empty` 空态；`GET /api/v1/workers` 返回 200；URL 保持 `/strategy-worker`（不被踢回 `/login`） | L1 |
| W2 | 在列表点某行操作列的「详情」文字钮（卡片视图是文字按钮「详情」） | URL 变为 `/strategy-worker/<id>`；页头为 PageContainer 详情制式：返回箭头 + worker 名称标题 + 副标 mono「#ID · 交易对 · 交易所」+ 右侧状态 chip 与「分享」「归档重锚」两个 30px 钮；标题下有一条 `.qc-strip` 事实条（周期/交易模式/累计盈亏/初始资金/杠杆/下单方式 + 最右「最后更新于 …」）；页签「总览」「交易」「决策」「风控」「参数」「日志」六个齐全（§6.8 下划线式，无边框无底色）；`GET /api/v1/workers/<id>` 返回 200。注：操作列的眼睛图标是「就地展开」，不跳转 | L1 |
| W3 | 点「创建Worker」 | 弹窗标题「创建Worker」，分区「基本信息」「交易配置」可见；**「策略」在左、「Worker名称」在右（位置互换）**；名称非必填——选策略后自动填充 `<策略名>_<4位短码>`（去掉易混淆字符），再次切换策略会重新生成不冲突名称；用户手动键入过名称后不再被覆盖；交易模式默认「本地模拟」；改名称为 `zz_test_probe_worker` + 选交易标的 → 点「创建」→ 提示「Worker创建成功」，`POST /api/v1/workers` 200，列表出现该行。另验一条：只选策略不改名称直接提交，应成功（名称兜底自动生成）。收尾删除（见前置） | L2 |
| W3a | 在「创建Worker」弹窗点开「交易标的」下拉（编辑弹窗同项） | 上部自选组组项在前（组色圆点 + 组名 + 弱色『(自选组)』小字，圆点颜色与数据管理页该组自定义色一致，不再用固定警示色星标图标）、下部裸标的后；搜索输入组名或 symbol 均能过滤；选组提交创建后，worker 详情页「交易对」事实条/参数页签显示组内全部货币对（`pool_` 前缀在提交时展开） | L2 |
| W4 | 在搜索框输入一个必然不存在的关键词 | 列表区变为空态「暂无Worker」；上方四张统计卡数字**不变**（统计取自全量，不受搜索影响）；不发起新请求 | L2 |
| W5 | 状态筛选选「已停止」 | 列表只剩状态标签为「已停止」的行或空态；不发起新请求 | L2 |
| W6 | 勾选任意一行 | 出现批量栏「已选择 N 个 Worker」及「批量启动」「批量停止」「批量重启」「取消选择」；点「取消选择」后批量栏消失且**未发起** `lifecycle/*` 请求 | L2 |
| W7 | 点某行的删除图标 | 弹「确定删除此Worker？」；点「否」关闭且该行仍在（不发起 `DELETE /api/v1/workers/<id>`） | L2 |
| W8 | 在列表页静止停留 35 秒 | 观察到 `GET /api/v1/workers` 出现第二轮请求；期间页面出现加载遮罩属正常（全局 loading），无报错弹窗 | L2 |
| W9 | 在运行中的 worker 卡片点「日志」 | 弹窗标题「Worker 日志」，内含「实时日志」标题、级别筛选、「暂停」「清除日志」；日志流断开时显示「⚠ 日志流已断开」而页面不崩（SSE 经反代可能被缓冲，属环境类，如实记录） | L2（外部依赖，不断言日志有内容） |
| W10 | 详情页「总览」页签 | 顶部 8 张 §6.4 `.qc-kpi` 卡（`--qc-border` 边 + `--qc-surface` 底，数字 mono 22/650）：「总盈亏」「收益率」「胜率」「盈亏比」「Profit Factor」按方向染涨跌色，「Sharpe」<1 为警示色，「最大回撤」「交易次数」恒中性；四张持仓摘要 KPI（总持仓价值/总未实现盈亏/总保证金/总 ROE）同制式；**键盘可操作**：KPI 卡有 `role="button"`，Tab 聚焦后按 Enter/空格触发与点击一致；时间档 24h/7d/30d/90d/全部 可切换；「累计收益曲线」「每日盈亏」「当前持仓实时」三张 `.qc-card` 可见（持仓激活时标题带 info chip + pulse 圆点；持仓表 symbol/杠杆 mono、方向多空涨跌色）；无数据时图表区显示「暂无数据」；加载骨架与实况同构不跳变；`GET /api/v1/workers/<id>/stats/overview?window=...` 200 | L2 |
| W11 | 详情页切到「交易」页签 | 卡片标题「交易详情」，激活时带「实时」chip（info 档 + pulse 圆点）；表头含「订单号」「交易对」「方向」「类型」「数量」「状态」；订单号/交易对/时间为 mono 弱文本，状态列为语义 chip（FILLED=ok、OPEN=info+圆点、CANCELED=quiet、REJECTED=down）；分页档位 12/24/36…（12 的倍数）；无数据时显示 `.qc-empty` 空态；`GET /api/v1/workers/<id>/monitoring/trades` 200（激活期每 3 秒轮询，属预期） | L2 |
| W12 | 详情页切到「决策」页签 | 卡片标题「决策记录」，副标「最近 N 条（含历史运行）」；`GET /api/v1/workers/<id>/decisions` 200；该 worker 从未跑过 cascade 时显示「该 Worker 未运行过 cascade 决策策略，或尚未产生决策（P2 之前的旧录制文件不展示）」；有录制行时**点整行**即打开决策详情抽屉（同操作列「详情」按钮，`_seq` 为空的行不响应、鼠标不变手型），抽屉四页签「最终决策 / 状态 / 提问 / 模型输出」内容与回测决策抽屉同源 | L2 |
| W13 | 详情页切到「风控」页签 | 「风控状态」「风控参数」两张 `.qc-card` 可见；「风控状态」右上角来源为语义 chip（人工管控=info 蓝、继承策略参数=quiet 灰），无彩色 Tag；「风控参数」卡头为盾形图标（非 emoji），启用时带 ok chip「风控管控已启用」；未配风控时分别显示「风控未装配：策略参数未配置 risk，且无人工管控」与「继承策略参数配置」；`GET /api/v1/workers/<id>/risk-status` 与 `GET /api/v1/workers/<id>/risk-control` 均 200（激活期 30 秒轮询属预期） | L2 |
| W14 | 详情页切到「参数」页签 | 「策略参数」卡可见；无可配置参数时显示「该策略没有可配置参数」；`GET /api/v1/workers/<id>/strategy/parameters` 200（worker 带策略元信息时另显示「策略信息」卡） | L2 |
| W15 | 详情页切到「日志」页签 | 「实时日志」区与「最近对账」卡同屏；无对账数据时显示「暂无对账记录（resume 或运行期对账后展示）」；`GET /api/v1/workers/<id>/logs/recent` 与 `GET /api/v1/workers/<id>/reconciliation/summary` 均 200 | L2（外部依赖：SSE 日志流按需） |
| W16 | 点「分享」 | 弹窗标题为「分享策略：<worker 名>」；**不要点「生成链接」**（会真实落库生成分享 token） | L2（只读断言） |
| W17 | 悬浮/查看「归档重锚」按钮 | 非 stopped/error 状态下按钮不可点；交易模式为「本地模拟」(paper) 时悬浮提示「paper 模拟盘不产生 journal 文件，启动即全新开始，无需归档」 | L2（只读断言） |
| W18 | 打开 `/strategy-worker/<id>#performance` | 提示「该视图已合并到 总览」，随后 hash 变为 `#overview` 且「总览」页签激活（旧分享链接兼容） | L2 |
| W19 | 把某页签（如「交易」）的 hash 复制后刷新页面 | 刷新后仍停在同一个页签（切换页签会同步 URL hash，刷新按 hash 恢复） | L2 |
| W20 | 详情页点「停止」（worker 为 running/paused） | 详情页头出现「停止」按钮；点击弹二次确认，确认后发起 `lifecycle/stop` 并刷新状态 chip；`stopped`/`stopping` 时该钮不出现；访客身份下按钮禁用并带 Tooltip | L2（写操作） |
| W21 | 观察详情页头部事实条持仓三件 | 「周期/交易模式」之后出现「当前持仓 / 开仓价格 / 未实现盈亏」；无持仓时整项省略（不留占位）；未实现盈亏正绿负红、`0` 不染色；多持仓时只显示未实现盈亏合计（数量与均价省略，不造均值） | L2 |
| W22a | 观察列表「运行时长」列 | running 行显示自 `started_at` 起的时长（`14h 22m` 形制，不刷新页面也会随下次 30s 重拉更新）；`stopped` 且有 `stopped_at` 的行显示历史定值（不随停留时间增长）；`paused`/`error` 且无 `stopped_at` 的行显示 `—`（不拿当前时间冒充暂停时长）；无 `started_at` 的行显示 `—` | L1 |
| W22 | 列表页状态筛选选「已暂停」 | 下拉新增「已暂停」项；选中后只显示 `status=paused` 的 worker（无匹配时为空态「暂无Worker」） | L1 |
| W23 | 观察列表页头左侧 | **无返回箭头**（2026-11-25 删除，与其他一级页同构：标题行 + 副标行，左侧无前缀钮，页头高度与 `/home` 等一致）；返回出口 = 侧边栏导航 / 首页快捷卡 | L1 |
| W24 | 点列表任一行（名称 / 累计盈亏 / 运行时长单元格） | 该行下方就地展开 `.qc-exp-panel`：首行为名称 + `#id` + 状态 chip，右侧为「累计盈亏」真值（0 不染色）；网格含「类型 · 交易模式」「策略名称」（`strategy_info.name` 有才显示）、「交易所」「周期」「运行时长」「启动时间」（有 `started_at` 才显示）、「停止时间」（有 `stopped_at` 才显示）；「资金配置」摘要只在 `worker.config` 真实存在 `initial_capital` / `leverage` / `max_position_size` 或 `trading_config.market_type` 时出现（缺的不渲染，不造手续费字段）；同一时刻只展开一行；**初次加载不自动展开**；筛选/搜索/翻页变化后自动收起 | L1 |
| W25 | 勾选行政复选框，再点表头全选复选框 | 行只被选中、批量栏出现，**不展开面板**（勾选列自带 stopPropagation）；全选也不展开任何行 | L1 |
| W26 | 点操作列眼睛图标（悬浮提示「就地展开」，展开后为「收起」） | 该行展开/收起，按钮 `aria-expanded` 同步；眼睛按钮不触发跳转（跳转只走「详情」文字钮与面板内「进入完整详情」） | L2 |
| W27 | 键盘：Tab 聚焦某行后按 Enter / 空格；展开后按 Esc（行或面板内聚焦任意位置均可） | Enter / 空格切换该行展开；Esc 收起面板且 `aria-expanded=false`；焦点在行内按钮/下拉时按 Enter 只触发按钮，不会连带切换展开 | L2（键盘） |
| W28 | 展开一条 `status=error` 的 worker 行（造数据：让 worker 进入错误态，或直接看现网异常行） | 面板出现红色「失败原因」块，正文是 `GET /api/v1/workers/<id>` 返回的 `_state_info.error_message` 原文——列表接口不含该字段，展开瞬间才发起这次单查；详情接口也没给 `error_message` 时该块整块不渲染（不拿状态码顶替）。停止行有 `stopped_at` 时另显示「停止时间」；`paused` 行没有原因字段，只显示状态 chip、不显示原因块 | L2 |
| W29 | 在展开面板点「进入完整详情」；再点面板内「启动 / 停止 / 重启」 | 「进入完整详情」跳 `/strategy-worker/<id>`；启停/重启复用列表下拉同一 handler（停止仍弹二次确认；提交期间按钮 loading/disabled）；点击面板内按钮不改变展开态 | L2 |
| W30 | 系统设置把「默认展示类型」切为「卡片视图」后打开本页，点任意一张 worker 卡片（卡片有 `role="button"` + `tabIndex=0`，Enter/空格亦可展开） | 卡片**所在视觉行的最后一张卡之后**插入与列表完全相同的 `.qc-exp-panel`（跨全宽、同行卡数不变），面板内文字 normalize 后与列表点首行得到的面板逐字相等，且展示的是**被点那张卡**的数据（不是同行末卡）；再点同卡收起，Esc / 搜索 / 状态筛选 / 翻页均收起，首载无面板；卡片右上角勾选、编辑、删除与卡内启停/详情/优化/重启/日志不触发展开（「详情」仍跳详情页）；异常卡（`status=error`）展开同样能看到「失败原因」`error_message` 块 | L2 |
| W31 | 详情页「交易」tab（对齐币安/OKX/Bybit 四页签）：仓位(n)｜当前委托(n)｜历史委托｜历史成交 | **仓位为默认页签**：列对齐币安——合约（+`永续`tag+杠杆tag）、数量（多正空负+方向色）、开仓价格、损益两平价、标记价格、强平价格（danger 色）、保证金比率（<50% 绿 / 50-75% 黄 / >75% 红）、保证金、盈亏（回报率双行，ROI 分母优先 margin_used、无则按杠杆折算名义本金）；live/testnet 富化值来自 `LiveTradeSync.sync_positions`（交易所对账），paper 的两平/强平/比率显示「—」、杠杆取引擎配置；无持仓空态「当前无持仓」。**当前委托/历史委托**：同一订单表接口，当前委托只取 `status=OPEN`、历史委托服务端 `exclude_open=true` 排除 OPEN（精确 total），有注脚说明撤单/拒单事件链路未接线。**四页签统一分页+筛选**：订单/成交页签走服务端分页（page_size 档位条+页码），仓位走 DataTable 本地切片（交易所对账行数天然个位数）；筛选面板全页签可展开——仓位=标的+持仓方向（long/short），订单/成交=标的+交易方向（buy/sell）+类型+时间（side 语义两域不同，切页签自动清空筛选防脏值）；提交筛选回第一页，切每页档位回第一页；四页签徽标为服务端精确计数（挂载时 `page_size=1` 预取，不随翻页重发）；CSV 按当前筛选导出（上限 100 行）。**历史成交**：服务端分页 + 筛选（标的/方向/类型/时间）+ CSV；每页签独立导出 CSV；重新进入页面默认激活仓位 | L2 |

## 历史雷区
- **`apiRequest.get(url, params)` 第二参就是查询参数本体，不能再包 `{ params }`（2026-11-26 修）**：`apiRequest.get` 内部实现是 `api.get(url, { params, ...config })`，包装层再写 `apiRequest.get(url, { params })` 会把真参数嵌进 `params[...]` 键——FastAPI 只认 `?status=OPEN`，嵌套键全部静默丢失、接口白跑（表现为「当前委托 (40)」假计数：status 没上车，返回的是全量表）。曾同病 5 处（`strategy/positions`、`strategy/orders`、`logs/recent`、`stats/trade-history-chart` 的 days、`stats/trading-summary`），全部直传修复。**新增 API 包装函数时 grep 一遍 `apiRequest.get([^)]*{ params` 确认没有重包**
- **「交易」tab 是币安式四页签，旧的单张合并表已退役（2026-11-26）**：页签= 仓位/当前委托/历史委托/历史成交，各自独立加载（勾总是 fetchActive(subTab) 只刷当前页签）。「仓位」数据源 = `worker_positions`（live/testnet 由 `LiveTradeSync.sync_positions` 交易所对账落库，见 P1-11 条目；paper 引擎快照）。**HMR 改造期间页签激活态/计数会错乱（React Fast Refresh 状态槽重排），验证默认页签必须整页 reload 后再看**——曾据此误判"默认激活非仓位"和"当前委托 40 条"，干净加载后均为正确值
- **live/testnet「当前持仓」是交易所对账值，不是本地推导（2026-11-26 修）**：详情页持仓曾从 `worker_trades` 未配对 fill 净额推导，live 跨重启聚合出幻影持仓（交易所实际已平仓，页面仍显示 -1.698 ETH 残仓）。现 `LiveTradeSync.sync_positions` 每 10s 以 `fetch_positions` 对账落 `worker_positions`（交易所为唯一事实源，OPEN 行 upsert、平仓行收口 CLOSED、重启重演后复活）；`GET /workers/{id}/strategy/positions` 对 non-paper worker **不再退回推导**（表空宁可显示「暂无持仓数据」，与交易所一致）。driver connect 失败（如 demo userDataStream 30s 未建立）时同步线程根本没起来，持仓显示空也是对的——先看 worker 日志再怀疑链路
- **`ExpandableCardGrid` 的 `renderExpanded` 参数是「该行末卡」而非「被点卡」**：组件按 `data-qc-card` 定位到被点卡的视觉行，把面板插在该行最后一张卡之后，回调却传的是那个末卡 item。直接写 `renderExpanded={(w) => renderExpanded(w)}` 会在同排非末卡展开时显示别人的详情（列表/卡片文字比对会抓出来）。本页按 `expandedId` 反查真正的 worker 再渲染（见 `renderCardView`）；其他页面复用该组件时同样要自查
- **失败原因已随列表返回（2026-11-26 修）**：此前 `GET /workers` 不带 `error_message`，异常行要展开时单查详情接口补——重启失败后首屏看不到原因、进详情再返回才有。现列表项直接带 `_error_message`（来自 state_manager 快照），展开即显；前端旧的"展开时单查 GET /workers/{id}"逻辑已删
- **重启是异步的，别用请求块断言状态（2026-11-26 修）**：`POST /{id}/lifecycle/restart` 曾在请求协程里 `_wait_for_terminal_state(15s)` 等 stop 收敛，前端转圈 15s+。现在接口只入队 stop 即返（实测按钮 550ms 恢复），stop 收敛+start 由后台线程接力，失败会 transition(error)。验证状态终态要轮询列表（stopping→starting→running/error），demo 环境下 martingale 可能因"user data stream 30s 未建立"进 error——那是环境/策略问题，不是重启链路 bug
- **一级列表页不要加返回箭头**（2026-11-25）：`/strategy-worker` 列表页头曾带 `onBack → /home`（形制抄 demo 956），用户裁定删除——demo 的「← 返回首页」是原型演示形制，一级页（/home /chart /strategy-management …）都不带返回箭头，列表页带一个反而页头几何不一致。**只给详情页用 PageContainer 的 `onBack`**（如 `/strategy-worker/:id` W2），列表页新增时别顺手传 `onBack`
- **行内展开单键且会被筛选清掉**：搜索/状态筛选/翻页都会自动收起面板（面板与其行否则会失联）；30 秒自动重拉**不会**收起面板，但 `error_message` 只在展开瞬间单查一次，刷新后的新原因要重新展开才看得到
- **「创建/编辑 Worker」弹窗不归本页样式门禁**：两个 Modal 的表单交互属创建链路（W3），chrome 已挂 `qc-modal + qc-form`；若表单字段校验文案报错，先查 store 与 API 再怀疑样式收口
- **不存在的 workerId 会永久转圈**：详情页在找不到 worker 时整页渲染加载态（`if (!currentWorker) return <Spin>`），既没有 404 也没有「返回列表」入口。用错/已删除的 id 打开只会一直转，先用 `/strategy-worker` 确认 id 再断言，别把它记成"页面卡住"的新 bug
- **30 秒自动刷新会盖遮罩**：列表页定时器每次重拉都会置全局 loading，遮罩期间点击不生效。自动化脚本在 W8 期间穿插操作会得到假阴性，先等遮罩消失
- **「最后更新时间」不是数据时间**：详情页头部该文案由本地 60 秒计时器驱动，接口没返回 `updated_at` 时会显示"几秒前"这类假新鲜度，不要拿它判断数据是否在刷新
- **多路轮询叠加**：交易页签 3 秒、风控页签 30 秒、列表页 30 秒，切换页签会重新拉一次（按 active 触发）。连续快速切页签时表格可能短暂显示上一版数据（请求竞态），以最后一次响应为准再断言
- **SSE 日志流经反代**：日志页签与日志弹窗走 `/api/v1/workers/<id>/monitoring/logs/stream`，打包预览的 `/api` 反代若缓冲 SSE，会显示「⚠ 日志流已断开」或日志不滚动——先查反代/网络，属环境类
- **旧 hash 会改写 URL**：打开 `#performance` 等旧 hash 会 toast 提示并 `replaceState` 成 `#overview`，脚本若监听 URL 变化会误判成"多跳了一次导航"
- **分享弹窗会写数据**：`POST /api/v1/workers/<id>/share` 真实生成 token 并落库，L1/L2 默认只验证弹窗打开，不点「生成链接」
- **删除 worker 不可撤销**：无回收站，只有确认框；验证删除只允许对 `zz_test_probe_worker` 执行，并当场 teardown
- **详情页不提供「暂停/继续」**：后端 `backend/worker/routes.py` 的 lifecycle 只有 start/stop/restart，`agentApi.pauseAgent`/`resumeAgent` 是死代码；加按钮会 404。要补必须先加真实 pause/resume 路由与泵线程语义，别只接前端
- **`/ws/worker` 现要求认证**（2026-11-25）：握手 token 走 query 参数（WS 无法带 Authorization 头），失败时 accept 后以 4401 关闭；dev/desktop 本地豁免认证是预期。另：该文件曾有 Python2 语法 `except TypeError, ValueError,` 导致整个后端 import 失败——见到 `SyntaxError: multiple exception types` 优先确认此处无回归
