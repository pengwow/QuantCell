<!-- 页面清单 = check-coverage.mjs 的对账基准。路由列必须与路由表字面量一致（参数路由折叠为无参形式；重定向路由不单列）。
     状态：✅ 已有文档｜⏳ 文档待补（不阻塞闸门，但 L2 覆盖前不得宣称该区域已验证） -->
# 功能区 → 验证文档索引

| 路由 | 功能区 | 文档 | 状态 | 层级 | 种子/前置 |
|---|---|---|---|---|---|
| `/login` | 登录注册 | `pages/login.md` | ⏳ | L1 | 无（未注入 token 时直达） |
| `/home` | 首页看板 | `pages/home.md` | ✅ | L1 | token 注入 |
| `/chart` | 行情图表 | `pages/chart.md` | ⏳ | L1 | token 注入 |
| `/strategy-worker` `/strategy-worker/:workerId` | 策略智能体/运行中策略 | `pages/strategy-worker.md` | ⏳ | L1 | token 注入 |
| `/strategy-management` | 策略管理列表 | `pages/strategy-management.md` | ⏳ | L1 | token 注入 |
| `/strategy-editor` `/strategy-editor/:strategyName` | 策略编辑器 + AI 生成 | `pages/strategy-editor.md` | ✅ | L1+L2 | token 注入 |
| `/backtest` `/backtest/config` | 回测中心 | `pages/backtest.md` | ⏳ | L1 | token 注入；有效回测记录可由 API 预置 |
| `/backtest/detail/:backtestId` `/backtest/replay/:backtestId` | 回测详情/回放 | `pages/backtest.md` | ⏳ | L2 | 同上 |
| `/model-hub` | 模型中心 | `pages/model-hub.md` | ⏳ | L1 | token 注入 |
| `/factor-analysis` | 因子分析 | `pages/factor-analysis.md` | ⏳ | L1 | token 注入 |
| `/research` `/research/:id` | 策略研究 | `pages/research.md` | ⏳ | L1 | token 注入 |
| `/notifications` | 消息中心 | `pages/notifications.md` | ⏳ | L1 | token 注入 |
| `/model-management` | 模型管理 | `pages/model-management.md` | ⏳ | L1 | token 注入 |
| `/data-management` `/data-management/market-replay` | 数据管理 | `pages/data-management.md` | ⏳ | L1 | token 注入 |
| `/setting/*`（9 个子页） | 设置 | `pages/settings.md` | ⏳ | L1+L2 | token 注入；AI 提供商配置是全站 L2 的种子 |
| `/agent` 子页 | 智能体工作台 | `pages/agent.md` | ⏳ | L1 | token 注入 |
| 插件注册的动态路由（`pluginRegistry`） | 插件页 | 按插件单独补 | ⏳ | 按需 | 安装对应插件 |
