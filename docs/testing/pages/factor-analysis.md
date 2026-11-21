# 因子分析（/factor-analysis）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- 页面两个 Tab 由 URL 驱动：`?tab=library`（缺省）／`?tab=compare`；选中因子写在 `?factor=<name>`
- 因子库目录由后端内置 + 自建因子组成，**无需预置数据**即可渲染列表（空库时显示空态）
- 分析/对比依赖本地已采集 K 线（见 F6，标"按需"）
- 导航入口：左侧菜单「因子分析」，或直接访问 URL

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| F1 | 直接打开 `/factor-analysis` | 页头标题「因子分析」+ mono 副标「因子库 N 个 · 有效 x · 观察 y · 失效 z」（N/x/y/z 与 `catalog` 按状态聚合一致：LIVE=有效，DISCOVERED/INSPECTED/PAPER_TRADING=观察，RETIRED=失效）；页头右侧主色「新建因子」；工具栏有搜索框（占位「搜索因子名 / 名称」）、状态胶囊 chips「全部/有效/观察/失效」、下拉「全部分类」「全部来源」、「刷新」、「策略研究」、右侧计数「显示 x-y / 共 z」；主区为表格（列头「因子 / 分类 / 来源 / IC 均值 / ICIR / 覆盖率 / 状态 / 快照数 / 最近快照 / 操作」）或空态
（搜索/筛选无结果时文案为「没有匹配的因子」，库为空时为「因子库为空，可新建因子或使用 LLM 挖掘」，两者不同） | L1 |
| F1a | 因子库表格「覆盖率」列（位于 ICIR 与「状态」之间） | 列头文本为「覆盖率」（en 为 `Coverage`），单元格右对齐 mono、形如 `98.2%`（一位小数，与右侧概览「覆盖率」同口径）；取首行因子名对照 `curl -s http://localhost:8000/api/v1/factor/catalog` 中该条 `last_metrics.coverage`，单元格文本 = `(coverage × 100).toFixed(1) + '%'`；`last_metrics` 缺失或 `coverage == null` 时显示 `—`（**不是 0.0%**） | L1 |
| F2 | 观察 F1 加载过程中的网络与 URL | `GET /api/v1/factor/catalog` 返回 200；目录加载后若选中了某因子，URL 变为 `?factor=<name>`（replace 写入，不新增历史）；切换/刷新后选中项保持（记住上次查看因子） | L1 |
| F3 | 点「因子对比」Tab | URL 变为 `/factor-analysis?tab=compare`（同时保留 `factor` 参数，参数顺序不限）；出现卡「分析参数」，字段「因子 / 品种 / 周期 / 时间范围 / IC方法 / 分组数 / 滚动窗 / 前瞻(根) / 衰减滞后 / 单边成本(bp) / FDR校正」与按钮「开始对比」；下方空提示「选择 2-5 个因子后点击「开始对比」」；`GET /api/v1/factor/list-detail` 与 `GET /api/v1/factor/instruments?candle_type=spot` 均返回 200 | L1 |
| F4 | 回「因子库」Tab，点任意一行（或行操作列的「眼睛」图标） | 眼睛钮悬浮提示「查看详情」；右侧抽屉打开（宽约 68% 视口），展示该因子的「展示名 + 英文标识（mono）」标签行与 Tab「概览 / 分析 / 快照 / 代码」；标签行用胶囊 chip（内置/代码/合成/AI/无数据），内置因子带「内置」标签 | L1 |
| F5 | 页头点「新建因子」（用 `zz_test_` 前缀）→ 名称填 `zz_test_momentum`，展示名 `zz_test 动量`，表达式填 `close / Ref(close, 5) - 1` → 先点「校验」再「保存」 | 弹窗标题「新建因子」，字段「因子名称（英文标识） / 展示名（可选） / 分类 / 描述（可选）」与模式切换「表达式 / Python 代码」；「校验」发出 `POST /api/v1/factor/validate` 200 并提示「校验通过」；「保存」发出 `POST /api/v1/factor/add` 200，提示「因子已保存」；弹窗关闭、目录刷新，列表出现该因子并被选中（右侧详情抽屉随之打开）。**必须用 `zz_test_` 前缀命名并在 F6 清理** | L2 |
| F6 | 清理：在列表对该 `zz_test_momentum` 行点删除（红色垃圾桶图标） | 确认气泡标题「删除因子」，正文「将删除该因子及其本地实现，因子档案同步清理：zz_test 动量（zz_test_momentum）」；确认后 `DELETE /api/v1/factor/delete/zz_test_momentum` 返回 200，提示「已删除因子」，行消失。**这一步就是 F5 的清理动作，不可跳过** | L2 |
| F7 | 对任意内置因子点删除按钮 | 按钮置灰不可点，悬浮提示「内置因子不可删除」；不发任何 DELETE 请求 | L2（只读校验） |
| F8 | 「分析」Tab 跑一次单因子分析（选内置因子 + 品种 + 周期） | 提交后出现进度卡（圆圈进度 + 阶段文案），`POST /api/v1/factor/analyze-async` 返回 job_id；完成后展示 IC 序列/分组收益/分位净值等结果区块。**按需**：需要本地已有该品种+周期的 K 线，且为后端重计算，耗时随窗口增长 | 按需（本地行情数据） |

| F9 | 代码编辑器 chrome（§6.16）：抽屉「代码」Tab 选**代码类**因子（如 `rs_17_21`，表达式类因子 `volume * close` 只是纯文本块、无 Monaco），再看新建弹窗的「Python 代码」模式 | 代码区容器 `rgb(30,30,30)`、圆角 10px、1px 边框；`.view-lines` 为 `12.5px / 19px` mono；底部状态条 `rgb(0,122,204)`、10.5px、`Ln x, Col y` 随光标变化；亮色主题下代码区仍是 `rgb(30,30,30)`；注释 `rgb(106,153,85)` 斜体、字符串 `rgb(206,145,120)`、关键字 `rgb(197,134,192)`、括号为 `rgb(212,212,212)`（不出现金/紫成对括号）。**回归哨：本页样式收口不得动 Monaco 主题** | L1 |

## 历史雷区
- **因子快照曾落临时目录（已根治）**：`data/factor/snapshots` 与 `.trash` 归档桌面端此前写进 PyInstaller 临时解压目录，升级/重启即丢。现已统一落 `QUANTCELL_DATA_DIR`
- **目录是一次性全量请求**：`GET /api/v1/factor/catalog` 返回**全部**因子（含 `last_metrics`），搜索/分类/来源筛选与分页都在前端对全量数组做。因子库很大时列表首屏慢、翻页无额外请求——看到"翻页没有网络请求"不是 bug。
- **异步任务双通道**：分析/对比走 `analyze-async` / `compare-async` 拿 `job_id`，进度优先由 WebSocket 主题 `factor:job` 推送，WS 未证明存活时降级轮询（1s→2s→5s 退避），**10 分钟无终态判超时**（提示"任务超时（10 分钟无结果），请重试"）。进度卡长时间不动先看 WS 是否连上，再看 `/api/v1/factor/jobs/{id}` 是否在刷。
- **内置因子不可删**：删除按钮只对自建因子可用，置灰 + "内置因子不可删除"；后端同样有保护，别把置灰当缺陷。
- **选中项来自三处决策**：`?factor=`（命中才生效）> `localStorage['factor.lastViewed']` > 目录第一条。刷新后"选中跑偏"通常是上次查看的因子被删或 URL 参数不合法。
- **状态只有一组演示口径（有效/观察/失效）**：接口给的是 5 态生命周期，页头副标与筛选 chips 共用同一映射：LIVE=有效、DISCOVERED/INSPECTED/PAPER_TRADING=观察、RETIRED=失效（映射写在 `FactorAnalysis.tsx` 的 `statusGroupOf` 与 `FactorLibraryPane.tsx` 的 `inGroup`，改口径两处要同步）。demo 副标的「样本 1h 全品种 · RankIC（日频）」接口没有返回，**不写**。
- **新建因子入口在页头右侧**（demo page-actions），不在工具栏；弹窗本体仍在 `FactorLibraryPane`，页头只持有开/关状态。
- **列表删除已从 modal.confirm 换成 Popconfirm 气泡**（与回测中心同款，避免键盘 Delete 直删的老雷区复发），确认文案保持「删除因子 / 将删除该因子及其本地实现…」不变。
- **工具栏状态筛选是 `.qc-ichip`（26px 胶囊）**，表格内状态是 `.qc-chip`（10px 徽章），是两个原语，不许混用（spec §6.6/§6.2）。
- **抽屉无标题栏**：详情抽屉不带 title，靠内容里的展示名/英文标识识别；自动化断言请取 `body.innerText` 而不是找 `.ant-drawer-title`。
- **图标按钮无文本**：列表操作列是纯图标（查看详情/删除），只能用 Tooltip 文案或 `aria-label` 定位，文本扫描会漏。
- **`FactorFormModal` 曾漏登记 4 个词条**（`factor_lib_form_label` / `_label_hint` / `_label_ph` / `factor_ai_polish`）：i18next 缺键时返回 key 本身（truthy），代码里的 `t('k') || '中文兜底'` 兜不住，弹窗直接显示 `factor_lib_form_label`。已在 zh/en 两侧补键；**以后再写 `|| '中文'` 兜底必须先确认词条存在**，否则等于没兜。
