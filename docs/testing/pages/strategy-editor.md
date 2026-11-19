# 策略编辑器 + AI 生成（/strategy-editor，含 /strategy-editor/:strategyName）

## 前置
- 环境与 token 注入见 `../README.md` 第一节
- AI 生成完整路径**默认只到"请求发出"为止**（真实生成烧 LLM 配额，按需手动跑）
- 数据目录保留 AI 提供商配置可让 E4 走"已配置"分支；全新数据目录走"未配置"分支——两分支都合法，按实际断言

## 验证项

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| E1 | 打开 `/strategy-editor` | 页面渲染"策略编辑器"标题与"创建策略"入口；出现模板选择列表或空白 BaseStrat 选项 | L1 |
| E2 | 切换"编辑器 / 预览"页签 | 两个页签均可切换，代码区（CodeMirror）渲染不白屏 | L1 |
| E3 | 选择一个模板创建策略 | 编辑器载入策略代码；右上保存可用（若执行写操作，用测试名如 `zz_test_doc` 并删除） | L2 |
| E4a | 点"AI生成策略"，弹窗内输入"创建一个双均线策略"，发送 | — 若数据目录**已配 AI 提供商**：思维链步骤开始渲染，network 出现 `POST /api/v1/ai-models/strategy/generate`（SSE）即算过，**不等待生成完成**，点击停止/关闭弹窗 | L1 |
| E4b | — 若**未配 AI 提供商**（400 分支） | 气泡出现**可读中文文案**（如"未配置默认AI模型"），绝不出现 `[object Object]` 或裸状态码 | L1 |
| E5 | "优化当前代码"页签 | 输入框可切换，提交按钮可点击（不要求真实优化完成） | L2 |

## 历史雷区
- **`[object Object]`**（已修 75077d29）：后端 400 错误体 `{detail:{message}}` 被整体塞进 Error。E4b 是回归哨——**凡错误断言先看文案可读性**
- **自动化连发请求的假阴性**：多次触发发送会互相 abort，abort 气泡被 `bubbleItems` 的 `status!=='abort'` 过滤，看起来像"错误静默"。必须**整页刷新后单发单验**（2026-11-19 L1 实录，绕了两小时弯路）
- **AI 入口是图标按钮**：工具栏 AI 助手入口无文本，用 `button[aria-label*="AI"]` 定位；文本扫描按钮列表会漏
- **模板分类不存在**（已修 c9be36d5）：打包 sidecar 漏 `--add-data` 提示词模板，报"模板分类 'strategy_generation' 不存在或未加载"。若 E4 出现此文案 → 打包缺陷复发，查 `build-backend.sh`
- **警告弹窗遮点击**：antd Modal 的 a11y 快照残缺，定位弹窗内元素用 DOM 直查（`.ant-modal`、`textarea`、`[aria-label]`），别依赖 ref；页面上同存多个 `.ant-modal`（创建向导 + 聊天窗）时按"含 textarea 的那个"取聊天窗
- **SSE 正常结束 + error 事件**：流式错误以 `type:"error"` 事件在 200 流内返回（非 HTTP 错误码），断言气泡 `failed` 样式而非状态码
