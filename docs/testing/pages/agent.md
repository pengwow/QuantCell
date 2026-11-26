# 智能体工作台（/agent）

## 前置
- 环境与 token 注入见 `../README.md` 第一节；本页在 `AuthGuard` 内，且被 `CapabilityGuard capability="agent_gateway"` 包裹
- 组件：`frontend/src/pages/agent/Agent.tsx`（左聊天 `components/ChatPanel.tsx`，右栏两卡 `components/FirstScreenCards.tsx`）
- **路由形态**：`DynamicRouter.tsx` 里 agent 只有一条路由 `/agent`，**没有子路由**。右栏已按 demo 收敛为「迭代足迹 + 记忆自迭代」两卡（原 8 页签工作台整体删除），URL 只剩 `?worker=<id>` 持久化选中的 Worker；旧的 `?tab=` 参数不再消费，带进来也不报错、直接忽略
- 能力开关：`GET /api/v1/capabilities` 中 `agent_gateway` 必须为 true，否则整页渲染 403 文案`功能未开启`（这是部署配置，不是页面缺陷）
- 种子：无需求；没有 Worker 时右栏全部落到空态/占位，页面骨架仍应完好。真实让 AI 跑任务会烧 LLM 配额，标"按需"

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| AG1 | 注入 token 后打开 `/agent` | 工作台骨架渲染：左栏空态标题`智能体工作台`、输入框占位`输入消息，按 Enter 发送，Shift+Enter 换行...`；右栏只有`迭代足迹`与`记忆自迭代（Dream）`两卡、无页签条；顶栏出现 `Worker` 选择器（有选中 Worker 时另带状态标签） | L1 |
| AG2 | 页面加载完成后查 network | `GET /api/v1/capabilities` 返回 200；`GET /api/v1/agent/sessions` 200；`GET /api/v1/agent/tools` 200；`GET /api/v1/workers?page_size=100` 200；控制台无未捕获错误 | L1 |
| AG3 | 观察 URL | 稳定后 URL 变为 `/agent?worker=<id>`（选中 Worker 时附带），无刷新；`?tab=...` 不再写入也不再消费（右栏无页签），直开 `/agent?tab=logs` 与 `/agent` 表现一致 | L1 |
| AG11 | 打开会话历史抽屉，点`新会话` | 发出 `POST /api/v1/agent/sessions` 并提示`新会话已创建`；会话名形如`会话 <时间>`，URL 与当前会话同步 | L2（写操作，结束后可删除该会话） |
| AG12 | 在输入框发送一句话 | 发出 `POST /api/v1/agent/chat/stream`（SSE，HTTP 200 流），气泡逐步渲染`AI 正在思考...`/思考过程；轮内有工具调用时 AI 气泡头部出现`迭代 N/40`徽标（SSE `iteration_start` 逐轮推进，上限 40 熔断）。失败以错误气泡呈现可读文案。**真实调用消耗 LLM 配额，默认跳过** | 按需（真实 LLM 配额） |
| AG14 | 把 `agent_gateway` 能力关闭后直达 `/agent` | 渲染 403 页：标题`功能未开启`，副标题含 `agent_gateway`；侧边菜单也不出现该入口 | L2（环境配置分支） |
| AG16 | 观察`记忆自迭代（Dream）`卡 | 总闸 chip 与 `QUANTCELL_AGENT_DREAM` 实际值一致；MEMORY.md 只读渲染；`已整合 x/y` 进度（x=模型下游 `.dream_cursor`，y=history.jsonl 行数）；`上次运行`三态如实（无记录`重启后尚未运行`/no-op 灰/失败红可展开 detail）；`下次运行：每日 04:00`；底部注明`Dream 只整理记忆，不会替你执行交易` | L2 |
| AG19 | 视觉收口：徽章形制（亮/暗各跑一遍） | 整页（含右栏两卡、抽屉、弹窗）DOM 中 `.ant-tag` 数量为 0；Worker 状态、Dream 总闸、迭代均值等徽章均为 `.qc-chip` 形制（tint 底 + 语义档位），进行中徽章带 `.qc-pdot` 脉冲点 | L1 |
| AG20 | 视觉收口：聊天流形制 | `getComputedStyle` 断言：AI 头像 32×32、`border-radius: 8px`、底色 = info token；消息气泡 `border-radius: 12px`、内边距 11px/15px、有 bubble-shadow；用户消息行右对齐、气泡底色 = `--qc-user-bubble-bg`；工具调用为链式节点形制（mono 工具名 + 参数摘要 + 状态 chip），而非孤立项徽章 | L1 |
| AG21 | 视觉收口：主题换挡 | 切换亮/暗主题后无需刷新：页面底、气泡底、边框、徽章 tint 全部跟随 token 变化（`computedStyle` 的 `background-color`/`border-color` 应随主题出现两套不同 rgb）；页面任何位置不出现写死的灰阶色块 | L1 |
| AG22 | 右栏只有 demo 两卡 | 右栏自上而下只有「迭代足迹」卡与「记忆自迭代（Dream）」卡，**没有页签条**（决策流/持仓订单/绩效/模型/日志/审计/事件与拥挤/自迭代全部移除）；打开页面时网络面板不出现 `/decisions`、`/positions`、`/performance`、`/logs`（含 SSE）、`/audit`、`/models`、训练任务等请求，只有 `GET /api/v1/workers`（选择器）、`GET /api/v1/agent/memory`、`GET /api/v1/agent/loop-status` | L1 |
| AG23 | 迭代足迹卡柱数 = 真实迭代数 | 无数据（新会话/仅历史恢复）时卡体为弱色空态提示，**不画占位柱**；发一条消息跑完 ReAct（按需，耗 LLM 配额）后出现对应柱：柱数 = 当前会话带轮次的 AI 回复数（SSE `iteration_start`/`complete` 聚合，与气泡「迭代 X/Y」徽标同源），不足 12 不补齐、不循环；均值 chip 只按画出的柱计算；熔断虚线取 SSE 真实上限（40）并置于轨顶，上限不可证时不画线 | L2（空态 L1；柱数须真实 LLM 回合，按需） |
| AG24 | Dream 卡字段全部来自 self-loop 接口 | `GET /api/v1/agent/memory` 返回值渲染：chip 与 `QUANTCELL_AGENT_DREAM` 实际值一致（`QUANTCELL_AGENT_DREAM = 1/0` mono 形制）、MEMORY.md 只读体、`已整合 x/y` 进度条（x=dream_cursor，y=history_entries）、`待处理`（>0 才显示）、`上次运行` 三态如实；读取失败显示弱色提示 + 右上刷新钮，不显示假数据 | L2 |
| AG26 | Dream 卡「下次运行」行（`next_run_at` 非空才有） | 同时读 `GET /api/v1/agent/loop-status` 里 `agent_dream` 的 `next_run_at`（后端直接取真实挂载的 APScheduler `job.next_run_time`，非解析 cron）：非空时 `上次运行` 下方出现一行「下次运行 `MM-DD HH:mm` · N 小时后」（相对量按分钟/小时/天取最小可读档位）；mount 时刻已过则显示「即将运行」而不是负值；`next_run_at` 为 `null`（job 未挂载，即 `QUANTCELL_AGENT_DREAM` 总闸未开）时**整行不渲染**，不得显示 04:00 之类推算值。`curl /api/v1/agent/loop-status` 可核实：总闸关闭时 `next_run_at: null` | L2 |
| AG25 | 页头真值 + 两个跳转钮 | 页头轻量行（非 PageContainer）：标题`智能体工作台` + mono 副标`会话 #<id> · ReAct 单轮上限 40 次迭代 · SSE 实时`（会话 id 为真实 session key，「40」为项目常量 backend/agent/core/loop.py `max_iterations` 默认值）；右侧两枚 30px 钮：`策略智能体 →` 跳 `/strategy-worker`、`← 返回首页` 跳 `/home`；既有顶栏（会话/Worker 控件）不受影响 | L1 |
| AG27 | 观察工具节点耗时 chip | 真实跑一次带工具调用的 ReAct 后（按需，耗 LLM 配额），每个工具节点右侧出现「耗时 x.xxs」chip，数值来自 SSE `tool_result.data.elapsed`（秒）；同轮多个工具各自独立、不共享同一数值；历史消息（无 `elapsed`）不显示该 chip，也不显示 `0s` | L2（按需） |
| AG28 | 每日复盘消息结构化渲染 | 每日复盘消息（03:35 job 写入 default 会话）在聊天流里带出处 chip「定时任务 · 每日复盘」，并按 `meta.report.sections` 渲染 概览 / 活跃 Worker / 持仓异常 / 风控建议 / 模型与 OOS 小节；空节整节省略；刷新页面后从 history 恢复时同样识别（`meta` 原样回传） | L2 |
| AG30 | 观察会话区外框与卡头 | 左侧聊天区是 demo 同款「会话卡」：1px 边 + 10px 圆角，卡头左侧「会话 · <会话名>」13px/650 + 绿点「实时」chip，右侧依次为 Worker 选择器、会话历史图标钮、工具参数图标钮、「清空会话」文字 mini 钮（无折叠钮——右栏恒显示）；消息区只在卡内滚动（滚到底时页头/卡头不动、`window.scrollY` 保持 0），输入区固定在卡片底部不被裁出视口 | L1 |
| AG31 | 长会话滚到底后看整体 | `.ai-agent-layout` 高度吃满 `qc-main`：卡片底边贴在视口内（1440×900 下无纵向溢出、无窗口滚动条），换 1280×720 也不出现输入区被切；明暗两主题下卡片底/边、卡头分隔线、实时 chip 都随 token 切换 | L1 |
| AG32 | 看页头右上动作钮 | 与 demo `page-head` 一致的两个 30px 文字钮：`策略智能体 →`（→ `/strategy-worker`）与 `← 返回首页`（→ `/home`），箭头是文案的一部分、**不叠加图标钮**（不得出现双箭头）；两钮同高 30px、同底边对齐，间距 8px | L1 |
| AG33 | 缩小窗口到 ~700/880px 与 1280×720 | 页面在 ≤1080px 退化为单列（demo `.agent-grid` 同口径）：会话卡整宽 560px 定高、右栏两卡堆到下方、整块工作台纵向滚动；任意宽度下会话卡卡头都是单行 44px（不换行）且 `scrollWidth == clientWidth`，Worker 选择器不压住「会话 · xxx」与「实时」chip，标题单行省略 | L1 |
| AG35 | 页面底色与双栏对齐（亮/暗各跑一遍） | `.ai-agent-layout` 计算样式 `background-color` = `--qc-canvas`（亮 `#f2f3f5` / 暗 `#0b0c0e`），与首页等其他页面同底色，右栏空白处不是白面；1440×900 下页头左右内距 2px、双栏顶边同为页头下 12px，右栏宽 372px（demo `.agent-grid`），右栏两卡底边与左会话卡底边重合；两卡都有 `--qc-shadow-card` 阴影 | L1 |
| AG34 | 展开 Worker 下拉，依次选名字最短/最长的 Worker | 卡头高度恒为 44px（换 Worker 不换行）；选中值单行省略（`title` 带全名），下拉选项单行省略、行高 32px；弹层宽度 220–320px 且整块落在会话卡内（不越过卡右缘盖到右栏） | L1 |
| AG36 | 意图面板点「转回测验证」类跳转（回复含策略名的场景） | 跳 `/backtest/config` 后策略下拉已预填该策略（`location.state.strategy.name` → 接收端按 name 取完整策略对象，成功 toast 含该策略名）；回复不含策略名或非回测类跳转不带 state，行为同旧，无 console error | L2 |

> 原 8 页签工作台的验收项（旧 AG4–AG10、AG13：决策流/持仓订单/绩效/模型/日志/审计/事件/训练）随页签一起删除，防回归断言见 AG22。

## 历史雷区
- **工作区曾落临时目录（已根治）**：agent 会话/工作区文件此前写进 PyInstaller 临时解压目录，升级/重启即丢。现已统一落 `QUANTCELL_DATA_DIR/data/agent_workspace`
- **无子路由**：不要构造 `/agent/xxx` 之类的地址找子页——React Router 里只有 `/agent`。右栏页签已于 2026-11 整体删除，`?tab=` 不再有任何效果，别按旧地址找入口
- **URL 与 store 双向同步有回写竞态**（已修）：挂载首拍同时执行 URL→store 与 store→URL，曾把 URL 里的 tab/worker 打回默认值。断言 AG3 要等同步稳定（条件轮询 URL），不要在 `domcontentloaded` 瞬间取值
- **会话报错一直显示旧模型**（已修 2026-11-26）：`get_agent()` 单例此前只在进程首次调用时读 `system_config` 的 `ai_model.*`，设置页保存新模型后单例仍持旧 provider/model 快照发请求，错误信息永远是旧模型名。已改为每次调用重读配置做签名（provider|host|key|model）比对，变化即热替换 `llm_backend/model`、实例复用（会话历史与工具不丢）；回归用例 `backend/tests/agent/test_factory_hotswap.py`。改模型设置后的验证口径：不重启后端，直接在 `/agent` 发一条新消息即可生效
- **意图面板「暂无结构化数据 + agent_data_actions + 三按钮」不是故障**（2026-11-26 定性，顺手修一个真 bug）：消息命中 `data_query` 类意图（「价格/数据/行情/查询/k线」任一关键词，权重 1 即够）后，后端 `extract_structured_data` **没有 data_query 分支**恒返回 `{}`，面板数据表为空必显示「暂无结构化数据」；三按钮来自 `build_actions` 静态映射（label 硬编码中文），与回复内容无关，仅「查看K线」真跳 `/chart`，其余降级 info 提示。**已修**：面板标题 `agent_data_actions` 是 i18n 缺键回显 key（zh/en 语言包均无），已补「相关操作 / Suggested actions」。详见 `docs/agent_workbench.md` §5
- **图标按钮无文本**：顶栏`会话历史`/`工具参数设置`/`清空会话`/`展开或收起面板`都是纯图标 + tooltip，文本扫描找不到，按 `aria-label`/tooltip 或 DOM 直查定位
- **日志 SSE 重连有上限**：`WorkerLogStreamSSE` 内部最多重连 5 次，超限断开后需重新挂载页面才会再连；"日志一直未连接"先看是否已超限，而非后端无日志
- **无 Worker 时右栏是空态不是故障**：所有 Tab 都靠 `workerId` 取数，`workerId` 为空即不发请求、不建日志流。L1 只验骨架，别把空态当数据缺失
- **能力关闭即 403**：`agent_gateway` 关闭时菜单隐藏且直达 URL 被 `CapabilityGuard` 拦成`功能未开启`。见到该文案先查 `GET /api/v1/capabilities`，别按前端 bug 追
- **删除会话需手输确认词**：删除弹窗要求输入`确认删除`才能点确认，自动化误点会被卡在弹窗；L2 收尾清理会话时优先走 API 或直接跳过
- **SSE 错误不是 HTTP 错误码**：聊天失败在 200 流内以 error 事件返回（气泡标记错误），按状态码断言会误判成功
- **迭代事件一轮双发**：一条回复的 SSE 流里 `iteration_start`/`complete` 各出现两次（routes 与 loop 各发一波），前端以最后到达为准渲染徽标；自动化断言徽标数值时勿假定事件只发一次
- **Workbench Tab 内容超视口被裁剪（已修，`8adde8a8`）**：`.agent-work-col` 是 `overflow:hidden` 列而 `.wb-tabs` 高度传导断裂，content-holder 的 `overflow-y:auto` 从未生效，所有 Tab 一起只露首屏。断言方式：content-holder `clientHeight < scrollHeight` 且 `scrollTop` 可推进
- **i18n 占位符泄漏（已修，`c4766c7e`）**：`selfloop_cursor` 曾把 `{{processed}}/{{total}}` 原样上屏（key 是插值版、调用处按纯 label 渲染）。断言：自迭代 Tab 文本不得包含 `{{`；改 key 文案形态时插值参数与调用必须同时改
- **首屏「迭代足迹」柱清零是空态不是故障**：柱数据只来自**当前会话**的 SSE 聚合（`agentStore.messages` 的 `iteration` 字段），会话历史接口不带 iteration（`fetchHistory` 不映射），刷新/切会话后柱清零回空态属预期。demo 的「近 12 轮会话」跨会话口径现网无源（`/agent/audit` 按天聚合的是**工具调用**，不是 ReAct 迭代，勿混用口径填柱）
- **首屏 Dream 卡「下次运行」必须来自调度器真值**：`/agent/loop-status` 的 `next_run_at` 取自本进程真实挂载的 APScheduler job（`core/scheduler.py::get_scheduler()` → `job.next_run_time`），未挂载/调度器未启动即 `null`；前端此时整行不渲染。**不要**按 `cron` 文案（`每日 04:00`）自己推算时间戳——croniter 未安装，且推算出来的时间在总闸关闭时是假的下次运行
- **Dream 心跳依赖后端进程活过 04:00**：两次平台级重启（11-18/11-19）都撞掉 04:00 调度载体。C/B 卡显示`重启后尚未运行`属预期，不是缺陷；总闸 `QUANTCELL_AGENT_DREAM` 未开时 Dream 行显示`已关闭（总闸未开）`
- **`tool_result.elapsed` 单位是秒**（`backend/agent/core/loop.py:426-435`），前端按 `data.name` 回填到同名且尚未填过的 `toolCalls[i].elapsed`；**不要**做消息级共享耗时——同轮多工具会显示成同一个值
- **聊天 SSE 已迁移 EventSourceResponse**（2026-11-25）：`/api/v1/agent/chat/stream` 由 `fastapi.sse.EventSourceResponse` 驱动，并删除了端点手写的 `Access-Control-Allow-Origin: *`（与全局 CORS allow_credentials 冲突）。前端若报 CORS 缺头，查 main.py 全局 CORS 配置而不是端点；流内自动出现的 15s 心跳注释帧属正常现象，不是脏数据
