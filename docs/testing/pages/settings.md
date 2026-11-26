# 设置（/setting/*，10 个子页）

## 前置
- 环境与 token 注入见 `../README.md` 第一节；无数据依赖
- 路由映射：`frontend/src/router/DynamicRouter.tsx`（`/setting` 为父路由，`index` 重定向到 `/setting/general`）；子页组件在 `frontend/src/pages/setting/`
- 每个子页加载时都会因 `SettingsProvider` 挂载发起 `GET /api/v1/config/`（`configApi.getConfig`）与 `GET /api/v1/system/metrics`；这两条是设置页群的共同前置信号
- `/setting/desktop-backend` 仅在桌面壳（Tauri）菜单可见；其余 9 个子页在浏览器链路全覆盖
- **本页是 AI 策略生成的配置种子**：`/setting/model` 配好默认生成式提供商后，`pages/strategy-editor.md` 的 E4 才走"已配置"分支（否则走 400 分支 E4b）
- 写操作一律 L2；敏感页（exchange / model / agentTokens）文档内**不出现任何真实 key 值**，断言止于"保存成功提示"

## 设置框架（/setting）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S0a | 直接打开 `/setting` | URL 变为 `/setting/general`（父路由 index 重定向）；页面标题区出现「设置」，左侧菜单文本含 账户管理 / 通用设置 / 环境变量 / 交易所设置 / 通知设置 / 模型设置 / Agent Token / 系统信息 / 插件管理 | L1 |
| S0b | 页面加载完成后 | `GET /api/v1/config/` 返回 200；`GET /api/v1/system/metrics` 返回 200；控制台无未捕获错误 | L1 |
| S0c | 点击左侧菜单「模型设置」 | URL 变为 `/setting/model` 且右侧内容区切换（不整页刷新） | L1 |

## 账户管理（/setting/account）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S1 | 打开 `/setting/account` | 卡片标题「账户信息」可见，行标签 用户名 / 昵称 / 角色 / 用户 ID / 账户类型 全部渲染（值为 `-` 或实际值均可）；卡片「账户安全」内出现「修改密码」按钮 | L1 |
| S2 | 点「修改密码」 | 弹窗标题「修改密码」，三个密码输入框（旧密码 / 新密码 / 确认新密码）可见；点「确认修改」在两次新密码不一致时给出「两次输入的新密码不一致」，且**不**发出 `POST /api/v1/auth/change-password` | L2 |
| S3 | 用临时账号走完整改密（密码用 `zz_test` 前缀；验证后改回） | `POST /api/v1/auth/change-password` 返回 200，提示「密码修改成功」；弹窗关闭、字段清空。desktop-local 免登录下若无当前用户表记录，接口报错属预期，如实记录状态码，不判失败 | L2（按需，仅在有可改的用户时） |
| S4 | 点「注销登录」 | 先出现确认框「确认注销登录？」；确认后 `POST /api/v1/auth/logout` 发出（失败也不阻断），`localStorage` 的 `access_token` / `quantcell_jwt_token` 被清空，整页跳转到 `/login`。重跑前置注入脚本即可恢复 | L2 |
| S5 | 访客态（`is_guest=true`）打开本页 | 改密按钮文案变为「访客不可修改」且禁用；用户名等仍渲染。验证后清掉 `is_guest` | L2 |

## 通用设置（/setting/general）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S6 | 打开 `/setting/general` | 分节标题 主题 / 语言 / 分页 / 时区 可见；主题三选项「浅色 / 暗黑 / 自动」可见；「列表页默认显示数量」「默认展示类型」（默认值「列表」）「默认时区」三个选择器可见；右下「保存」按钮处于禁用态（未改动时，悬浮提示「请先修改配置后再保存」） | L1 |
| S6a | 「默认展示类型」切到「卡片」并保存，随后走查 7 个支持双形态的页 | 回测中心 / 策略管理 / 因子分析 / 策略智能体 / 数据管理（标的）/ 模型中心 / 策略研究 全部切到卡片形态（每页只出现一套 DOM，不出现「卡片+表格」并存）；切回「列表」后同样即时生效；两态下行内展开、搜索、筛选、分页均可继续使用；卡片态点卡片只选中不展开（模型中心除外，其卡片下方详情照旧）；刷新后保持所选形态。demo 基准：`docs/design/qc-prototype-demo.html` 的系统设置 → 默认展示类型 | L2 |
| S7 | 把主题从「浅色」切到「暗黑」 | 页面立即变暗并提示「主题已切换」（无需点保存即生效）；此时「保存」变为可点 | L2 |
| S8 | 点「保存」 | `POST /api/v1/config/batch` 返回 200，提示「设置已保存」；随后刷新页面，主题仍为「暗黑」（说明后端已落库）。验证完切回「浅色」再保存一次 | L2 |
| S9 | 改语言下拉为 English | 界面文案立即切英文并提示「语言已切换」；`localStorage.quantcell-language` 变为 `en-US`。切回中文；**注意**语言在点保存前就已持久化到本地（见雷区"语言/主题在保存前就持久化"） | L2 |
| S10 | 点「重置」 | 提示「配置已重置」，控件回到默认值；但 `POST /api/v1/config/batch` **未**发出 → 刷新页面后会回到后端里的旧配置。此条为预期行为（见雷区「重置只改前端，提示却像已生效」），判"提示有、落库无" | L2 |

## 主题体系（全局，面向维护者；详见 docs/theme.md）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| T1 | 按浏览器/系统切换亮暗（浅色/暗黑/自动，见 S6-S8） | 页面底色、卡片、文字、边框、按钮、状态点全站联动变主题；`document.documentElement.style` 上有整套 `--qc-*` 与 `--tw-color-*` 变量（DevTools 查） | L1 |
| T2 | 暗色模式下整页刷新 | 首帧即暗（白色闪屏不可见）：index.html 内联脚本锁 `dark` class + 兜底底色，main.tsx 渲染前注入调色板 | L1 |
| T3 | 品牌改色冒烟（docs/theme.md 路径） | 改 `frontend/src/theme/palettes.ts` 某槽位（如 primary）→ `bun run test -- src/theme/theme.test.ts` 全绿 → 刷新页面，antd 组件/CSS/图表对应色全站生效，业务组件零改动 | L2（按需） |
| T4 | theme.test.ts 守卫回归 | 以下任一情形测试红灯：global.css/index.css 出现颜色字面量；index.html 首帧兜底底色与 palettes.ts 不同步；ACTIVE_THEME_ID 写成未注册主题 | L1 |
| T5 | 主题包导入链（docs/theme.md 路径 B） | `bun scripts/theme-import.mjs export → 改 json → import <id>.json → use <id> → theme.test 全绿 → 构建生效 → use default 回滚`；非法包（缺字段/色值错）在 import 时被逐项拒绝 | L2（按需） |

## 环境变量（/setting/env）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S11 | 打开 `/setting/env` | 标题「环境变量」与「添加」按钮可见；`GET /api/v1/env-vars/` 返回 200；表格表头 键名 / 值 / 描述 / 操作 渲染，无数据时显示「暂无环境变量」 | L1 |
| S12 | 添加一条 `ZZ_TEST_TOKEN`（值随意），保存 | 弹窗标题「添加环境变量」，提交后 `POST /api/v1/env-vars/` 返回 200，提示「环境变量配置已保存」，表格出现 `ZZ_TEST_TOKEN` 行 | L2 |
| S13 | 勾选「是否为敏感」再添加一条 `ZZ_TEST_SECRET` | 表格该行的「值」列显示 `******`（非明文） | L2 |
| S14 | 删除 `ZZ_TEST_TOKEN`（行内「删除」→ 确认「确认删除该环境变量？」） | `DELETE /api/v1/env-vars/ZZ_TEST_TOKEN` 返回 200，提示「删除成功」，行消失。两条 `ZZ_TEST_*` 必须清掉 | L2 |

## 交易所设置（/setting/exchange）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S15 | 打开 `/setting/exchange` | 左栏标题「交易所列表」，列表项含 币安 / OKX / Bybit / Gate.io / KuCoin / Bitget；`GET /api/v1/config/` 返回 200 | L1 |
| S16 | 点任一交易所（如「币安」） | 右栏渲染表单：启用开关、「交易模式」、「计价货币」、「手续费率」、「API Key」、「API Secret」、「代理设置」、「测试连接」按钮。**只断言字段可见，不填任何 key** | L1 |
| S17 | 只改非敏感字段：计价货币 `USDT` → `USDC`，点保存 | `POST /api/v1/config/batch` 返回 200，提示「配置已保存」；刷新页面后该交易所计价货币仍为 `USDC`。验证后改回 `USDT` 再保存 | L2 |
| S18 | 把「交易环境」切到「实盘」 | 弹出确认框标题「实盘交易确认」，正文含"真实资金"字样；点「取消」不产生保存请求 | L2 |
| S19 | 填入真实 key 后点「测试连接」 | 弹出结果面板，逐项显示 网络连接 / 市场数据 / WebSocket / API 认证 的成功或失败标记（文案「测试中...」→ 结果）。**按需**：真实探测交易所、依赖外网与代理，默认跳过并记原因 | 按需（外部依赖） |

## 通知设置（/setting/notifications）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S20 | 打开 `/setting/notifications` | 左栏标题「通知渠道」，渠道项 邮件 / 企业微信 / 飞书 可见；`GET /api/v1/notifications/channels` 返回 200；底部「保存」「重置」可见 | L1 |
| S21 | 点「邮件」渠道 | 右栏渲染「SMTP服务器地址」「SMTP服务器端口」「连接安全性」「用户名」「密码」「发件人邮箱」「收件人邮箱」等字段；顶部有启用开关与「测试」按钮 | L1 |
| S22 | 不改启用状态，直接点「测试」 | 渠道未启用时「测试」按钮为禁用态、点击无请求；启用后按钮可点。注意：`notification_channel_not_enabled`（"请先启用后再测试"）分支只在禁用按钮被绕过时才出现，正常路径看不到 | L2 |
| S23 | 启用某渠道后点保存 | `POST /api/v1/notifications/channels` 返回 200，提示「设置已保存」；刷新页面后该渠道开关仍为启用。验证完恢复原状 | L2 |
| S24 | 配置真实 SMTP 后点「测试」 | `POST /api/v1/notifications/test` 返回成功且提示「测试成功」，收件箱收到测试邮件。**按需**：真实发信 | 按需（外部依赖） |

## 模型设置（/setting/model）— 全站 AI 种子页

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S25 | 打开 `/setting/model` | 左栏标题「模型提供商」，两个分组标题「System 1 · 决策模型」「System 2 · 生成式大模型」可见，组内至少有 OpenRouter / OpenAI / DeepSeek 等厂商项；`GET /api/v1/config/` 返回 200 | L1 |
| S26 | 点左栏任一厂商（如「DeepSeek」） | 右栏渲染「模型类型」标签、「API Key」输入框与「检查可用性」按钮、「API主机」、「模型」列表与「添加」、右下「保存」「重置」。**断言到字段可见为止，不写 key** | L1 |
| S27 | **种子步骤**：选一个 System 2 厂商（如 OpenRouter/DeepSeek）→ 填自己的 key（**不写入本文档**）→ 点左栏「设为默认」 | 提示「默认提供商已设置」；右侧「默认提供商」开关变为开；同分组内其他厂商的按钮回到「设为默认」（组内唯一） | L2 |
| S28 | 接上一步点「保存」 | `POST /api/v1/config/batch` 返回 200，提示「配置已保存」；刷新页面后该厂商仍标「默认」，「API Key」输入框有值（遮罩显示）。此时 `pages/strategy-editor.md` 的 E4 可走"已配置"分支 | L2 |
| S29 | 点「检查可用性」 | `POST /api/v1/ai-models/check` 返回 200 且带回模型列表（弹窗「添加模型」里出现可点选的「可用模型」）。**按需**：会真实请求厂商接口，消耗配额/依赖外网 | 按需（外部依赖） |
| S30 | 「添加模型」/ 删除模型后不点保存，直接刷新页面 | 未保存的增删消失（仅前端 state，见雷区"重置只改前端，提示却像已生效"）；提示「模型已添加 / 模型已删除」不代表已落库 | L2 |

## Agent Token（/setting/agentTokens）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S31 | 打开 `/setting/agentTokens` | 顶部出现「Agent Token」标题与说明（说明文本以"签发 qctk_ 前缀的代理令牌…"开头），右上「签发令牌」按钮可见；表格表头 令牌名称 / 权限范围 / 状态 等渲染；`GET /api/v1/agent/tokens` 返回 200 | L1 |
| S32 | 点「签发令牌」，名称填 `zz_test_agent`，权限选「只读」 | `POST /api/v1/agent/tokens` 返回 200；弹出「签发成功」弹窗，明文令牌以 `qctk_` 开头、附「请立即复制保存令牌，关闭本窗口后将无法再次查看」警示；关闭后表格新增一行，状态为「正常」。**只断言格式与提示，不记录明文值** | L2 |
| S33 | 对该行点「撤销」 | 确认框标题「撤销令牌」；确认后 `DELETE /api/v1/agent/tokens/{id}` 返回 200，提示「已撤销」，该行状态变「已撤销」且不再有「撤销」按钮。`zz_test_agent` 行可留在库里（软删除）或按需清理 | L2 |

## 系统信息（/setting/info）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S34 | 打开 `/setting/info` | 「系统信息」卡片可见，行标签 系统版本 / Python版本 / 构建日期 / 运行时间 / 运行状态 / CPU使用率 / 内存使用率 / 磁盘空间 / 最后更新 全部渲染；`GET /api/v1/system/metrics` 返回 200 | L1 |
| S35 | 观察 CPU/内存/磁盘 数值 | 展示为百分比或"已用 / 总量"形式，且在页面停留期间不出现 `NaN` / `undefined` 文本 | L1 |

## 插件管理（/setting/plugins）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S36 | 打开 `/setting/plugins` | 标题「插件管理」可见，右上「刷新」「安装插件」按钮可见；`GET /api/v1/plugins/` 返回 200；无插件时显示「暂无已安装插件」 | L1 |
| S37 | 点「安装插件」 | 弹窗标题「安装插件」，两个页签「ZIP 上传」与「Git URL」；ZIP 页签显示拖拽区文案「点击或拖拽 ZIP 文件到此处」。**到此为止，不执行安装**（安装=加载执行第三方代码） | L2 |
| S38 | 若已有插件：点「刷新」后切换插件卡片的启用开关 | `POST /api/v1/plugins/{name}/enable` 或 `/disable` 返回 200，状态标记随之变化；出现"需重启后端"的提示条时按提示处理（重启后状态才生效） | L2（有插件时） |
| S39 | 点卡片右上删除 → 确认「确定卸载插件「xxx」？」 | `DELETE /api/v1/plugins/{name}` 返回 200，提示「插件 xxx 已卸载」，卡片消失。**只在自建测试插件上执行** | L2（有测试插件时） |

## 桌面后端（/setting/desktop-backend）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| S40 | 桌面壳（.app）中打开设置页 | 左侧菜单多出「桌面后端」项，点击后 `URL` 为 `/setting/desktop-backend`；页面卡片标题「桌面后端」，两个单选「本机后端（应用自启 sidecar，免登录）」「远程后端（走登录鉴权）」与「保存并切换」按钮可见 | L1（仅 .app） |
| S41 | 浏览器链路直接访问 `/setting/desktop-backend` | 菜单无此入口但 URL 可达；卡片骨架渲染，状态标签显示「未知」/无「当前地址」（浏览器无 Tauri 桥，`invoke` 不可用）。**这不算失败**，如实记录；不要在浏览器上点「保存并切换」（会整页重载走引导） | L1 |

## 设置模块视觉 token 收口（2026-11-20）

| # | 操作 | 预期（可观测信号） | 层级 |
|---|---|---|---|
| V1 | 打开任意设置子页（general / exchange / model / notifications / env / agentTokens / info / plugins / account） | 内容区卡片均为 `qc-card` 规格（10px 圆角、`--qc-border` 边框、分节标题 13px/650）；`grep -rnE "text-gray-|bg-gray-|border-gray-|text-blue-|bg-blue-|text-green-|text-red-|bg-red-|bg-green-" frontend/src/pages/setting/*.tsx` 零命中；无 antd 彩色 `Tag color="blue/green/red"`（LogSettingsUnified 的目录筛选 CheckableTag 与插件 Badge 为 antd 主题 token，已接 qc 调色板，白名单） | L1 |
| V2 | /setting/general 亮色下查看主题选择卡 | 选中项边框为品牌 primary + 同色 20% ring（非 antd 蓝）；未选中边框 `--qc-border`，hover 变 `--qc-border-strong`；勾选圆点用 primary 底 + `--qc-on-primary` 对勾 | L1 |
| V3 | /setting/exchange 点「测试连接」看结果面板（未配 key 时只断言面板结构在「未测试」态） | 面板底色为 success/error 8% tint、文字为 `--qc-success`/`--qc-error`（DevTools 可 `getComputedStyle` 读 token）；逐项标签 网络连接/市场数据/WebSocket/API认证 为 `--qc-text-secondary`，「未测试」为 `--qc-text-quaternary`；`$` 前缀装饰为 `--qc-surface-raised` 底 + `--qc-border` 边（非 gray-*） | L2（真实探测外部依赖，按需） |
| V4 | /setting/model 点「添加」打开弹窗 | 弹窗带 `qc-modal` chrome（14px 圆角/虚线分隔 footer）；确认按钮为主题 primary（非 `bg-gray-900` 黑）；「点击获取 API Key」链接为 `--qc-info`；输入框不加 size/圆角覆盖（global.css 基础层 32px 口径） | L1 |
| V5 | /setting/notifications 启用渠道点「测试」（或只看结果面板出现条件） | 测试结果面板底色/文字同 V3 的 success/error 语义色；渠道启用开关在页头 actions 区 | L2 |
| V6 | /setting/info 点「日志设置」打开抽屉 | 文件列表为 DataTable 规格（表头 10.5px、正文 12px、行高 ~45px、`.qc-pg-bar` 分页含每页条数切换）；类型/大小/日期为语义 chip（info/ok/warn/quiet）；选中汇总条为 info 8% tint；批量删除弹窗带 `qc-modal`、合计金额为 `--qc-error`、需勾选风险确认后「确认删除」才可点 | L1 |
| V7 | /setting/info 页面本体 | 运行状态为语义 chip（运行中=ok）；CPU/内存/磁盘状态点颜色随使用率取 `--qc-success`/`--qc-warning`/`--qc-error`；Descriptions 标签列为 mono 11px 弱灰 kv 口径；系统日志终端区保持恒深色（§6.16 豁免，stone 底保留），但「刷新日志/加载更多」链接为 `--qc-info`、级别徽章为语义 chip | L1 |
| V8 | 暗色模式重复 V1-V7 抽查（theme.test 守卫之外的手工面） | 无深灰文字压深底；tint/chip 在暗色下同样可读（token 自动降级）；控制台无新增未捕获错误 | L1 |

## 历史雷区
- **模型设置保存后会话仍用旧模型**（2026-11-26 已修，定位顺序备忘）：用户在 `/setting/model` 改模型保存后，`/agent` 会话报错仍显示旧模型。排查顺序：①先查 DB——system_config 表 `ai_model.openai-compatible.is_enabled` 等键已即时更新，保存链路（`configApi.updateConfig` → `update_config`）无罪；②真凶在后端 `agent/core/factory.py::get_agent()` 单例——LLM 配置只在进程首次调用读一次，此后永用旧快照。已改为每次调用重读 + 签名比对热替换（详见 agent.md 雷区与 `tests/agent/test_factory_hotswap.py`）。以后遇到「改设置不生效」先分清**存储层已写入、读取方有进程级缓存**，两类问题修法完全不同
- **设置模块视觉收口（2026-11-20，车道 O）**：`src/pages/setting/**` 全量替换 Tailwind 灰阶/语义色为 `--qc-*` token、Card→`qc-card`、页头接 `PageContainer`、日志页 antd Table→`DataTable`、全部弹窗加 `qc-modal`。回归点 V1-V8。注意三处：①交易所页 `$` 前缀装饰在 `Space.Compact` 里手拼内联边框（`--qc-surface-raised`+`--qc-border`），改 Input 组件样式会双线；②LogSettingsUnified 的日志文件表迁移到 DataTable 后，「每页 8/15/25」下拉被分页器自带的条数切换取代，行点击展开详情保留；③系统日志终端（SystemLogs）按 §6.16 豁免保留 stone 深色系，除链接蓝（`--qc-info`）与级别 chip 外 classify 不算违规。
- **LogSettingsPanel 是薄壳不是独立页**：真正的日志设置 DOM 在 `/setting/info` 页「日志设置」按钮拉起的右侧 Drawer 里（内嵌 LogSettingsUnified），没有独立路由；`/setting/*` 路由表里找不到 log 路由属正常。
- **Agent Token 页一次弹出两个 Modal**：签发表单与「签发成功明文展示」是两个 Modal，明文 qctk_ 只在第二个里出现一次，关闭后表格行状态正常但**明文不可再取**（S32 证据采集要在关闭前完成）。
- **主题体系重构（2026-11-20，docs/theme.md）**：全部品牌色收编进 `frontend/src/theme/palettes.ts`（唯一真相源），antd/CSS/canvas 三渠道自动同步；`theme.test.ts` 守卫（global.css 零字面量等）。回归点：亮暗切换全站联动（T1）、暗色首帧不闪白（T2）。遗留待砍：backtest.css 里迁移前的 antd 蓝选中/悬浮底（`rgba(74,108,247,*)`/`rgba(24,144,255,*)`，与橙色品牌现已不一致——** anci 行为保留**，换 `--qc-primary` 属视觉变更需单独拍板）；backtest 进度弹窗的 tint/边框/渐变、`#faad14`、行高亮 `#fff7e6/#ffe7ba` 等五处不等值字面量集中待 palette 补槽位后二次迁移。
- **ModelObsPanel 的 `var(--text-hint, #999)` 假变量（已修）**：该 CSS 变量从未定义，fallback 恒生效，形似语义化实为硬编码；已改接 `--qc-text-tertiary`。写 `var(--x, fallback)` 前先确认变量真的有人定义。
- **启动横幅不再阻塞 + onedir 提速（2026-11-20 改）**：双管齐下。① 桌面引导改为**立即进 UI**，后端未就绪时各页以离线态渲染；后端 `/health` 就绪后自动整页刷新一次（`sessionStorage: qc_boot_reloaded_once` 防循环，手动重启场景靠"刷新后首探即健康则清标志"复用）。② sidecar 从 PyInstaller onefile 改 **onedir**（`binaries/backend/` 整目录 → `.app/Contents/Resources/backend/`，`backend.rs` 直启），免每次自解压 ~250MB；matplotlib 字体缓存钉持久目录。实测（Resource 后端直测）：旧 onefile 每次 45-70s → 新 **热启动 ~2.4s / 装后冷首启 ~15s（一次性）**；GUI 界面 <2s 可见。桌面验证回归点：冷启动 app 界面秒现；后端就绪后数据自动出现（热启 ~10s 内）；预热窗口内只一次自动刷新
- **构建环境雷：外置盘 Spotlight 索引会让打包龟速（2026-11-20）**：`/Volumes/ExtDisk` 索引开启 + 大量构建产物触发 `mds_stores` 全量索引（84% CPU），PyInstaller 从健康 176s 拖到 >60min×5 轮。构建卡死先查 `mdutil -s /Volumes/ExtDisk`，关索引 `mdutil -i off /Volumes/ExtDisk`（无需 sudo）立恢复（实测关后 122s 完成）
- **升级/重装丢历史数据（已根治，桌面 sidecar 全量路径收编）**：打包 sidecar 是 PyInstaller onefile，`__file__` 位于每次启动重新解压的临时目录。此前 K线源数据、策略 .py、已装插件、agent 工作区、因子快照、日志、LLM 录制等凡按模块相对路径写入的，**重启/升级即蒸发**（DB/模型库本就落 app_data_dir 不受影响）。已统一经 `utils/paths.get_persistent_dir` 落 `QUANTCELL_DATA_DIR`（守护测试 `backend/tests/unit/test_persistent_paths.py`）。桌面验证回归点：升级替换 .app 后旧 worker/策略/K线数据应仍在
- **系统信息有硬编码占位值**：`SettingsContext` 的 `defaultSystemInfo` 里 `python_version: '3.10.0'`、`build_date: '2025-01-01'`，而 `systemInfo` 从未被后端数据写入（`_setSystemInfo` 无调用点）。S34 只断言"字段渲染"，别拿 Python 版本/构建日期做环境核对；真实指标只有 `/api/v1/system/metrics` 那几项。
- **"重置"只改前端，提示却像已生效**：通用设置 `resetConfig` 不写后端（S10），模型页「重置」同理；模型页「添加/删除模型」也只改本地 state，未点保存刷新即丢（S30）。看到「配置已重置 / 模型已删除」不等于已落库——排查"设置不生效"时先确认是否漏点保存。
- **语言/主题在保存前就持久化**：切语言即时写 `localStorage.quantcell-language` 并切换 i18n，切主题即时写 `quantcell-ui-theme`（S7/S9）。"没保存却变了"是设计如此，不是状态泄漏。
- **环境变量保存是全量覆盖**：`POST /api/v1/env-vars/` 提交整份数组。两个标签页/窗口同时编辑会互相覆盖，后保存者赢；多人核对时必须先刷新再改。另：编辑敏感变量时值框回填空串（`is_sensitive ? '' : value`），不重填就会被必填校验拦住，表现为"改不动"；`is_sensitive` 开关在编辑态禁用，事后无法改敏感标记。
- **API Key 以明文进 DOM**：交易所页把 key 回填进 `Input.Password` 的 `value`，模型页同理——页面源码/DevTools 里能看到明文，点"眼睛"图标即显示。截图、录屏、DOM dump 都会泄露，证据采集只能用遮罩截图。交易所保存时还把实盘 key 同步写进兼容字段 `exchange.*.api_key` / `api_secret`，同一密钥在配置表里存两份，轮换时要改两处（实际是一处写入两处，读错版本会导致"改了 key 仍报鉴权失败"）。
- **`/setting/desktop-backend` 在 Web 版无菜单但可直达**：组件挂载即 `invoke('get_backend_config')`，浏览器没有 Tauri 桥，页面停在「未知」态（S41）。误以为是"后端挂了"属误判。
- **通知渠道测试会真实发消息**：启用渠道后「测试」不是 dry-run；未启用时按钮禁用，别把它当成"点了没反应"的 bug。
- **插件安装是执行第三方代码**：ZIP/Git 安装后由后端加载运行，L1/L2 只验到安装弹窗；真实安装只在自建测试插件上做（S37/S39）。
