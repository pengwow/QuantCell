# 消息中心 / 收件箱（/notifications）

## 前置
- 环境与 token 注入见 `../README.md` 第一节；本页在 `AuthGuard` 内
- 组件：`frontend/src/pages/notifications/InboxPage.tsx`；预览面板：`frontend/src/components/NotificationInbox.tsx`；任务跳转注册：`frontend/src/utils/taskRoutes.ts`
- 接口：`GET /api/v1/notifications/inbox?limit=&before_id=&unread=&task_type=`、`POST /api/v1/notifications/inbox/{id}/read`（单条已读，任务类首次已读同时归档）、`POST /api/v1/notifications/inbox/read-all`、`DELETE /api/v1/notifications/inbox/read`、`DELETE /api/v1/notifications/inbox/{id}`
- 种子：默认数据目录**无通知**，L1 走空态分支；要验列表/已读/删除需先产生通知（运行任一策略或回测产生站内通知，或沿用已有通知的旧数据目录），在报告中注明种子来源；验任务类通知（N13/N14/N16）用任务终态产生：跑一次回测 / RL 训练 / 因子计算 / 数据采集 / 研究会话至终态，五域 key 为 `backtest` / `rl_train` / `factor_job` / `collector_task` / `research`
- `/setting/notifications` 是**通知渠道配置页**，与本页（站内收件箱）不同，勿混

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| N1 | 注入 token 后打开 `/notifications` | 页头「消息中心」（§5：title 16px/650）+ mono 副标「未读 X · 已读 Y」（X/Y 与 `GET /api/v1/notifications/inbox` 首响应的计数一致）；页头右侧「清空已读」（danger 默认钮）与「全部已读」（主色钮，均 30px 高/0 12px 内边距）；其下工具栏 Segmented「全部/未读/已读」+「全部任务类型」下拉；主区为 qc-card 列表卡（bgc 底 / --bd 边 / 圆角 10px）；`GET /api/v1/notifications/inbox` 返回 200；页面无控制台报错，URL 保持 `/notifications` | L1 |
| N2 | 观察列表区（无种子数据时） | 显示空态`暂无站内通知`，其下按钮文案`前往配置通知渠道`；不出现加载骨架卡死 | L1 |
| N3 | 观察列表底部图例 | 四个级别说明`提示` `成功` `警告` `错误` 全部可见（色点含义说明） | L1 |
| N4 | 观察页头右侧动作钮 | `清空已读` 与 `全部已读` 两个按钮存在；无已读/无未读时对应按钮为禁用态（不点击） | L1 |
| N5 | 有种子数据时观察列表 | 每条显示标题与时间（`MM-DD HH:mm` 形态），有正文时显示两行截断预览；列表底部显示`没有更多通知了`（不足 20 条）或`加载更多` | L2（需种子） |
| N6 | 点`加载更多`（>20 条种子时） | 发出 `GET /api/v1/notifications/inbox` 且带 `before_id=<当前列表末条 id>`；新条目追加在列表尾部，不重复不跳位 | L2（需 >20 条种子） |
| N7 | 未读 > 0 时点`全部已读` | `POST /api/v1/notifications/inbox/read-all` 返回 200；页头副标未读计数归零（变「未读 0 · 已读 N」）；`全部已读`转为禁用，`清空已读`可用 | L2（写操作，可撤销式验证） |
| N8 | 已读 > 0 时点`清空已读` | `DELETE /api/v1/notifications/inbox/read` 返回 200，随后重新请求收件箱第一页；列表中已读条目消失、未读条目保留 | L2（写操作，会删数据，用测试种子） |
| N9 | 悬停某条通知，点右侧删除图标 | 弹出确认气泡，文案含`确认删除这条通知？`；确认后 `DELETE /api/v1/notifications/inbox/{id}` 返回 200，该条从列表消失，未读数按响应 `unread_count` 更新 | L2（写操作，用测试种子） |
| N10 | 空态下点`前往配置通知渠道` | 跳转 `/setting/notifications` 且页面渲染 | L2 |
| N11 | 保持页面打开，触发一条新通知（如启动策略） | WebSocket 推送到达后未读数 +1，且列表头部插入新条目、页面出现浮动提醒；不刷新页面 | 按需（需 WS 推送 + 业务事件触发） |
| N12 | 点读写过滤 Segmented（`全部`/`未读`/`已读`） | 每次切换发出 `GET /api/v1/notifications/inbox` 且带 `unread=true` 或 `unread=false`；返回条目与所选态一致（未读项标题加粗、已读项灰显）；切回`全部`不带 `unread` 参数 | L2（需种子） |
| N13 | 任务域 Select 选`回测` | 请求带 `task_type=backtest`；列表仅剩 source 为 backtest 的条目；清空选择（allowClear）后恢复全量 | L2（需任务终态种子） |
| N14 | 点一条**任务类**通知行 | 该条未读时先发 `POST /api/v1/notifications/inbox/{id}/read` 返回 200 且行内样式转已读；随后跳转与域一致：RL 训练→`/model-hub?tab=train`、因子→`/factor-analysis`、采集→`/data-management`、研究→`/research`（WS 行带 task_id 时→`/research/{id}`）、回测→`/backtest`（WS 行成功态带 task_id 时→`/backtest/detail/{id}`）；非任务类行点击不跳转 | L2（需任务终态种子） |
| N15 | WS 推送送达时点浮动 toast | toast 可点击并按 N14 同表规则跳转；`source=system` 等非任务 toast 点击不跳转常背景 | 按需（需 WS 推送 + 业务事件触发） |
| N16 | 服务重启后的中断补偿 | 重启前人为留下中断任务（如 rl_train / factor_job 的 `async_task_records` 行留 queued、collector `tasks` 行留 running、`backtest_tasks` 行留 pending、research 会话留 running），重启后日志出现`任务通知补偿扫描`行，各域残留行被置终态，收件箱出现对应`已中断`/`失败`通知 | 按需（需重启场景） |
| N17 | 悬停页头右上角铃铛，打开预览面板 | 面板标题「消息中心」+ 右上「全部已读」；列表每行**完整**显示色点 + 标题 + 时间（`MM-DD HH:mm`），有正文时正文最多两行截断，行高约 39px —— **不得**出现行被压扁成几像素细条/文字被裁掉（见雷区）；列表最高 360px 内部滚动（15 行时应出现滚动条而非全部铺开）；底部「加载更多 / 查看全部」可见 | L1（需种子；无通知走空态） |

## 历史雷区
- **预览面板行被压扁成细条（已修）**：预览列表是 `flex flex-col max-h-[360px] overflow-y-auto`，行元素自带 `overflow-hidden`。`overflow:hidden` 会把 flex item 的自动最小高度（`min-height:auto`）置 0，于是 15 行 × 39px 超过 360px 限高时，行被 `flex-shrink` 均摊压缩到 9px —— 浏览器里就是一条条细横条，标题/正文全被裁掉（悬停铃铛看不到任何详细信息）。修法：行加 `shrink-0`。**同类组合排查**：`flex flex-col` + 限高 + 子项 `overflow-hidden`（或 `truncate`）都会踩同一坑，列表项一律要显式 `shrink-0`
- **请求失败会伪装成空态**：`loadList` 抛错后仅结束 loading、`items` 保持空数组，页面照样渲染`暂无站内通知`。断言"N2 通过"必须同时看 `GET /notifications/inbox` 的状态码，否则 401/500 会被当成"没有通知"
- **未读数的唯一权威是接口返回的 `unread_count`**：WS 推送只在前端 `bumpUnread` 本地 +1，刷新前可能与后端不一致。断言未读数以 `/notifications/inbox` 返回值为准
- **401 硬跳登录（已修）**：收件箱曾因 401 把用户踹回 `/login`（首页 H2 是同一回归哨）。本页若出现"打开即回登录页"，先查该接口状态码
- **WS 断开时列表仍 200**：新通知不会实时出现（只影响 N11），不要据此判列表页失败；先看 `/ws` 连接态
- **写操作会真删数据**：`清空已读` 与删除单条不可撤销，L1 绝不点击；L2 只用测试种子，且 N7→N8→N9 顺序执行会把种子耗尽，重跑前重新造种子
- **收件箱 REST 行不带 task_id**：task_id 只在 WS 实时推送的 `metadata` 里（后端 InboxNotification 未扩列）。REST 列表行点击跳的是兜底列表页（回测→`/backtest`、研究→`/research`），不要断言跳详情页；只有 WS 实时插入的行才可能跳 `/backtest/detail/{id}`、`/research/{id}`。N14 断言按行来源区分
- **跳转落点由 taskRoutes.ts 统一注册**：任务域 → 路径映射在 `frontend/src/utils/taskRoutes.ts`，五域 key 与后端 `task_notices.TASK_TYPES` 必须一致；新增任务域先加 resolver，漏配时点击已读但不跳转（静默，无报错）
