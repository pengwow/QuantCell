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
| AG1 | 注入 token 后打开 `/agent` | 工作台骨架渲染：左栏空态标题`策略智能体`、输入框占位`输入消息，按 Enter 发送，Shift+Enter 换行...`；右栏 8 个页签`决策流` `持仓/订单` `绩效` `模型` `日志` `审计` `事件与拥挤` `自迭代` 全部可见；顶栏出现 `Worker` 选择器（有选中 Worker 时另带状态标签） | L1 |
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
| AG12 | 在输入框发送一句话 | 发出 `POST /api/v1/agent/chat/stream`（SSE，HTTP 200 流），气泡逐步渲染`AI 正在思考...`/思考过程；失败以错误气泡呈现可读文案。**真实调用消耗 LLM 配额，默认跳过** | 按需（真实 LLM 配额） |
| AG13 | 在`自迭代`页签点`开始训练` | 提交后台训练任务并出现 `训练中`/`排队中` 等阶段文案 | 按需（消耗算力，且需已选 Worker/模型） |
| AG14 | 把 `agent_gateway` 能力关闭后直达 `/agent` | 渲染 403 页：标题`功能未开启`，副标题含 `agent_gateway`；侧边菜单也不出现该入口 | L2（环境配置分支） |

## 历史雷区
- **无子路由**：不要构造 `/agent/xxx` 之类的地址找子页——React Router 里只有 `/agent`，工作台子页一律用 `?tab=`。写错路径会落到首页重定向或 404，而不是某个 Tab
- **URL 与 store 双向同步有回写竞态**（已修）：挂载首拍同时执行 URL→store 与 store→URL，曾把 URL 里的 tab/worker 打回默认值。断言 AG3 要等同步稳定（条件轮询 URL），不要在 `domcontentloaded` 瞬间取值
- **图标按钮无文本**：顶栏`会话历史`/`工具参数设置`/`清空会话`/`展开或收起面板`都是纯图标 + tooltip，文本扫描找不到，按 `aria-label`/tooltip 或 DOM 直查定位
- **日志 SSE 重连有上限**：`WorkerLogStreamSSE` 内部最多重连 5 次，超限断开后需重新挂载页面才会再连；"日志一直未连接"先看是否已超限，而非后端无日志
- **无 Worker 时右栏是空态不是故障**：所有 Tab 都靠 `workerId` 取数，`workerId` 为空即不发请求、不建日志流。L1 只验骨架，别把空态当数据缺失
- **能力关闭即 403**：`agent_gateway` 关闭时菜单隐藏且直达 URL 被 `CapabilityGuard` 拦成`功能未开启`。见到该文案先查 `GET /api/v1/capabilities`，别按前端 bug 追
- **删除会话需手输确认词**：删除弹窗要求输入`确认删除`才能点确认，自动化误点会被卡在弹窗；L2 收尾清理会话时优先走 API 或直接跳过
- **SSE 错误不是 HTTP 错误码**：聊天失败在 200 流内以 error 事件返回（气泡标记错误），按状态码断言会误判成功
