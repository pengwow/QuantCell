# 模型中心（/model-hub，含 ?tab=train|ensemble|history）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- 数据依赖：模型总表以「文件 = 唯一事实」扫描数据目录下 `models/*.zip`，**空目录也合法**（走空态分支）。
  - 有数据分支种子：`$DATA_DIR/models/` 下存在 `*.zip`；若同名 `<zip>.meta.json` 存在，sidecar 启动时会把它自动注册进注册表（幂等：注册表非空即跳过），并挑一个 `enforce_oos_gate=False` 晋升为 production
  - 集成页签依赖「此前创建过集成」；RL 回测历史页签依赖「此前跑过 RL 回测」，两者为空均属正常
- 展示形态跟随系统设置「默认展示类型」（`configStore.defaultViewType`，**缺省为卡片**）：断言不要只认表格
- 训练（M9）烧算力/耗时，默认只到「请求发出」为止，**L1 不断言训练完成**
- 旧地址 `/rl-training`、`/model-registry`、`/ensemble` 是 SPA 内 replace 重定向，分别落到本页 train / 总表 / ensemble 页签，不单列文档

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| M1 | 直接打开 `/model-hub` | 标题「模型中心」与四个页签「模型总表 / 训练工作台 / 模型集成 / RL 回测历史」可见；`GET /api/v1/models/unified` 返回 **200**；URL 保持 `/model-hub`（不回 `/login`） | L1 |
| M2 | 观察模型总表数据区与筛选栏 | 搜索框占位「搜索文件名 / 模型 ID」、两个筛选占位「算法」「状态」可见；有 zip 时渲染卡片（每卡含 Sharpe / 创建时间 / 大小 行）**或** 表格（表头「模型名称 / 状态 / 创建时间 / 大小 / 操作」）；无 zip 时渲染空态「暂无数据」。两分支都算过 | L1 |
| M3 | 依次点击四个页签 | 训练工作台 → URL 变 `/model-hub?tab=train` 且出现配置卡标题「强化学习训练配置」；模型集成 → `?tab=ensemble` 且出现「创建集成」「集成列表」两卡；RL 回测历史 → `?tab=history` 且出现提示「此处为 RL 模型回测历史；全部回测任务可在回测中心查看。」；点回模型总表 → URL 无 `?tab` | L2 |
| M4 | 直接打开 `/rl-training`、`/model-registry`、`/ensemble` | 分别落到 `/model-hub?tab=train`、`/model-hub`、`/model-hub?tab=ensemble`，且对应页签为选中态 | L2 |
| M5 | 在模型总表搜索框输入一个不存在的关键字 | 数据区立即变空态；network **不出现**新的 `/api/v1/models/unified`（纯前端过滤）。清空关键字后数据恢复 | L2 |
| M6 | 点某行「详情」（表格内为图标按钮，用 tooltip「详情」定位） | 抽屉标题含该文件名；`GET /api/v1/models/{model_id}/detail` 返回 200。「未注册」/「文件缺失」行不发该请求（抽屉内容为空），属正常 | L2 |
| M7 | 训练工作台：清空「训练步数」后点「开始训练」 | **不发出** `POST /api/v1/rl/train`；表单出现必填校验红字（形如 `'训练步数'是必选字段`）；「Walk-Forward 验证」「超参数优化 (HPO)」两个开关为禁用态（点不动） | L2 |
| M8 | 训练工作台：保持默认（PPO / BTCUSDT / 1h / 10000 步 / 奖励 pnl），点「开始训练」 | 发出 `POST /api/v1/rl/train`（原生 fetch，带 `Authorization` 头）即算过；按钮文案变「训练中...」并出现「取消」与进度卡。**不断言训练完成**；点「取消」中止后提示「训练已取消」 | L2（按需：烧算力/时长，默认跳过） |
| M9 | 模型集成页签：点「选择模型」 | 弹窗「选择模型」渲染候选模型表（列「模型名称 / 算法 / 大小」），**文件缺失条目不出现**；搜索框占位「搜索模型名称」 | L2 |
| M10 | 选中 ≥1 个模型后点「创建集成（N）」 | `POST /api/v1/ensemble/create` 返回 200，提示「集成 xxx 创建成功」，集成列表刷新出该行；若额外提示「跳过 N 个模型」仍是合法结果（成员加载失败不算失败） | L2（按需：写操作） |
| M11 | 集成行点冒烟预测图标（图标无文本，用 tooltip「零观测冒烟预测」定位） | `POST /api/v1/ensemble/{id}/predict` 返回 200，弹窗「冒烟预测 — {id}」显示聚合动作 BUY/HOLD 与成员 ratio 表 | L2（按需：外部依赖可加载的模型文件） |
| M12 | RL 回测历史页签 | `GET /api/v1/backtest/list?source=rl&page=1&page_size=20` 返回 200；无记录时表格空态文案为「完成一次 RL 回测后，历史记录将在此展示。」 | L2 |
| M13 | 在 RL 回测历史点某行「查看」 | 跳转 `/backtest/detail/{id}` | L2 |

## 历史雷区
- **训练没有进度源**：训练只走同步 `POST /api/v1/rl/train`（后端无 SSE/进度端点），前端 `progress` 恒为 `null` → 训练中进度条恒 0%、当前步数恒 0。这是现状实现，**不要据此判定"训练卡死"**；判据是请求是否 pending/返回
- **「取消」只 abort 浏览器侧 fetch**：后端训练线程继续跑并落模型文件。取消后再刷新总表可能出现新 zip —— 记录为"客户端中止"，别断言后端已取消
- **训练必须走 fetch 而非 axios**：axios 默认 30s 超时会掐断训练，故该调用手写 `fetch`。若后续改回 `apiRequest`，长训练必挂（这是刻意的取舍，不是遗留）
- **视图形态取决于系统设置**：默认 `card`，只按表格选择器断言会误判"列表没渲染"。先读系统设置「默认展示类型」，或同时接受卡片/表格两分支
- **删除不可逆**：删除按钮打的是 `DELETE /api/v1/rl/models/{stem}`，删的是真实 zip；确认弹窗已写明「文件删除后不可恢复；已注册条目将变为『文件缺失』」。自动化**不要**在真实数据目录跑
- **下载不走鉴权**：「下载」是 `window.location.href='/api/v1/models/{id}/download'`（后端该端点刻意不校验 Authorization）。大文件走浏览器下载，自动化链路里别点
- **`/models/unified` 503**：`RuntimeError("axon_quant.registry not available")` 会被包成 503 + 前端 toast「加载模型总表失败：…」。若出现，先查打包是否漏了 `axon_quant.registry`，不是前端问题
- **旧路由是 replace 重定向**：从 `/ensemble` 进入后浏览器后退回不到 `/ensemble`（历史被替换），断言用 pathname 而非后退行为
