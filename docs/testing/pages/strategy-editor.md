# 策略编辑器 + AI 生成（/strategy-editor，含 /strategy-editor/:strategyName）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- AI 生成完整路径**默认只到"请求发出"为止**（真实生成烧 LLM 配额，按需手动跑）
- 数据目录保留 AI 提供商配置可让 E4 走"已配置"分支；全新数据目录走"未配置"分支——两分支都合法，按实际断言

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| E1 | 打开 `/strategy-editor` | 页面渲染"策略编辑器"标题与"创建策略"入口；出现模板选择列表或空白 BaseStrat 选项 | L1 |
| E2 | 切换"编辑器 / 预览"页签 | 两个页签均可切换，代码区（Monaco，`quantcell-dark` 主题）渲染不白屏 | L1 |
| E6 | 在编辑器里看代码区容器（§6.16） | 容器 `background rgb(30,30,30)`、`border-radius 10px`、`1px` 边框；`body` 切亮色后编辑器仍 `rgb(30,30,30)`（chrome 恒深，不随主题） | L1 |
| E7 | 读代码字号与状态栏 | `.view-lines` 为 `12.5px / line-height 19px` mono；底部状态条底 `rgb(0,122,204)`、10.5px，「Spaces: 4」右对齐；点击编辑区按方向键后 `Ln x, Col y` 随光标变化（不是写死） | L1 |
| E8 | 看 token 配色（§6.16 表） | 注释 `rgb(106,153,85)` 斜体、字符串 `rgb(206,145,120)`、数字 `rgb(181,206,168)`、关键字 `rgb(197,134,192)`、标识符 `rgb(156,220,254)`；括号为默认前景 `rgb(212,212,212)`（**不应**出现金黄色 `rgb(255,215,0)` / 紫色 `rgb(218,112,214)` 的成对括号） | L1 |
| E3 | 选择一个模板创建策略 | 编辑器载入策略代码；右上保存可用（若执行写操作，用测试名如 `zz_test_doc` 并删除） | L2 |
| E4a | 点"AI生成策略"，弹窗内输入"创建一个双均线策略"，发送 | — 若数据目录**已配 AI 提供商**：思维链步骤开始渲染，network 出现 `POST /api/v1/ai-models/strategy/generate`（SSE）即算过，**不等待生成完成**，点击停止/关闭弹窗 | L1 |
| E4b | — 若**未配 AI 提供商**（400 分支） | 气泡出现**可读中文文案**（如"未配置默认AI模型"），绝不出现 `[object Object]` 或裸状态码 | L1 |
| E5 | "优化当前代码"页签 | 输入框可切换，提交按钮可点击（不要求真实优化完成） | L2 |

## 历史雷区
- **成对括号配色**（2026-11-20）：Monaco 默认开启 bracket pair colorization，`()`/`[]`/`{}` 会染金/紫/粉，与基准 demo 的单色括号不一致。修法是在主题里把 `editorBracketHighlight.foreground1..6` 统一到 `#d4d4d4`（`src/monaco/quantcellTheme.ts`）；**注意 `options.bracketPairColorization.enabled: false` 经 `@monaco-editor/react` 传不进去，别走那条路**
- **编辑器 token 色的唯一真相源是 `src/monaco/quantcellTheme.ts`**（不是 demo）。demo 的 `.tk-*` 是静态 mock，`node docs/design/check-spec.mjs` 会比对两者，改色必须三处同步：主题文件 → demo CSS → spec §6.16 表
- **`[object Object]`**（已修 75077d29）：后端 400 错误体 `{detail:{message}}` 被整体塞进 Error。E4b 是回归哨——**凡错误断言先看文案可读性**
- **自动化连发请求的假阴性**：多次触发发送会互相 abort，abort 气泡被 `bubbleItems` 的 `status!=='abort'` 过滤，看起来像"错误静默"。必须**整页刷新后单发单验**（2026-11-19 L1 实录，绕了两小时弯路）
- **AI 入口是图标按钮**：工具栏 AI 助手入口无文本，用 `button[aria-label*="AI"]` 定位；文本扫描按钮列表会漏
- **模板分类不存在**（已修 c9be36d5）：打包 sidecar 漏 `--add-data` 提示词模板，报"模板分类 'strategy_generation' 不存在或未加载"。若 E4 出现此文案 → 打包缺陷复发，查 `build-backend.sh`
- **警告弹窗遮点击**：antd Modal 的 a11y 快照残缺，定位弹窗内元素用 DOM 直查（`.ant-modal`、`textarea`、`[aria-label]`），别依赖 ref；页面上同存多个 `.ant-modal`（创建向导 + 聊天窗）时按"含 textarea 的那个"取聊天窗
- **SSE 正常结束 + error 事件**：流式错误以 `type:"error"` 事件在 200 流内返回（非 HTTP 错误码），断言气泡 `failed` 样式而非状态码
