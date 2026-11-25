<!-- 页面清单 = check-coverage.mjs 的对账基准。路由列必须与路由表字面量一致（参数路由折叠为无参形式；重定向路由不单列）。
     状态：✅ 已有文档｜⏳ 文档待补（不阻塞闸门，但 L2 覆盖前不得宣称该区域已验证） -->
# 功能区 → 验证文档索引

| 路由 | 功能区 | 文档 | 状态 | 层级 | 种子/前置 |
|---|---|---|---|---|---|
| —（无独立路由，挂任意已登录页） | 全站通用 chrome：toast / notification | `pages/common.md` | ✅ | L1 | 任一已登录页 |
| `/login` | 登录注册 | `pages/login.md` | ✅ | L1+L2 | 无（守卫外；真实登录见文档 A4 条件式） |
| `/home` | 首页看板 | `pages/home.md` | ✅ | L1 | token 注入 |
| `/chart` | 行情图表 | `pages/chart.md` | ✅ | L1+L2 | token 注入；实时行情按需 |
| `/strategy-worker` `/strategy-worker/:workerId` | 策略智能体/运行中策略 | `pages/strategy-worker.md` | ✅ | L1+L2 | token 注入；创建 worker 需策略库非空 |
| `/strategy-management` | 策略管理列表 | `pages/strategy-management.md` | ✅ | L1+L2 | token 注入 |
| `/strategy-editor` `/strategy-editor/:strategyName` | 策略编辑器 + AI 生成 | `pages/strategy-editor.md` | ✅ | L1+L2 | token 注入 |
| `/backtest` `/backtest/config` | 回测中心 | `pages/backtest.md` | ✅ | L1+L2 | token 注入；详情/回放需有效 backtestId |
| `/backtest/detail/:backtestId` `/backtest/replay/:backtestId` | 回测详情/回放 | `pages/backtest.md` | ✅ | L2 | 同上 |
| `GET /api/v1/jobs/queue`（后端 API，无独立前端页） | 作业池队列观测 | `pages/backtest.md`（B29-B30） | ✅ | L1 | token 注入；B30 需真实发起一次回测 |
| `/model-hub` | 模型中心 | `pages/model-hub.md` | ✅ | L1+L2 | token 注入；有数据分支需 `$DATA_DIR/models/*.zip` |
| `/factor-analysis` | 因子分析 | `pages/factor-analysis.md` | ✅ | L1+L2 | token 注入 |
| `/research` `/research/:id` | 策略研究 | `pages/research.md` | ✅ | L1+L2 | token 注入 |
| `/notifications` | 消息中心 | `pages/notifications.md` | ✅ | L1+L2 | token 注入；非空态种子靠业务事件/任务终态；任务过滤与跳转见 N12-N15 |
| `/model-management` | 模型管理（演示壳） | `pages/model-management.md` | ✅ | L1+L2 | token 注入；仅 URL 直达（无菜单入口） |
| `/data-management` `/data-management/market-replay` | 数据管理 | `pages/data-management.md` | ✅ | L1+L2 | token 注入 |
| `/setting` `/setting/account` `/setting/general` `/setting/env` `/setting/exchange` `/setting/notifications` `/setting/model` `/setting/agentTokens` `/setting/info` `/setting/plugins` `/setting/desktop-backend` | 设置页群（10 子页） | `pages/settings.md` | ✅ | L1+L2 | token 注入；AI 提供商配置是全站 L2 的种子 |
| `/agent` | 智能体工作台（`?tab=` 八视图） | `pages/agent.md` | ✅ | L1+L2 | token 注入；真实 LLM 任务按需 |
| 插件注册的动态路由（`pluginRegistry`） | 插件页 | 按插件单独补 | ⏳ | 按需 | 安装对应插件 |
