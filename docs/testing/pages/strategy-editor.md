# 策略编辑器 + AI 生成（/strategy-editor，含 /strategy-editor/:strategyName）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- AI 生成完整路径**默认只到"请求发出"为止**（真实生成烧 LLM 配额，按需手动跑）
- 数据目录保留 AI 提供商配置可让 E4 走"已配置"分支；全新数据目录走"未配置"分支——两分支都合法，按实际断言

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| E1 | 打开 `/strategy-editor` | 页头为 `PageContainer`：标题 `qc-page-title`（16px/650，未载入策略时「创建策略/编辑策略」，载入后=真实策略名）+ 返回箭头；动作区 4 个 **30px 带字钮**（重置 / 去回测 / 保存 / AI 生成策略，末位 primary 550 字重），全部保留 Tooltip 与 `aria-label` | L1 |
| E1a | 载入已保存策略（如 `zz_test_doc`） | 标题旁出现 `qc-chip info` 版本 chip（`v{真实版本号}`）；`qc-page-sub` mono 副标显示「更新时间 {YYYY-MM-DD HH:mm} · 来源: 数据库」（真实 `updated_at` + 数据来源，不写死） | L2 |
| E2 | 切换"编辑器 / 预览"页签 | 两个页签均为 §6.8 下划线制式（2px 主色底边），无胶囊/size large；代码区（Monaco，`quantcell-dark` 主题）渲染不白屏 | L1 |
| E6 | 在编辑器里看代码区容器（§6.16） | 容器 `background rgb(30,30,30)`、`border-radius 10px`、`1px` 边框；`body` 切亮色后编辑器仍 `rgb(30,30,30)`（chrome 恒深，不随主题） | L1 |
| E7 | 读代码字号与状态栏 | `.view-lines` 为 `12.5px / line-height 19px` mono；底部状态条底 `rgb(0,122,204)`、10.5px，「Spaces: 4」右对齐；点击编辑区按方向键后 `Ln x, Col y` 随光标变化（不是写死） | L1 |
| E8 | 看 token 配色（§6.16 表） | 注释 `rgb(106,153,85)` 斜体、字符串 `rgb(206,145,120)`、数字 `rgb(181,206,168)`、关键字 `rgb(197,134,192)`、标识符 `rgb(156,220,254)`；括号为默认前景 `rgb(212,212,212)`（**不应**出现金黄色 `rgb(255,215,0)` / 紫色 `rgb(218,112,214)` 的成对括号） | L1 |
| E9 | 切到"预览"页签看容器 | 整块为 `qc-card`（`--qc-surface` 底 + `1px --qc-border` 边 + 10px 圆角）；卡头右侧为数据来源 **Segmented**（mono `database`/`parse`，选中项主色）+「重新解析」`qc-mini-btn`；亮/暗主题下卡底随主题变色、编辑器容器不变 | L1 |
| E10 | 预览页点「名称」行 | 进入编辑态（Input），Enter/失焦提交；提交后**页头标题同步**为新名称（demo edFName↔edTitle 对位）；「版本」「描述」两行同样可点击编辑 | L2 |
| E11 | 预览页看参数 / 依赖因子区 | 区头为 `qc-card-sub`（10.5px）+ `qc-mini-btn pri`「+ 添加参数 / + 添加因子」；行内元数据用 `qc-chip`（quiet/info/ok/warn）+ `qc-mono`，行尾 hover 出 `qc-mini-btn qc-icon-only`（编辑/删除）；新增行自动进编辑态、删除/改值可保存 | L2 |
| E12 | 打开"创建策略"模板选择弹窗 | `Modal` 挂 `qc-modal`（14px 面板圆角、§6.11 密度）；底部跳过/创建按钮为 `qc-mini-btn`；下拉底部上传行仍整行可点 | L2 |
| E3 | 选择一个模板创建策略 | 编辑器载入策略代码；右上保存可用（若执行写操作，用测试名如 `zz_test_doc` 并删除） | L2 |
| E3a | 模板选择弹窗选 grid 模板，看参数表单 | 价格计划配置项完整渲染：lower / upper / levels / position_limit 四项（默认 60000 / 70000 / 20，与 `GET /api/v1/ai-models/strategy/templates` 该模板 `variables[]` 逐条一致）；填参创建后（用测试名并删除）`POST /strategy/upload` 落盘的 `params` 与表单填写一致，worker 页价格计划预览档位数 = levels+1（W32-W36） | L2 |
| E3b | 同法选 martingale 模板 | direction 为下拉且 options 恰为 long/short/both；价格计划配置项齐全：direction / base_position / multiplier / max_multiplier / spacing_pct / spacing_multiplier / layer_count / take_profit_pct（默认 0.1 / 2.0 / 4.0 / 2.0 / 1.5 / 5 / 1.0）；**同名参数只渲染一次，不出现重复字段**（回归哨）；创建后 worker 页 plan 预览层价符合闭式公式（entry=100 → 100/98/95/90.5/83.75，满层仓位超上限出警告） | L2 |
| E4a | 点"AI生成策略"，弹窗内输入"创建一个双均线策略"，发送 | — 若数据目录**已配 AI 提供商**：思维链步骤开始渲染，network 出现 `POST /api/v1/ai-models/strategy/generate`（SSE）即算过，**不等待生成完成**，点击停止/关闭弹窗 | L1 |
| E4b | — 若**未配 AI 提供商**（400 分支） | 气泡出现**可读中文文案**（如"未配置默认AI模型"），绝不出现 `[object Object]` 或裸状态码 | L1 |
| E5 | "优化当前代码"页签 | 输入框可切换，提交按钮可点击（不要求真实优化完成） | L2 |
| E13 | 访客账号打开页面 | 「保存」钮 disabled 且 Tooltip 为访客限制文案；重置/去回测/AI 生成仍可点；确认弹窗（保存/重置/重新解析）正常 | L2 |
| E14 | 对比页头副标与预览档案卡里的时间 | 页头 `qc-page-sub` 的「更新时间 MM-DD HH:mm」与预览档案卡的创建/更新时间**同一套格式**（同为 `MM-DD HH:mm`，不混用 `YYYY-MM-DD`、不带秒）；悬停档案行时间 → Tooltip 显示完整 `YYYY-MM-DD HH:mm:ss` | L1 |
| E15 | 点「AI 生成策略」打开弹窗 | 弹窗标题右侧出现「kernel 兼容契约」chip（info 档色 + mono 形制，沿用 `qc-chip info` 口径）；不挤压标题、窄窗下不换行错位 | L1 |
| E16 | 载入已保存策略后点工具栏「版本历史」 | 右侧抽屉（标题「版本历史」，宽 920px）内为**左时间轴 + 右快照预览**双栏：左侧每条 = 时间 + 版本号 + `hash · 大小 · 行数`（当前条圆点高亮），点击即选中；右侧 = meta 行（版本 / 创建 / 大小 / 行数 / hash / 「当前文件」标记）+ 只读 Monaco 快照全文 + 底部「对比当前文件」开关与「载入编辑器」按钮；切换快照时 meta 与代码同步切（无第二次请求，按 id 缓存）；未载入策略时该钮 disabled；抽屉展开无 console error | L2 |
| E17 | 在编辑器里改代码但不保存 → 打开「版本历史」→ 点「载入编辑器」→ 确认 | Popconfirm 提示「把 {label} 载入编辑器？」，`dirty` 时额外出现「编辑器里尚未保存的改动会丢失」；确认后**只写编辑缓冲区**：`code` = 快照全文、页头出现「未保存」chip、保存按钮高亮，抽屉关闭并提示「已载入 {label} 到编辑器，保存后才会生成新快照」；此时 `GET /strategy/{name}/versions` 的 `count` 不变、磁盘文件未改（无任何写请求）；点「保存」后才 `POST /strategy/upload`，`count` +1（内容与最近快照相同则按 `code_hash` 去重不涨），「未保存」chip 消失 | L2 |

## 历史雷区
- **模板参数表单同名重复**（已修 2026-11-27）：`self.get_param("direction", "long")` 带 Literal 注解在策略的两个方法里各出现一次时，`strategy/service.py::_extract_params_from_get_param` 的 AnnAssign 分支漏检 `seen` 去重，templates 接口返回两个 `direction`、创建表单重复渲染同名字段。已修为「首次绑定为准」；E3b 的「不重复渲染」是回归哨。自写策略里同一参数多处取值属正常写法，提取器必须兜住
- **价格计划 tab 已从编辑器移除**（2026-11-27）：编辑器态没有货币对/运行时参考价，参考价全靠手填不实用。价格计划展示只保留 worker 链路（创建弹窗自检 / 启动确认 / 详情 plan tab / 列表摘要）与 backtest 回放 overlay；后端 `POST /api/v1/strategies/preview` 仍被 worker 链路使用，勿删。验证项见 `pages/strategy-worker.md` W32-W36。chart 页价格计划控制条已于 2026-11-28 移除（C14 同步删除）
- **成对括号配色**（2026-11-20）：Monaco 默认开启 bracket pair colorization，`()`/`[]`/`{}` 会染金/紫/粉，与基准 demo 的单色括号不一致。修法是在主题里把 `editorBracketHighlight.foreground1..6` 统一到 `#d4d4d4`（`src/monaco/quantcellTheme.ts`）；**注意 `options.bracketPairColorization.enabled: false` 经 `@monaco-editor/react` 传不进去，别走那条路**
- **编辑器 token 色的唯一真相源是 `src/monaco/quantcellTheme.ts`**（不是 demo）。demo 的 `.tk-*` 是静态 mock，`node docs/design/check-spec.mjs` 会比对两者，改色必须三处同步：主题文件 → demo CSS → spec §6.16 表
- **`[object Object]`**（已修 75077d29）：后端 400 错误体 `{detail:{message}}` 被整体塞进 Error。E4b 是回归哨——**凡错误断言先看文案可读性**
- **自动化连发请求的假阴性**：多次触发发送会互相 abort，abort 气泡被 `bubbleItems` 的 `status!=='abort'` 过滤，看起来像"错误静默"。必须**整页刷新后单发单验**（2026-11-19 L1 实录，绕了两小时弯路）
- ~~**AI 入口是图标按钮**~~（2026-11-21 已改带字钮）：AI 生成现为页头带字 primary 按钮（含 `aria-label`），可按文本定位；旧脚本若用 `button[aria-label*="AI"]` 仍兼容
- **页头结构（2026-11-21 收口 §5/§6.1/§6.16）**：标题/版本 chip 坐在 `PageContainer` 里；`PageContainer` 无「标题旁」插槽，版本 chip 落在动作区首位（规范化缺口已记录，见该页车道报告）；名称内联编辑入口在预览页「名称」行，**标题随 name state 实时同步**
- **模板分类不存在**（已修 c9be36d5）：打包 sidecar 漏 `--add-data` 提示词模板，报"模板分类 'strategy_generation' 不存在或未加载"。若 E4 出现此文案 → 打包缺陷复发，查 `build-backend.sh`
- **警告弹窗遮点击**：antd Modal 的 a11y 快照残缺，定位弹窗内元素用 DOM 直查（`.ant-modal`、`textarea`、`[aria-label]`），别依赖 ref；页面上同存多个 `.ant-modal`（创建向导 + 聊天窗）时按"含 textarea 的那个"取聊天窗
- **SSE 正常结束 + error 事件**：流式错误以 `type:"error"` 事件在 200 流内返回（非 HTTP 错误码），断言气泡 `failed` 样式而非状态码
