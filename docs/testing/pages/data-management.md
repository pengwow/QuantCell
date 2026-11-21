# 数据管理（/data-management、/data-management/market-replay）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- 页面四个 tab 由 URL 驱动：`?tab=symbols|collection|quality|archive`（缺省/非法值回落 `symbols`）
- 交易所实时行情（`POST /api/v1/data/crypto/market-data`）属**外部依赖**：浏览器预览链路无系统代理继承时可能失败，
  失败只弹「获取市场数据失败」，价格列显示 `-`，**不算页面缺陷**（如实记录）
- 历史行情浏览/质量检测/行情回放都依赖**本地已采集数据**；没有采集过任何数据的空库只能验证"空态/表单渲染"，
  查询类断言标"按需"
- 行情回放页需要本地已有对应 `symbol + interval` 的 K 线（见 D6）

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| D1 | 直接打开 `/data-management` | 页头「数据管理」+ mono 副标「数据类型 10 类 · 已接入标的 N 个」（真实口径：DATA_KIND_LABEL 类数 × 交易所标的数）；页签下划线式无图标（选中 = 主色 + 2px 下划线）；货币对 tab 内工具栏为「搜索框(32px/8px 圆角) + 计价货币胶囊 全部/USDT/BTC/ETH（选中主色 tint） + 排序下拉 + 右侧 mono 计数 显示 x-y / 共 z + 刷新」；四张 KPI 卡「总标的 / 当前组 / 有数据 / 自动更新」（label 11px fg-4 + mono 22px/650 数值 + 10.5px 弱注）；左侧「自选组」树与「新建自选组」入口；表格列头「货币对 / 最新价格 / 24h涨跌 / 24h成交量 / 市值 / 数据状态 / 自动更新 / 操作」——标的列 mono + #排名/实时 chip、价格/涨跌/成交量/市值 mono 右对齐、空值「—」、数据状态 chip（良好绿/警告黄/异常红/未检测灰）、操作 24px 图标钮；表格下方 §6.7 分页条「共 N 条 · 每页 [12▾]」（档位 12 的倍数） | L1 |
| D1a | 在 D1 搜索框输入不存在的关键字（如 `zzzz`） | 表格出现 §6.13 空态「暂无数据 + 无匹配「zzzz」的结果」；清空后列表恢复、计数回到「显示 1-12 / 共 z」 | L1 |
| D2 | 点「数据采集」tab | URL 变为 `/data-management?tab=collection`；左卡「批量数据采集（支持全数据类型）」（qc 卡头 13px/650 无分隔线）含字段「数据类型 / 市场 / 选择货币对 / 时间范围 / 并发数」（字段 label mono 11px fg-4）与「市场」分段器（选中项主色 12% tint）+ 按钮「开始采集 · K线数据」；右卡「采集任务」+ 右上角 mono 圆角计数「共 N 条」，工具栏=搜索（占位「搜索任务 / 范围…」）+ 状态胶囊（全部/已完成/运行中/失败）+ 计数 + 刷新；任务表列「开始时间 / 任务 / 范围 / 状态 / 备注 / 操作」——开始时间 mono MM-DD HH:mm、任务=类型 chip + 市场 mono chip（当前任务多一枚「当前」）、范围 mono 截断带 Tooltip、状态 chip（已完成绿/运行中蓝点脉冲/失败红/等待灰）、备注=运行中迷你进度条+「x/y 项」或失败红字截断、完成态「—」、操作删除钮 24px | L1 |
| D2a | D2 表格点击「+」展开任一历史任务行 | 展开行显示子任务明细（symbol + 周期 chip + 百分比 mono + 进度条，失败标红），>5 条出「展开全部 / 收起」；无明细时空态「暂无子任务明细」 | L1（按需：有历史任务） |
| D3 | 点「数据质量」tab | URL 带 `?tab=quality`；左卡「质量概览」含 2×2 KPI「已检测(共 N 个) / 良好(green，占已检 x%) / 警告(amber) / 异常(red)」、区块「快速检测」（两个下拉「选择货币对」「选择周期」+ 按钮「开始检测」，未选齐时按钮置灰）、区块「数据清理」（按钮「打开清理工具」）；右卡标题「检测结果」，未检测时显示 §6.13 空态「请选择标的并点击检测按钮」 | L1 |
| D4 | 点「历史行情浏览」tab | URL 带 `?tab=archive`；左卡「历史行情浏览」顶部有分类切换「行情 (7) / 指标 (2)」（分段器选中主色 tint）与搜索框（占位「搜索 symbol...」），树内可见数据种类「归集交易 / 逐笔交易 / 深度快照 / 最优挂单 / 标记价格K线 / 指数价格K线 / 溢价指数K线」（K 线类条目带「K线」info 小芯片、衍生类带「衍生」pri 小芯片）；右卡初始显示 §6.13 空态「请在左侧选择数据浏览」与「步骤：展开数据种类 → 选择市场 → 点击 symbol」 | L1 |
| D5 | 展开「归集交易」→ 选「现货 Spot」→ 点任一 symbol | 右卡标题出现类型 chip + 市场 mono chip + symbol mono；`GET /api/v1/data/archive/meta/aggTrades/spot/{symbol}` 返回 200，展示「数据起始 / 数据结束 / 总行数 / 文件数」（值 mono）；下方动态列表走 qc 表格密度（th 10.5px / td 12px、数值/时间 mono 右对齐、布尔原样文本、空值「—」），§6.7 分页条「共 N 条 · 每页 [200▾]」**独立档位 100/200/500/1000**（与全局 12 的倍数档位无关，见代码注释）；顶部预设分段「近1天/近7天/近30天/近1年」主色选中。无任何已采集数据时本项跳过并记录 | L1（按需：已采集数据） |
| D6 | 打开 `/data-management/market-replay`（或从 K 线类数据（如「标记价格K线」）右卡的「行情回放」按钮带 `?symbol=&interval=` 进入） | 页面标题「行情回放」，卡「启动回放」内有蓝条说明「从指定品种与起始时间开始，逐根回放历史K线；指标只在已播放数据上计算」、字段「品种 / 起始时间」与按钮「开始回放」；品种默认 `BTCUSDT`，此前回放过的品种/时间会被记住回填 | L1 |
| D7 | 在 D6 填 `BTCUSDT` + 起始时间（例如近 30 天内）后点「开始回放」 | `GET /api/v1/data/klines?symbol=BTCUSDT&interval=1h&limit=2000&start_time=...&order=asc` 返回 200 且非空 → 进入回放视图：播放/单步后退/单步前进/重置按钮、速度下拉（0.25x–64x）、「跳到时间」、进度徽标「1 / n」与时间轴滑块，图表逐根出现。本地无该品种/周期数据时改为红条「起始时间 {{start}} 之后没有 BTCUSDT 的数据」——属按需项，记录即可 | L1（按需：本地已有该 symbol+interval 的 K 线） |
| D8 | 回放视图中点播放，再点暂停 | 播放中按钮提示为「暂停」，进度徽标分子递增、时间标签随之推进；暂停后停止推进。整页无控制台错误 | L1（在 D7 成功后可跑） |
| D9 | 新建自选组并删除：左侧「新建自选组」→ 名称填 `zz_test_group` → 保存；随后打开「管理自选组」抽屉删除它 | 弹窗为 §6.11 chrome（14px 圆角 + 1px 边 + 虚线分隔页脚，标题 14.5px/700，字段 label mono 11px）；保存发出 `POST /api/v1/data-pools/` 返回 200/201，提示创建成功，左树出现 `zz_test_group` 且计数标签为 0，抽屉内该组摘要为「0 个货币对 · 创建于 …」；「管理自选组」抽屉宽 400px、标题 13.5px/650、header 12px 16px、body 16px 内边距；删除时确认「确定删除此自选组？」→ `DELETE /api/v1/data-pools/{id}` 200，条目消失。**必须用 `zz_test_` 前缀命名并当场删除**；默认自选组不可删（删除按钮置灰并提示默认组不可删除） | L2 |
| D10 | 数据采集表单校验：清空「选择货币对」后再点「开始采集」 | 表单红字「请至少选择一个货币对或自选组」，**不发** `POST /api/v1/data/download/crypto`。真正点采集会向交易所批量拉数据（外部依赖 + 写盘），仅在有明确需要时执行 | L2（不写数据） |
| D11 | 在「数据采集」触发一次小范围采集后观察任务行，再删除该任务记录 | 任务表顶部出现「当前」任务行（状态「运行中」chip 带脉冲点、备注列进度条 + 「x/y 项」随 WS 推进；5s 静默刷新第一页）；完成后状态切「已完成」；点删除 → Popconfirm「删除该采集任务记录？」/「仅删除这条执行历史，已采集的数据不受影响。」→ `DELETE /api/v1/data/tasks/{taskId}` 200，提示「任务记录已删除」，当前页删空自动回上一页；进行中/当前任务的删除按钮置灰并提示「进行中的任务不可删除」 | L2（外部依赖：交易所；用最小时间窗，其中任务记录可删除） |
| D12 | 打开「打开清理工具」弹窗 | 弹窗「清理数据」为 §6.11 chrome（14px 圆角 / 虚线页脚），顶部黄条警告 + 表单「标的 / 周期 / 时间范围」字段 label mono 11px；确认按钮为危险红色。仅打开核对渲染，不实际执行清理 | L2（不写数据） |
| D13 | 亮 / 暗主题各截一张整页图 | 两主题下页头/页签/KPI 卡/表格/任务表/chip/弹窗抽屉均无白底漏洞或对比度塌陷（暗色 qc 卡底 rgb(29,31,35)、页签选中 rgb(249,115,22)、th fg 弱化） | L1 |
| D14 | 小徽章形制抽查（树/卡片/明细/回放） | 侧栏「全部/自选组」计数、卡视图 `#rank` 均为 §6.2 count-chip（mono 10px 全圆、bd-2 边、bge 底）；归档树 kind 小标签为 chips：「K线」info 芯 /「衍生」pri 芯（无 antd 彩色 Tag）；质量明细的缺列/重复形态=down 芯、字段警告=warn 芯、重复区间/时间段=quiet 芯且值 mono；回放页「1 / n」进度徽标为 count-chip（非 antd Badge 蓝点）；全页 getComputedStyle 抽查这些元素不出现 antd Tag 的 8c 类硬色 | L1 |
| D15 | JS 语义色随主题切换 | 24h 涨/跌、清理结果「已删除 N 条」、默认星标黄、质量 KPI 红黄均来自 `var(--qc-success/error/warning)`：切暗色主题后 getComputedStyle 颜色随之变化（亮暗 rgb 值不同）；树/市场/symbol 三级选中底为 `--qc-info` 8%/10%/30% tint，暗色下同样生效 | L1 |
| D16 | 首屏两块卡（四个页签下都应可见）：页头与页签之间自上而下「数据源水位」四张卡 +「存储用量」卡 | 四张水位卡标题依次为 `kline` / `fundingRate` / `markPriceKlines` / `aggTrades`（mono 11px），右上角状态 dot 只用真值着色（有数据绿、无数据灰、落后 > 1 天黄），卡内为「累计 bar（K 线类）/ 累计条目（其余）」+ mono 数值 +「最新 <日期>」+ 落后 chip；任何卡片都**不出现**「限频 / 断连 / 排队 / 方式 / 频率」等无源文案。切到 `?tab=collection|quality|archive` 两块卡仍在（不随页签消失） | L1 |
| D16a | 对照 `GET /api/v1/data/archive/watermark` 的返回逐卡核对数值 | 每张水位卡的「累计量」= 接口 `watermarks[]` 中同 kind 的 `total_rows`（≥100 万走紧凑写法如 `8.42M`，其余千分位整数）、「最新」= `latest_date`、落后 chip = 今天 − `latest_date` 的天数（日期粒度，`curl` 后手算核对）；`symbol_count` 作为卡底弱注「N 个标的」；接口里**没有**该 kind 时该卡整体弱色并显示「无数据」+ quiet chip「无数据」（接口不补 0 行占位，卡上也不得显示 0） | L1 |
| D16b | 存储用量卡逐行核对 | 每行 = `kind · parquet` + 6px 圆角占比条（宽度 = 该 kind `bytes` / `total_bytes`，主色 `var(--qc-primary)`）+ 右对齐 mono 体积（KB/MB/GB/TB 人读）；卡头右侧「合计 <体积>」= 接口 `total_bytes`；行按体积降序；无任何 parquet 时显示「暂无归档 parquet 数据」；**不得**出现「特征缓存 / LLM replay 记录 / 上次压缩 / 保留 180 天」等无源行/脚注 | L1 |
| D16c | 水位接口自身行为（可 `curl` 复核） | 空归档目录返回 `{"success":true,"watermarks":[],"storage":[],"total_bytes":0}`（空数组而非 0 行占位）；两族布局都统计：有 `_meta.json` 的归档目录以 meta 为权威（同目录 parquet 只计体积、不叠加行数），无 meta 的数据池 parquet（`crypto/{market}/klines/{interval}/{symbol}.parquet` → `kline`，`{fundingRate,openInterest}/{market}/{symbol}/*.parquet`）读 footer 得行数与日期；数据池布局的 `symbol_count` 按 distinct symbol 计（同标的多周期只算一个）；各数组按 kind 升序 | L2（只读） |
| D16d | 水位卡底「补齐」钮（只对有已采集数据的归档 kind 出现） | 卡底「N 个标的」右侧出现 11px 文本钮「补齐」；先 `curl "GET /api/v1/data/archive/symbols?kind=<kind>&market=<market>"` 核对：钮只在该 kind **至少一个 market 有已采集 symbols** 且该卡有 `latest_date` 时出现。`kline` / `fundingRate` 两张卡**不出现**该钮（`/data/archive/download` 的 `kind` 值域是 7 个 ArchiveKind，这两个 kind 走数据池下载路径，点了只会 400 = 假动作）。K 线类 kind 卡底另带周期下拉（默认 `1h`，档位 1m/3m/5m/15m/30m/1h/2h/1d）——后端 K 线类缺 interval 直接 400 | L1 |
| D16e | 点「补齐」后的真实响应 | Network 里按 market **各发一个** `POST /api/v1/data/archive/download`（spot/um/cm 各自一个，不混发），请求体 `mode:"inc"`、`start_date` = 该卡「最新」日期、`end_date` = 今天、`symbols` = 该 market 的已采集列表、K 线类带 `interval`；成功后 toast 显示真实的 `task_id`（形如「已创建 1 个补齐任务：<task_id>」），水位卡随后重新拉 `watermark` + `symbols`；**不出现**「已完成 / 已同步」字样（下载是后端异步任务，进度看「数据采集」tab 任务表）。失败时 toast 原样显示后端 `detail` 文案（如 `非法 kind` / K 线类缺 interval 的提示），不改写成通用错误 | L2（写任务记录，不写行情数据；可用最小 kind 试一次） |

## 历史雷区
- **采集/K线源数据曾落临时目录（已根治）**：桌面 sidecar 的下载源数据此前写进 PyInstaller 临时解压目录，升级/重启即丢。现已统一落 `QUANTCELL_DATA_DIR/data/source`；桌面回归点：采集一批数据 → 重启后端 → 历史浏览应仍有该批数据
- **行情列一直转圈/显示 `-`**：`POST /api/v1/data/crypto/market-data` 走交易所实时探测，分批（每批 100 个）请求，失败只弹「获取市场数据失败」。属环境类，先看请求是否发出、状态码是多少，再判断。
- **WebSocket + 5s 轮询双通道**：采集任务进度靠全局 WS 推送，同时存在运行中任务时每 5s 刷新第一页任务列表。两者并行是设计（WS 断了轮询兜底），页面"数字在跳"不等于重复提交。
- **`?tab=` 白名单**：非法/旧键名（如 `?tab=tasks`）会静默回落到「货币对」，看起来像"tab 点了没反应"。改 URL 验证时只用 `symbols/collection/quality/archive`。
- **大文件/长任务**：采集是后端异步任务（并发数 1–8），历史行情浏览按块分页；页面本身不做整库加载。真正的超时/慢在 sidecar 侧，查 `sidecar.log` 对应时间窗。
- **行情回放的"按需"边界**：回放只读 `/api/v1/data/klines`，没有数据就没有播放内容（红条提示而非崩溃）。分块加载 2000 根，向前/向后按需补块，图表看似"加载中"多一次请求属正常。
- **删除自选组不可恢复**：`DELETE /data-pools/{id}` 直接删组（含成员关系），验证时务必用 `zz_test_` 前缀并当场清理，不要删默认组。
- **采集任务表曾按"卡片流+无限滚动"渲染（已改造）**：任务列表现按 demo「同步任务」卡排版成表格 + 服务端分页（每页 20），原 TaskCard 的展开明细/删除能力移入展开行与操作列。搜索框是对**已加载行**的前端过滤（当前页撑满后应翻页再搜，不是全库搜索）。
- **历史浏览分页档位独立**：归档明细单次按条数拉全页（100/200/500/1000），**不走**全局 12 的倍数档位，也不读"每页显示数量"配置；看到分页档位不是 12 的倍数属预期。
- **水位卡「补齐」只认归档端点值域**：`POST /api/v1/data/archive/download` 的 `kind` 只接受 7 个 `ArchiveKind`（aggTrades/trades/bookDepth/bookTicker/mark·index·premium Klines）。`kline` 与 `fundingRate`/`openInterest` 是**数据池布局**的 kind，`GET /data/archive/symbols?kind=kline` 直接 400（`非法 kind`），所以这两张卡故意不显示「补齐」钮——想补它们走「数据采集」tab 的数据池下载路径。看到 kline 卡无钮属设计，不要"补回来"
- **数据源水位口径（两族布局 + 单位陷阱）**：`data/source` 下并存两种布局——归档布局 `{market}/{kind}/{symbol}/_meta.json`，与数据池布局 `crypto/{market}/klines/{interval}/{symbol}.parquet`、`{fundingRate,openInterest}/{market}/{symbol}/*.parquet`（**无 `_meta.json`**）。只认前者会漏掉全部 K 线（页面显示「kline 无数据」、存储合计少一半），已由 `get_watermark()` 的 parquet footer 兜底修掉。核查时若发现 `kline` 卡又变「无数据」，先看数据池布局是否被整体跳过。时间列有两个坑：名不统一（常规是 `timestamp`，pandas 导出的 `crypto/future/klines/1h/BTCUSDT.parquet` 在索引列 `__index_level_0__`），单位也不统一（`spot/*` 微秒、`future/*` 多为毫秒），必须**逐值按量级判**（`<1e11` 秒 / `<1e14` 毫秒 / `<1e17` 微秒 / 否则纳秒）；按路径硬编单位会算出 `1970-01-21` 这种假日期。stats 缺失只丢日期，行数与体积照算，**不得**用今天或文件名日期顶替
- **D1 副标口径**：副标只含「数据类型 10 类 · 已接入标的 N 个」两个真实可算数；demo 原文案的「数据源 4 类 / 保留 180 天」无后端接口支撑，**不得**加回副标或页头。存储用量已由首屏「存储用量」卡（`/data/archive/watermark` 的 `storage`）覆盖真实体积，但「特征缓存 / LLM replay / 上次压缩」仍无源，**不得**补；水位卡的 dot 只允许由真实数据推导（有/无数据、落后天数），「限频 / 断连 / 排队」无源，**不得**编造。
