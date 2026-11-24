# 策略管理（/strategy-management）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- **数据依赖**：本页数据源是 `GET /api/v1/strategy/overview`（策略 × worker × 最近回测聚合，后端提供）。端点不可用/404 时页面为合法空态（表格空态 + toast），此时跳过依赖聚合列的断言（S4-S7、S11-S12）
- 无数据也是合法状态：表格空态为 `.qc-empty` +「暂无策略」，卡片视图同文案
- 列表/卡片形态跟随系统设置「默认展示类型」（页面无切换按钮），断言前先确认当前形态
- 造数据（行级操作 L2 用）：在 `/strategy-editor` 新建 `zz_test_probe` 并保存 → 回到本页。收尾：行内删除或 `DELETE /api/v1/strategy/zz_test_probe`
- 对照口径：`curl -s http://localhost:8000/api/v1/strategy/overview` 的 `data.strategies[]` 是状态/Worker/最近回测三列的唯一真值来源
- 展示/回测入口不再指向本页退役页签：「回测记录」页签已删除，回测统一在回测中心（断言见 S10）

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S1 | 打开 `/strategy-management` 并读页头副标 | 副标为 mono 单行「共 N 个 · 运行中 N · 模拟盘 N · 已暂停 N · 未部署 N · 点击行查看参数详情」，六段计数与 `/strategy/overview` 逐项一致（live/paper/paused/undeployed 各自求和、N 为 strategies 总数）；若 overview 里真实存在 stopped/error 则副标在「已暂停」与「未部署」之间/之后**如实多出「已停止 N」或「错误 N」段**；全文**不得出现「草稿」**（strategies.status 只有 active，无此语义） | L1 |
| S2 | 数工具栏状态 chips | 基线 6 枚：全部 / 运行中 / 模拟盘 / 已暂停 / 未部署（+ 真有 stopped/error 数据时增补「已停止」「错误」，此时为 7-8 枚）；点各芯片表格按 state 精确过滤且页码归 1；点「全部」恢复；**不含「草稿」chip** | L1 |
| S3 | 读表头 | 前五列顺序恰为：策略 / 标的 · 周期 / 状态 / Worker / 最近回测，末列为操作（共 6 列，类型徽章并入策略列、标的与周期合并为一列）；「策略」列 = 行首展开三角 + 策略名（单行截断）+ 类型徽章（9px 缩小版）；Worker 与最近回测两列数字右对齐 | L1 |
| S4 | 抽查任意一行的「状态」列 vs `curl /strategy/overview` | 状态 chip 与该行 `state` 字段一一对应：live=ok chip+pulse 圆点「运行中」、paper=warn「模拟盘」、paused=quiet「已暂停」、stopped=quiet「已停止」、error=down「错误」、undeployed=info「未部署」；即状态列是 worker 聚合的投影，与 worker 列表页同口径，不是 strategies 表自己的字段 | L1 |
| S5 | 抽查「Worker」列 vs curl | 值 = 该策略 `worker_count`，右对齐 mono；0 显示弱色 0（不染色不隐藏）；>0 普通前景色 | L1 |
| S6 | 抽查「最近回测」列 vs curl | `latest_backtest` 为 null → 弱色「未回测」；status running/pending → 弱色「回测运行中」；failed → 红色「失败」；completed 且 total_return>0 → 绿色「+x.xx%」、<0 → 红色「-x.xx%」、**=0 → 中性色「0.00%」（0 不染色）**；completed 但 total_return 为 null → 弱色「—」 | L1 |
| S7 | 点第一行 | 行打 primary 5% tint + 左侧 3px 主色条 + 行首三角旋转 90° 变主色；**面板就地展开在该行正下方**（表格内 `<tr class="ant-table-expanded-row">` 的 `.qc-exp-panel`，不是表格下方常驻块），面板头 = 「策略详情」+ 策略名（mono）+ 状态 chip（与该行状态列同一映射）+ 右侧「v{version} · 更新 {MM-DD}」；主体 = 参数键值两列表（键列弱色 mono 参数名、值列默认值 + `[min ~ max]` 弱色 + 弱色描述），与 `/strategy/overview` 该项 `params[]` 的 name/default/description/min/max 逐条一致；底部 = 主色「去回测」+「创建 Worker」+ footer 一行「默认 runner：kernel · 累计回测 N 次 · 版本历史 N 条」（`backtest_count` / `version_count` 由 `/strategy/overview` 回传 = 该策略历史回测任务总数 / 版本快照总数，与 `curl` 原始 JSON 逐条一致；字段缺席时**不显示版本历史段**，`version_count=0` 时显示弱态「版本历史 0 条」（不可点开，见 S19），**不得出现编造的 0/固定数**） | L2 |
| S8 | 参数为空的策略上点行 | `params` 为空数组或缺失时面板显示弱提示「该策略没有可调参数」，不留空表壳；**`version_count` 为 0 时 footer 保留版本历史段，形制为弱态文字「版本历史 0 条」且不可点开**（初始化入库、从未经保存入口的策略属于此列，是真实值不是缺陷）；`version_count > 0` 时该段为可点按钮，N 与接口一致 | L2 |
| S9 | 点行内面板「创建 Worker」 | 打开 worker 创建弹窗（worker 模块现成组件），提交后真实 `POST /workers` 并刷新本页聚合计数（Worker 列/副标数字变化）；不弹「点了没反应」的死钮行为 | L2 |
| S10 | 点行内「去回测」（或面板主色钮） | 跳转 `/backtest/config` 且该策略已预填（state.strategy.name = 点击行名）；点页头「发起回测」跳同一页但不带预填；**页面任何位置不存在「回测记录」页签或指向 `?tab=` 的链接** | L2 |
| S11 | 直接打开 `/strategy-management?tab=backtests` 或旧返回链路 `?search=..&status=..` | 地址立即被 replace 成裸 `/strategy-management`，落在列表视图，无任何页签；刷新后仍为列表 | L1 |
| S12 | 千万注意反数据造假 | 全页搜索「草稿」无结果；「版本历史」只允许出现在行内展开面板 footer（且其 N 必须等于 `curl /strategy/{name}/versions` 的 `count`；为 0 时显示弱态「版本历史 0 条」且不可展开，不隐藏也不编数）；周期/标的/最近回测字段为 null 时一律显示弱色「—」，Worker 为 0 显示弱色 0；无任何写死/假造的聚合数 | L1 |
| S13 | 切到卡片视图（系统设置改默认展示类型） | 卡片不因新列退化：卡头名称 mono + 类型/状态 chip 行，卡面含 周期 / 标的 / Worker（0 弱色）/ 最近回测（同 S6 染色）/ 更新时间行，底部「去回测」+「编辑」钮；点卡片 → 选中并就地展开与列表**同一份**详情面板（详见 S22），再点同卡收起；卡内删除钮/编辑钮不触发选中变化；不报错 | L2 |
| S14 | 工具栏搜索「zzz」/清空 | 按名称/描述/标的即时前端过滤不发请求，页码归 1，无匹配显示空态；排序 Select（更新时间 ↓ 默认）仍在且切换生效，不发请求 | L2 |
| S15 | 点行内「去回测 / 编辑 / 删除」 | 三个操作钮 stopPropagation：**不触发行内展开/收起，也不改变当前展开行**（已展开行保持不变）；删除弹「确认删除策略」确认框，取消则行仍在；编辑跳 `/strategy-editor/<名称>`；访客账号删除钮 disabled 且处理函数访客早退（不发 DELETE） | L2 |
| S16 | 在 `/strategy-editor` 选一个真实策略保存一次（内容确实改动）→ 回本页点该行，再展开「版本历史」 | ① 保存后 `curl /api/v1/strategy/{name}/versions` 的 `count` 比保存前 +1，行内面板 footer 的「版本历史 N 条」N 与之一致；② 展开列表按时间倒序显示前 20 条（`MM-DD HH:mm` + `v{version}` 或 code_hash 前 8 位），超过 20 条时末尾有「仅显示最近 20 条」；③ **同内容再保存一次 → N 不变**（去重按 code_hash 比对上一条）；④ 从未保存过的策略（`version_count=0`）footer 显示弱态「版本历史 0 条」且不可展开（不隐藏、不编数）；⑤ 接口 `versions[]` 不含 `code` 字段 | L2 |
| S17 | 找一个长度 > 30 字符的真实策略名（现网有 `strategy_with_underscores`；不足则用长名策略保存一次），观察「策略」列 | ① 名字被截断并以省略号结尾，**单元格宽度不随名字长度变化**（`document.querySelector('.ant-table-tbody td').getBoundingClientRect().width` 对长/短名两行相等）；② 表格总宽 ≤ 容器宽（`.ant-table-content` 无横向滚动条），长名不会把其余列挤出可视区；③ 鼠标悬停该格 → 浮层显示**完整名字**（与 `curl /strategy/overview` 的 `name` 逐字一致）；④ 短名（如 `trend_follow`）不出现省略号，悬停浮层仍是完整名 | L1 |
| S18 | 进入 `/strategy-management`，等列表加载完成，**不点任何行** | **首屏不选中、不展开任何行**（无 `.qc-row-selected` 行、无 `.ant-table-expanded-row`），页面底部也不再出现常驻详情块；点任意行 → 该行选中并就地展开；**再点同一行 → 收起且取消选中**；同一时刻最多一个展开行（点 B 行时 A 行自动收起）；搜索 / 状态筛选 / 排序 / 翻页任一变化 → 自动收起（无展开行）；展开行被筛选排除后不残留面板；列表为空时不选中任何行 | L1 |
| S19 | 展开一个 `version_count=0` 的策略行，看面板 footer | footer **仍出现版本历史段**，形制为弱态文字「版本历史 0 条」且不可点开（无折叠箭头 / 点了不展开）；`version_count>0` 时该段仍为可点按钮，点击展开折叠列表（倒序前 20 条），N 与 `curl /api/v1/strategy/{name}/versions` 的 `count` 一致 | L1 |
| S20 | 看「标的 · 周期」列（多标的策略） | 单标的 = 标的（primary 加粗）+ 弱色「 · 周期」；2 个标的 = 逗号分隔整串（限宽截断）；≥3 个 = 首个 + 小号 quiet 徽章「+N」（N = 总数−1），例如 4 个标的显示「BTC/USDT +3 · 1d」；`symbols` 为空 → 弱色「—」（周期存在时仍显示「— · 周期」）；悬停该列 → Tooltip 显示全部标的 + 周期；数值与 `curl /strategy/overview` 的 `symbols`/`interval` 一致（不显示自选组形态——overview 契约无该字段） | L1 |
| S21 | 键盘操作 | 行可 Tab 聚焦；聚焦行上按 Enter 或 Space → 展开/收起（与点击同效）；面板展开时按 Esc → 收起（焦点在面板按钮上时也生效）；行首三角随展开态旋转 90° 并变主色，收起恢复 | L1 |
| S22 | 卡片视图与列表视图各点同一策略（首项）展开详情 | ① 两种形态共用 `selectedRowKey`：列表点首行 / 卡片点首卡都展开**内容逐字相同**的 `.qc-exp-panel`（`innerText` 空白归一后字符串相等，参数 KV、footer、版本历史段一致，不出现串到同行邻卡的情况）；② 卡片态面板插在**被点卡片所在视觉行的最后一张卡之后**、跨满整行（`.qc-card-exp-slot` 与 `.ant-row` 左右边界对齐），展开前后该视觉行卡数不变；③ 再点同一张卡 → 收起；Esc → 收起；列表态搜索 / 状态筛选 / 排序 / 翻页、卡片态分页条翻页，以及切换卡片↔列表视图 → 均收起；首载不自动展开；面板打开不产生 console error | L2 |

## 历史雷区
- **数据源是 overview 不是 list**（2026-11-21 重构）：本页只消费 `GET /strategy/overview`；将其回退成 `/strategy/list` 并在前端拼 state/worker_count 属于造假，禁止。端点 404/405 时是空态 + toast，不是页面 bug
- **state 是后端优先级投影**（2026-11-21 落联调）：`live > paper > paused > error > stopped`，无 worker → `undeployed`（worker 次/进程异常等中间态由后端归桶，前端照 `state` 字段渲染，不得自行再判）。现网 worker 多为 `interrupted` → 端点落 `stopped`，所以「已停止」「未部署」常态化出现——这两 chip 必须真实可见可筛选，不得为贴近 demo 五桶而隐藏或并桶
- **「最近回测」取任务表最新一条**（`WHERE strategy_name=? ORDER BY created_at DESC LIMIT 1`，后端聚合）：status 驱动染色（失败 down / 运行中 weak）优先于百分比；`total_return` 为 null（任务无 result_id 是常态）时显示「—」，**不得显示 0.00%**；只有 `total_return === 0` 才显示中性色 0.00%
- **interval/symbols 来自关联 worker 聚合**（多 worker 去重并集）：无 worker → `null`/`[]` → 显示「—」，不回填策略文件里的默认值
- **「回测记录」页签已退役**（2026-11-21）：表格、`?tab=backtests`、buildReturnUrl 返回链路全部删除。老入口（回测详情/回放的 returnUrl）进页会被 replace 成裸路径（S11）。后端 `source=` 能力不动
- **搜索不重置页码**（已修复 2026-11-20）：搜索 onChange 必须把 pagination.current 拨回 1（S14 断言）
- **删除策略无权限兜底**：删除处理函数内已有 `isGuest` 早退（2026-11-21 补），绕过 disabled 的自动化点击不再发出 DELETE
- **删除不可恢复**：确认文案已写明，没有回收站/软删。除 `zz_test_probe` 外不要在任何真实策略上点「确定」
- **状态列语义**：live/paper/paused/stopped/error 全部来自 worker 聚合（见 S4）。「已停止」「错误」chip 只在真有数据时出现（chips 与副标同步增删），不要为了凑 demo 五桶而隐藏
- **详情块曾在表格下方，用户发现不了 → 改行内展开**（2026-11-23）：旧实现把详情常驻在表格下方（`.sm-detail`），选中行与面板在视觉上分开，长列表/翻页后看不出对应关系，用户基本不会去展开。现改为 antd `expandable` 行内展开（`expandedRowKeys` 单键 + `expandRowByClick` + `showExpandColumn: false`，三角自绘在策略列），面板贴在行下方；**不要再把详情块放回表格底部**，也不要为了自绘三角而开两条展开状态（选中态与展开态是同一份 `selectedRowKey`，由 `onExpand` 单向写回）
- **行内展开的副作用**（2026-11-23）：`expandRowByClick` 在行元素上触发，行内动作钮必须 `stopPropagation`（现有 `.qc-row-actions` 容器已做），否则点「去回测/编辑/删除」会连带展开/收起行；搜索/筛选/排序/翻页必须显式清空 `selectedRowKey`，否则面板留在旧行或跨页失联
- **详情块footer 的「累计回测 N 次」**：取 `/strategy/overview` 的 `backtest_count`（同一次任务遍历累计，不加额外查询）；字段缺席时只显示「默认 runner：kernel」，不许写死数字。计数为 0 是真实值（该策略没跑过回测），与「未回测」列语义一致
- **版本历史只记录经过保存入口的保存**（2026-11-21）：`strategy_versions` 只在 `save_strategy()`（以及界面保存实际走的 `upload_strategy_file()`）成功后旁路写入；初始化/批量导入入库的策略没有历史（`version_count=0` 属预期，不是缺陷）。同内容重复保存按 `code_hash` 去重不涨条数。策略删除后历史保留（审计需要），但 overview 按现存策略文件遍历，不会出现幽灵计数
- **`version` 不是历史序号**：`strategies.version` / 快照里的 `version` 是策略文件声明的版本号（`__version__` / `VERSION` 常量，未声明为 null），与「第几条快照」无关；前端在没有声明版本时展示 `code_hash` 前 8 位，不要把 `1.0.0` 之类的默认值当历史序号写死
- **表头/行密度被 antd 覆盖**（2026-11-20 踩坑）：`.qc-table` 密度规则必须写 `.qc-table.ant-table-wrapper ...` 前缀（见 `global.css`）；详情块的 kvtab 在页面私有 `StrategyManagement.css`，色值只用 `var(--qc-*)`
- **策略名列必须限宽截断**（2026-11-21）：`DataTable` 默认 `scroll={{x:'max-content'}}` + 自动表格布局，列上声明的 `width` 不是硬约束——**在裸 `inline` span 上写 `maxWidth` 完全无效**（inline 元素忽略 max-width），长名会把该列撑到 700px+、整表横向溢出。正确写法是给渲染节点 `display:block` + `maxWidth` + `overflow:hidden/text-overflow/white-space`，外层套 `Tooltip` 显示全名（S17）。改列宽时不要靠名字长度"自然"限制
- **首屏不再预选/自动展开**（2026-11-23，替换旧的「兜底选全量首行」逻辑）：详情改行内展开后，自动选首行 = 自动展开首行（demo 首载展开只属于原型演示）。现行口径是首屏零展开，只在「当前展开行被筛选/删除排除」时清空；别再为了「首屏有内容」恢复 setSelected(首行)，那会把行内面板顶在用户脸上并和 S18 打架
- **卡片展开面板按 key 取数据，不用组件回调参数**（2026-11-24）：`ExpandableCardGrid` 把面板插在「视觉行最后一张卡」之后，`renderExpanded(item)` 的回调参数是**那一张卡**而非被点卡；直接把参数丢给 `renderDetailPanel` 会让面板串到同行邻卡（首卡展开显示第 4 张卡的内容）。本页改为 `renderExpanded={() => renderDetailPanel(selectedItem)}`，以 `selectedRowKey` 为准与列表同源；改动组件本身前先处理这个语义分歧
