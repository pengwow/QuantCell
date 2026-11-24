# 智能体工作台（/agent）

## 前置
- 环境与 token 注入见 `../README.md` 第一节；本页在 `AuthGuard` 内，且被 `CapabilityGuard capability="agent_gateway"` 包裹
- 组件：`frontend/src/pages/agent/Agent.tsx`（左聊天 `components/ChatPanel.tsx`，右工作面板 `components/workbench/WorkbenchPanel.tsx`）
- **路由形态**：`DynamicRouter.tsx` 里 agent 只有一条路由 `/agent`，**没有子路由**。工作台"子页"是右栏 Tab，靠查询参数持久化：`/agent?tab=<tab>&worker=<id>`，tab 取值 `decisions`（决策流）/`positions`（持仓/订单）/`performance`（绩效）/`models`（模型）/`logs`（日志）/`audit`（审计）/`events`（事件与拥挤）/`selfloop`（自迭代）；非法 tab 回落 `decisions`
- 能力开关：`GET /api/v1/capabilities` 中 `agent_gateway` 必须为 true，否则整页渲染 403 文案`功能未开启`（这是部署配置，不是页面缺陷）
- 种子：无需求；没有 Worker 时右栏全部落到空态/占位，页面骨架仍应完好。真实让 AI 跑任务会烧 LLM 配额，标"按需"

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| AG1 | 注入 token 后打开 `/agent` | 工作台骨架渲染：左栏空态标题`智能体工作台`、输入框占位`输入消息，按 Enter 发送，Shift+Enter 换行...`；右栏 8 个页签`决策流` `持仓/订单` `绩效` `模型` `日志` `审计` `事件与拥挤` `自迭代` 全部可见；顶栏出现 `Worker` 选择器（有选中 Worker 时另带状态标签） | L1 |
| AG2 | 页面加载完成后查 network | `GET /api/v1/capabilities` 返回 200；`GET /api/v1/agent/sessions` 200；`GET /api/v1/agent/tools` 200；`GET /api/v1/workers?page_size=100` 200；控制台无未捕获错误 | L1 |
| AG3 | 观察 URL | 稳定后 URL 变为 `/agent?tab=decisions`（存在 Worker 时附带 `worker=<id>`），无刷新；直接打开 `/agent?tab=logs` 时该页签为选中态 | L1 |
| AG4 | 切到`决策流`页签 | 有选中 Worker 时发出 `GET /api/v1/workers/{id}/decisions?limit=200`（5s 轮询）；无决策时显示`该 Worker 暂无决策记录（运行后自动写入）` | L2 |
| AG5 | 切到`持仓/订单`页签 | 发出 `GET /api/v1/workers/{id}/strategy/positions?status=OPEN` 与 `GET /api/v1/workers/{id}/strategy/orders`；空仓时显示`当前无持仓`，页面不报错 | L2 |
| AG6 | 切到`绩效`页签 | 未选 Worker 时显示`选择 Worker（右栏数据域）`；有 Worker 时加载指标区（`总盈亏`/`收益率`/`胜率`/`夏普比率`/`最大回撤`/`交易次数`）与`累计收益曲线`，无数据显示`暂无数据` | L2 |
| AG7 | 切到`模型`页签 | 发出 `GET /api/v1/models/unified`；表格渲染（表头含`模型`/`算法`/`观测`）或空表，不出现错误提示 | L2 |
| AG8 | 切到`日志`页签 | 有选中 Worker 时页面已建立 SSE `/api/v1/workers/{id}/monitoring/logs/stream`（随 Worker 建立，不随 Tab 重建）；页签内出现`日志流已连接`或`日志流未连接`状态文案，日志行持续追加 | L2 |
| AG9 | 切到`审计`页签 | 发出 `GET /api/v1/agent/audit`；空数据显示`暂无工具调用审计（工具一旦被调用即落库）`，有数据按时间倒序列表 | L2 |
| AG10 | 切到`事件与拥挤`页签 | 显示占位文案`事件与拥挤指标将在接入后展示`（该模块未接后端，属如实空态） | L2 |
| AG11 | 打开会话历史抽屉，点`新会话` | 发出 `POST /api/v1/agent/sessions` 并提示`新会话已创建`；会话名形如`会话 <时间>`，URL 与当前会话同步 | L2（写操作，结束后可删除该会话） |
| AG12 | 在输入框发送一句话 | 发出 `POST /api/v1/agent/chat/stream`（SSE，HTTP 200 流），气泡逐步渲染`AI 正在思考...`/思考过程；轮内有工具调用时 AI 气泡头部出现`迭代 N/40`徽标（SSE `iteration_start` 逐轮推进，上限 40 熔断）。失败以错误气泡呈现可读文案。**真实调用消耗 LLM 配额，默认跳过** | 按需（真实 LLM 配额） |
| AG13 | 在`模型`页签选模型后提交训练 | 提交后台训练任务并出现 `训练中`/`排队中` 等阶段文案（`TrainPanel` 挂在模型页签，不在自迭代页签） | 按需（消耗算力，且需已选 Worker/模型） |
| AG14 | 把 `agent_gateway` 能力关闭后直达 `/agent` | 渲染 403 页：标题`功能未开启`，副标题含 `agent_gateway`；侧边菜单也不出现该入口 | L2（环境配置分支） |
| AG15 | 切到`自迭代`页签 | 发出 `GET /api/v1/agent/memory` 与 `GET /api/v1/agent/loop-status`（并行加载、各自失败只在该卡显示重试，不整卡报错）；四卡骨架齐全：`迭代足迹`/`记忆自迭代（Dream）`/`每日闭环时钟线`/`重训台账` | L2 |
| AG16 | 观察`记忆自迭代（Dream）`卡 | 总闸 chip 与 `QUANTCELL_AGENT_DREAM` 实际值一致；MEMORY.md 只读渲染；`已整合 x/y` 进度（x=模型下游 `.dream_cursor`，y=history.jsonl 行数）；`上次运行`三态如实（无记录`重启后尚未运行`/no-op 灰/失败红可展开 detail）；`下次运行：每日 04:00`；底部注明`Dream 只整理记忆，不会替你执行交易` | L2 |
| AG17 | 观察`每日闭环时钟线`卡 | 四行 job 与 `core/scheduler.py` 挂载一致（03:30 OOS 审计 / 03:35 每日复盘 / 03:40 自动重训 / 04:00 Dream）；总闸环境变量未开时该行显示`已关闭（总闸未开）`灰点而非红失败；行可点开展开 last_run 详情/错误 | L2 |
| AG18 | 观察`重训台账`卡 | 双闸 chip 与 `QUANTCELL_AUTO_RETRAIN`/`QUANTCELL_AUTO_PROMOTE` 实际值一致；任一关闭时出现警示条「模型不会自动更换——终点为晋升待审，需人工审核」；空表显示`暂无重训台账记录`并注明 shadow 对照为回测替代口径（已知降级项）。**默认部署双闸全关，`已关闭`是正确断言不是缺陷** | L2 |
| AG19 | 视觉收口：徽章形制（亮/暗各跑一遍） | 整页（含全部右栏 Tab、抽屉、弹窗）DOM 中 `.ant-tag` 数量为 0；Worker 状态、训练状态、审计状态、模型 stage、决策 buy/sell 徽章均为 `.qc-chip` 形制（tint 底 + 语义档位），进行中徽章带 `.qc-pdot` 脉冲点 | L1 |
| AG20 | 视觉收口：聊天流形制 | `getComputedStyle` 断言：AI 头像 32×32、`border-radius: 8px`、底色 = info token；消息气泡 `border-radius: 12px`、内边距 11px/15px、有 bubble-shadow；用户消息行右对齐、气泡底色 = `--qc-user-bubble-bg`；工具调用为链式节点形制（mono 工具名 + 参数摘要 + 状态 chip），而非孤立项徽章 | L1 |
| AG21 | 视觉收口：主题换挡 | 切换亮/暗主题后无需刷新：页面底、气泡底、边框、徽章 tint 全部跟随 token 变化（`computedStyle` 的 `background-color`/`border-color` 应随主题出现两套不同 rgb）；页面任何位置不出现写死的灰阶色块 | L1 |
| AG22 | 右栏首屏两卡可见，8 页签退居其下 | 打开 `/agent`（不切 tab）右栏**第一眼**是「迭代足迹」卡（卡头标题 + 右侧弱色说明 + 柱图区）与「记忆自迭代（Dream）」卡（卡头 + MEMORY.md 只读体 + 键值行）；两卡下方 8 个页签（`决策流`…`自迭代`）全部可见且可切换；`/agent?tab=logs` 直达时页签选中态仍生效（tab 持久化不受两卡影响） | L1 |
| AG23 | 迭代足迹卡柱数 = 真实迭代数 | 无数据（新会话/仅历史恢复）时卡体为弱色空态提示，**不画占位柱**；发一条消息跑完 ReAct（按需，耗 LLM 配额）后出现对应柱：柱数 = 当前会话带轮次的 AI 回复数（SSE `iteration_start`/`complete` 聚合，与气泡「迭代 X/Y」徽标同源），不足 12 不补齐、不循环；均值 chip 只按画出的柱计算；熔断虚线取 SSE 真实上限（40）并置于轨顶，上限不可证时不画线 | L2（空态 L1；柱数须真实 LLM 回合，按需） |
| AG24 | Dream 卡字段全部来自 self-loop 接口 | `GET /api/v1/agent/memory` 返回值渲染：chip 与 `QUANTCELL_AGENT_DREAM` 实际值一致（`QUANTCELL_AGENT_DREAM = 1/0` mono 形制）、MEMORY.md 只读体、`已整合 x/y` 进度条（x=dream_cursor，y=history_entries）、`待处理`（>0 才显示）、`上次运行` 三态如实；读取失败显示弱色提示 + 右上刷新钮，不显示假数据 | L2 |
| AG26 | Dream 卡「下次运行」行（`next_run_at` 非空才有） | 同时读 `GET /api/v1/agent/loop-status` 里 `agent_dream` 的 `next_run_at`（后端直接取真实挂载的 APScheduler `job.next_run_time`，非解析 cron）：非空时 `上次运行` 下方出现一行「下次运行 `MM-DD HH:mm` · N 小时后」（相对量按分钟/小时/天取最小可读档位）；mount 时刻已过则显示「即将运行」而不是负值；`next_run_at` 为 `null`（job 未挂载，即 `QUANTCELL_AGENT_DREAM` 总闸未开）时**整行不渲染**，不得显示 04:00 之类推算值。`curl /api/v1/agent/loop-status` 可核实：总闸关闭时 `next_run_at: null` | L2 |
| AG25 | 页头真值 + 两个跳转钮 | 页头轻量行（非 PageContainer）：标题`智能体工作台` + mono 副标`会话 #<id> · ReAct 单轮上限 40 次迭代 · SSE 实时`（会话 id 为真实 session key，「40」为项目常量 backend/agent/core/loop.py `max_iterations` 默认值）；右侧两枚 30px 钮：`策略智能体 →` 跳 `/strategy-worker`、`← 返回首页` 跳 `/home`；既有顶栏（会话/Worker 控件）不受影响 | L1 |
| AG27 | 观察工具节点耗时 chip | 真实跑一次带工具调用的 ReAct 后（按需，耗 LLM 配额），每个工具节点右侧出现「耗时 x.xxs」chip，数值来自 SSE `tool_result.data.elapsed`（秒）；同轮多个工具各自独立、不共享同一数值；历史消息（无 `elapsed`）不显示该 chip，也不显示 `0s` | L2（按需） |
| AG28 | 每日复盘消息结构化渲染 | 每日复盘消息（03:35 job 写入 default 会话）在聊天流里带出处 chip「定时任务 · 每日复盘」，并按 `meta.report.sections` 渲染 概览 / 活跃 Worker / 持仓异常 / 风控建议 / 模型与 OOS 小节；空节整节省略；刷新页面后从 history 恢复时同样识别（`meta` 原样回传） | L2 |
| AG29 | 模型页签「部署」二次确认卡里的「标的」字段 | 与全站同一份标的源下拉（紧凑写法 `BTCUSDT` + 可搜索），不再是无约束手输框；默认值仍取回测/模型 prefill 的 symbol；提交 `POST /workers` 的 symbol 为紧凑形态 | L2 |
| AG30 | 观察会话区外框与卡头 | 左侧聊天区是 demo 同款「会话卡」：1px 边 + 10px 圆角，卡头左侧「会话 · <会话名>」13px/650 + 绿点「实时」chip，右侧依次为 Worker 选择器、会话历史图标钮、工具参数图标钮、「清空会话」文字 mini 钮、面板折叠图标钮；消息区只在卡内滚动（滚到底时页头/卡头不动、`window.scrollY` 保持 0），输入区固定在卡片底部不被裁出视口 | L1 |
| AG31 | 长会话滚到底后看整体 | `.ai-agent-layout` 高度吃满 `qc-main`：卡片底边贴在视口内（1440×900 下无纵向溢出、无窗口滚动条），换 1280×720 也不出现输入区被切；明暗两主题下卡片底/边、卡头分隔线、实时 chip 都随 token 切换 | L1 |

## 历史雷区
- **工作区曾落临时目录（已根治）**：agent 会话/工作区文件此前写进 PyInstaller 临时解压目录，升级/重启即丢。现已统一落 `QUANTCELL_DATA_DIR/data/agent_workspace`
- **无子路由**：不要构造 `/agent/xxx` 之类的地址找子页——React Router 里只有 `/agent`，工作台子页一律用 `?tab=`。写错路径会落到首页重定向或 404，而不是某个 Tab
- **URL 与 store 双向同步有回写竞态**（已修）：挂载首拍同时执行 URL→store 与 store→URL，曾把 URL 里的 tab/worker 打回默认值。断言 AG3 要等同步稳定（条件轮询 URL），不要在 `domcontentloaded` 瞬间取值
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
