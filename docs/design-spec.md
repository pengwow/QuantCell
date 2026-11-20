# QuantCell 前端设计规范（Design Spec）

> **版本**：v1.0 · 2026-11-20
> **基准**：`docs/design/qc-prototype-demo.html`（静态原型，13 视图，亮/暗双主题，零依赖单文件）——**一切视觉争议以该文件渲染结果为准**。
> **目标**：按本规范可将 demo 的视觉与交互**像素级复刻**进 `frontend/`（React + antd）。规范与 demo 不一致时，改 demo 或改规范，不允许口头例外。
> **配套**：品牌配色管理见 `docs/theme.md`；本文的 token 表是其 palette 槽位的超集，迁移映射见 §10。

---

## 0. 基准与复现

```bash
# 本地查看基准 demo（任意静态服务器均可）
cd docs/design && python3 -m http.server 8800
# → http://localhost:8800/qc-prototype-demo.html
```

demo 内建 hash 路由（`#home` `#strategy` `#strategy-editor` `#backtest-config` …），可直接深链到任意视图；`localStorage['qc-proto-theme']` 记忆亮暗。

**规范漂移门禁**：本文 token 表 / 视图路由 / 关键几何值必须与 demo 逐值一致，改动任一侧后执行

```bash
node docs/design/check-spec.mjs   # 169 项断言，退出码非 0 即漂移
```

**像素级验收方式**：同一视口（≥1280px 宽）下，产品页与 demo 对应视图截图叠加 diff；色值、字号、行高、内边距、圆角、间距的允许误差为 0（抗锯齿除外）。

---

## 1. 设计原则

1. **紧凑优先**：13px 正文、32px 控件、10-14px 卡片内边距。密度是量化工具的专业感来源，不做营销页式留白。
2. **等宽数字**：一切数值、代码、时间戳、ID 用 mono 栈 + `tabular-nums`。非数值文本用系统 UI 栈。
3. **单强调色**：品牌橙只用于「主操作 / 选中态 / 当前页 / 品牌标识」；语义信息（涨跌、成败、警示）用语义色，不用品牌色。
4. **alpha 分层**：文本/边框/悬浮底用同一基色的 alpha 阶梯（而非独立灰阶），保证亮暗切换时层级关系不变。
5. **可解释性标注**：数据区块标注来源与口径（如「纯前端」「需 GET /agent/memory」「最新在前 · 滚动加载更早」），不做虚假承诺。

---

## 2. Design Tokens

### 2.1 全量槽位表

| 槽位 | 亮色 | 暗色 | 语义 |
|---|---|---|---|
| `--canvas` | `#f2f3f5` | `#0b0c0e` | 画布（最底层背景） |
| `--bg` | `#ffffff` | `#17191c` | 页面/面板底（侧栏、Header） |
| `--bgc` | `#ffffff` | `#1d1f23` | 卡片/气泡底（content） |
| `--bge` | `#f5f6f8` | `#232529` | 内嵌面板/浮层/表头底（elevated） |
| `--fg` | `#141414` | `#fafaf9` | 主文本 |
| `--fg-2` | `rgba(20,20,20,.72)` | `rgba(250,250,249,.68)` | 次级文本 |
| `--fg-3` | `rgba(20,20,20,.52)` | `rgba(250,250,249,.48)` | 三级文本（表头、标签） |
| `--fg-4` | `rgba(20,20,20,.38)` | `rgba(250,250,249,.36)` | 弱文本（提示、占位、脚注） |
| `--bd` | `rgba(20,20,20,.13)` | `rgba(250,250,249,.12)` | 常规边框/分割线 |
| `--bd-2` | `rgba(20,20,20,.21)` | `rgba(250,250,249,.22)` | 强调边框（hover、徽章描边） |
| `--primary` | `#ea580c` | `#f97316` | 品牌橙（唯一强调色） |
| `--info` | `#0969da` | `#478be6` | 信息/链接/进行中 |
| `--up` | `#1a7f37` | `#57ab5a` | 涨/成功 |
| `--down` | `#d1242f` | `#e5534b` | 跌/失败/危险 |
| `--warn` | `#b45309` | `#daaa3f` | 警示（亮档加深保对比度） |
| `--on-primary` | `#ffffff` | `#18100a` | 主色按钮上的文字 |
| `--avatar-user-bg` | `#9aa2ad` | `rgba(250,250,249,.48)` | 用户头像底 |
| `--avatar-user-fg` | `#ffffff` | `#17191c` | 用户头像字 |
| `--user-bg` | `var(--info)` | `color-mix(in srgb, var(--info) 88%, black)` | 用户消息气泡底 |
| `--user-fg` | `#ffffff` | `#ffffff` | 用户消息气泡字 |
| `--card` | `var(--bgc)` | `var(--bgc)` | 卡片别名（弹窗等复用） |
| `--card-shadow` | `0 1px 2px rgba(16,20,26,.04)` | `0 1px 3px rgba(0,0,0,.22)` | 卡片阴影 |
| `--bubble-shadow` | `0 1px 4px rgba(16,20,26,.06)` | `0 2px 8px rgba(0,0,0,.15)` | 气泡阴影 |
| `--scroll-thumb` | `rgba(20,20,20,.18)` | `rgba(250,250,249,.14)` | 滚动条 |
| `--glow-1` | `rgba(234,88,12,.05)` | `rgba(249,115,22,.07)` | 画布辉光（橙） |
| `--glow-2` | `rgba(9,105,218,.04)` | `rgba(71,139,230,.05)` | 画布辉光（蓝） |

### 2.2 可直接粘贴的 token 块（demo 原文，`frontend/src/global.css` 迁移时同构使用）

```css
:root, html[data-theme='light'] {
  color-scheme: light;
  --canvas: #f2f3f5;
  --bg: #ffffff;
  --bgc: #ffffff;
  --bge: #f5f6f8;
  --fg: #141414;
  --fg-2: rgba(20,20,20,.72);
  --fg-3: rgba(20,20,20,.52);
  --fg-4: rgba(20,20,20,.38);
  --bd: rgba(20,20,20,.13);
  --bd-2: rgba(20,20,20,.21);
  --primary: #ea580c;
  --info: #0969da;
  --up: #1a7f37;
  --warn: #b45309;
  --down: #d1242f;
  --on-primary: #ffffff;
  --avatar-user-bg: #9aa2ad;
  --avatar-user-fg: #ffffff;
  --user-bg: var(--info);
  --user-fg: #ffffff;
  --card: var(--bgc);
  --bubble-shadow: 0 1px 4px rgba(16,20,26,.06);
  --card-shadow: 0 1px 2px rgba(16,20,26,.04);
  --scroll-thumb: rgba(20,20,20,.18);
  --glow-1: rgba(234,88,12,.05);
  --glow-2: rgba(9,105,218,.04);
}
html[data-theme='dark'] {
  color-scheme: dark;
  --canvas: #0b0c0e;
  --bg: #17191c;
  --bgc: #1d1f23;
  --bge: #232529;
  --fg: #fafaf9;
  --fg-2: rgba(250,250,249,.68);
  --fg-3: rgba(250,250,249,.48);
  --fg-4: rgba(250,250,249,.36);
  --bd: rgba(250,250,249,.12);
  --bd-2: rgba(250,250,249,.22);
  --primary: #f97316;
  --info: #478be6;
  --up: #57ab5a;
  --warn: #daaa3f;
  --down: #e5534b;
  --on-primary: #18100a;
  --avatar-user-bg: rgba(250,250,249,.48);
  --avatar-user-fg: #17191c;
  --user-bg: color-mix(in srgb, var(--info) 88%, black);
  --user-fg: #ffffff;
  --card: var(--bgc);
  --bubble-shadow: 0 2px 8px rgba(0,0,0,.15);
  --card-shadow: 0 1px 3px rgba(0,0,0,.22);
  --scroll-thumb: rgba(250,250,249,.14);
  --glow-1: rgba(249,115,22,.07);
  --glow-2: rgba(71,139,230,.05);
}
```

### 2.3 tint 公式（语义徽章/选中态唯一允许的着色方式）

| 用途 | 公式 |
|---|---|
| 徽章/chip 底 | `color-mix(in srgb, <语义色> 8%, transparent)`（信息/成功/失败类）或 `10%`（强调） |
| 徽章/chip 边 | `color-mix(in srgb, <语义色> 40%, transparent)` |
| 导航选中底 | `color-mix(in srgb, var(--primary) 9%, transparent)` |
| 表格选中行 | `color-mix(in srgb, var(--primary) 5%, transparent)` |
| 表格 hover 行 | `color-mix(in srgb, var(--fg) 3%, transparent)` |
| 悬浮（按钮/图标） | `color-mix(in srgb, var(--fg) 5%, transparent)` |
| 弹窗遮罩 | `color-mix(in srgb, #000 44%, transparent)` + `backdrop-filter: blur(2px)` |

禁止：第四级灰阶、渐变按钮、纯色填充的状态块（除主色实心按钮与进度条外）。

---

## 3. 排印

### 3.1 字体栈

```css
/* UI 文本 */
font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", "Microsoft YaHei", sans-serif;
/* 数值 / 代码 / 时间戳 / ID（.mono 类） */
font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
font-variant-numeric: tabular-nums;
```

### 3.2 字号阶梯（全站只许以下档位）

| 字号 | 用途 |
|---|---|
| 9px | 角标、极小图标字 |
| 9.5px | mono 微标注（步进时间、事件行） |
| 10px | chip 文字、card-foot code、分组标题字母距前身 |
| 10.5px | 表头（th）、page-sub、空态说明 |
| 11px | 次级说明、modal 字段 label（mono） |
| 11.5px | toast、小按钮（mini-btn）、列表辅助行 |
| 12px | 按钮、表格正文（td）、表单输入 |
| 12.5px | Tab、面板正文、气泡正文（聊天流） |
| 13px | **正文基准**、nav-item、page-title 之外的标题、卡片正文 |
| 14.5px | modal 标题 |
| 15px | 视图内大标题（h-title 类） |
| 16px | page-title（页面主标题） |
| 22px | KPI 大数字（mono 650） |

### 3.3 字重与行高

- 常规 400；强调/标题 550-650；数字大标 650。
- 正文行高 1.6-1.7；表格/列表 1.4；标题 1.3。
- 全站 `letter-spacing: .01em` 用于大标题与 KPI；`10.5px` 分组标题 `letter-spacing: .16em` 全大写。

---

## 4. 空间与几何

| 项 | 值 |
|---|---|
| 间距节奏 | 2px 基元；常用 4 / 8 / 10 / 12 / 14 / 18 / 24 |
| 卡片内边距 | `12px 14px`（通用卡）、modal body `15px 18px` |
| 卡片间距 | 纵向 10-12px |
| 圆角 | 卡片 10px · 侧栏 12px · 气泡 12px · modal 14px · 输入框/按钮 8px · 页码钮 6px · chip 20px（全圆）· 徽章 4-6px |
| 控件高度 | 主按钮 30px · mini 按钮 24px · 输入/select 32px · 页码钮 28px · segmented 内钮 24px · Header 52px |
| 阴影 | 仅两级：`--card-shadow`（极轻）与 modal/toast 浮层（`0 10px 26px rgba(0,0,0,.2)` / `0 24px 60px rgba(0,0,0,.28)`）；亮色靠边框分层，暗色靠抬升表面 |
| 滚动条 | 宽 8px、thumb `--scroll-thumb`、track 透明 |

---

## 5. 布局骨架

```
┌────────────────────────────────────────────────────────────────┐
│ Header 52px：logo+面包屑 ｜ 主题切换 铃铛 设置 头像            │
├──────────┬─────────────────────────────────────────────────────┤
│ Sider    │ main（padding: 4px 4px 18px）                        │
│ 216px    │  ┌ page-head（标题16 + 副标11 mono + 右侧操作）     │
│ （折叠    │  ├ 卡片/表格/图表…                                   │
│  64px）  │  └ …                                                │
│ 分组菜单  │                                                      │
│ 版本+状态 │                                                      │
└──────────┴─────────────────────────────────────────────────────┘
```

- **Header**：`height: 52px; flex: 0 0 52px; padding: 0 16px; border-bottom: 1px solid var(--bd); background: var(--bg)`。左：logo（20px 渐变方块 + 「QuantCell」14px/700，左组 gap 10px）+ 面包屑 `crumb`（`fg-2`，13px，`/` 分隔）。右：主题切换胶囊（30px 高、15px 圆角、`bge` 底、图标 16px 主色）、图标钮（30×30、6px 圆角）、铃铛带主色角标。
- **Sider**：`flex: 0 0 216px`，`background: var(--bg)`，`border: 1px solid var(--bd)`，`border-radius: 12px`（内嵌画布中）。折叠态 64px（`body.sider-min`），仅图标居中。
- **main**：`flex: 1; overflow-y: auto; padding: 4px 4px 18px`。
- **page-head**：`display:flex; align-items:flex-end; justify-content:space-between; margin: 2px 2px 14px`。左：`page-title` 16px/650 + `page-sub` 11px `fg-4`（mono 数据口径行）；右：`page-actions`（按钮组，gap 8px）。
- **视图切换**：`.view { display:none } .view.active { display:block; animation: viewIn .18s ease-out }`（`translateY(4px)` 淡入）。
- 画布背景：`--canvas` + 双 radial-gradient 辉光（`--glow-1/2`，1100×420 顶部 + 900×380 右下）。

---

## 6. 组件规范

> 每个组件给出 demo 类名与关键 CSS 值；迁移到 React 时组件名可改，**渲染尺寸/色值/状态必须一致**。

### 6.1 按钮 `.btn`

- 基础：`height:30px; padding:0 12px; border-radius:8px; border:1px solid var(--bd); background:var(--bgc); color:var(--fg-2); font-size:12px;` hover：`color:var(--fg); border-color:var(--bd-2)`。
- 主色 `.btn.primary`：`background:var(--primary); border-color:transparent; color:var(--on-primary); font-weight:550;` hover：`background:color-mix(in srgb, var(--primary) 88%, black)`。
- 危险 `.btn.danger`：`color:var(--down); border-color:color-mix(in srgb, var(--down) 42%, transparent); background:color-mix(in srgb, var(--down) 7%, transparent);` hover 底 12%。
- 小号 `.mini-btn`：`height:24px; padding:0 9px; border-radius:6px; font-size:11px;` 主色变体同 tint 逻辑（实心 primary）。
- 图标按钮 `.icon-btn`：30×30、透明底、`border-radius:6px`、hover `fg 5%` 底；必须带 `aria-label`。

### 6.2 徽章 / Chip `.chip` `.tag-run` `.mode-tag` `.count-chip`

- `.chip`：`font-size:10px; line-height:1; padding:3px 7px; border-radius:20px; border:1px solid transparent;` 语义变体 = tint 公式（§2.3）：`ok/up → --up`、`down → --down`、`info → --info`、`warn → --warn`。
- 进行中 chip 内嵌 `.pdot`（5px 圆点，`animation: pulse 2.2s`）。
- `.mode-tag`（实盘/模拟盘）：`9.5px; padding:3px 6px; border:1px solid var(--bd-2); background:var(--bge); color:var(--fg-3)`。
- `.count-chip`（计数徽章）：mono 10px、全圆、`bd-2` 边、`bge` 底。

### 6.3 卡片 `.card`

- `background:var(--bgc); border:1px solid var(--bd); border-radius:10px; padding:12px 14px; box-shadow:var(--card-shadow);`
- 头部 `.card-head`：`display:flex; gap:9px; margin-bottom:8px;` 标题 13px/650；序号徽章 `.card-idx`（mono 10px、主色 40% 边）；右侧 `.head-right { margin-left:auto }`。
- 脚注 `.card-foot`：`margin-top:10px; padding-top:8px; border-top:1px dashed fg 10%; font-size:10.5px; color:var(--fg-4);` 内嵌 `code` 用 mono 10px `fg-3`。

### 6.4 KPI 卡

- 结构：label（11px `fg-4`）→ `.kpi-num`（mono 22px/650、涨跌色）→ `.kpi-sub`（10.5px `fg-4`）。
- 4 卡等宽网格，gap 10px。

### 6.5 表格 `.bt`

- `table { width:100%; border-collapse:collapse; min-width:760px }`（外层横向滚动）。
- `th`：10.5px / 500 / `fg-4` / `padding:9px 12px` / `background:var(--bge)` / 底边 `--bd`。
- `td`：12px / `padding:10px 12px` / 底边 `--bd` / `vertical-align:middle` / `white-space:nowrap`。
- 行 hover：`fg 3%` 底；选中行 `.on`：`primary 5%` 底 + 左侧 2px 主色条（表格行以 tint 表达即可）。
- 策略名/标的等标识列用 mono。

### 6.6 工具栏 `.toolbar`

- `display:flex; gap:8px; margin:0 0 12px;` 搜索框 `.tsearch`：`height:32px; width:min(240px,58vw); border-radius:8px;` 占位 `fg-4`、mono 提示。
- 状态过滤 chips：与 `.chip` 同款，选中态主色 tint；右侧 `.r-count`（11px `fg-4`）「显示 x-y / 共 z」。
- 过滤与分页联动：过滤后页码归 1。

### 6.7 分页 `.pg-bar`

- 条：`display:flex; align-items:center; gap:10px; margin-top:12px; padding-top:9px; border-top:1px solid var(--bd);`
- 左：「共 N 条 · 每页 [10|20|50 ▾]」；右：`‹ 1 2 3 … N ›` + 「跳至 [__] 页」。
- 页码钮 `.pg-btn`：`min-width:28px; height:28px; padding:0 7px; border-radius:6px; border:1px solid var(--bd);` 当前页 `.on`：主色字 + `primary 45%` 边 + `primary 10%` 底；禁用 0.35 透明度；省略号非交互。
- 页码算法：首尾常显 + 当前页 ±1 + 其余 `…`（4/9 → `1 … 3 4 5 … 9`）。
- `<860px` 压缩为「‹ 2/7 ›」。

### 6.8 Tab `.tabs` / `.tab`

- 底边 1px `--bd` 容器；`.tab`：`padding:9px 11px; font-size:12.5px; color:var(--fg-3); border-bottom:2px solid transparent;`
- 选中：主色字 + 主色 2px 底边 + 550 字重；hover `fg-2`。

### 6.9 Segmented `.seg`

- 容器：`inline-flex; border:1px solid var(--bd); border-radius:8px; padding:2px; gap:2px; background:var(--bgc);`
- 内钮：`height:24px; padding:0 12px; border-radius:6px; font-size:12px;` 选中：`primary 12%` 底 + 主色字 600。

### 6.10 输入 / Select / Textarea

- 高 32px、`border-radius:8px`、`border:1px solid var(--bd)`、`background:var(--bgc)`、字号 12-12.5px、`padding:0 11px`。
- 字段 label：mono 11px `fg-4` + `letter-spacing:.02em`。
- focus-visible：`outline:2px solid var(--info); outline-offset:2px`（全局统一，不另设边框变色）。

### 6.11 弹窗 `.modal`

- 遮罩：`fixed inset:0; background:color-mix(#000 44%); backdrop-filter:blur(2px); z-index:90`。
- 面板：`width:min(560px,94vw); max-height:86vh; border-radius:14px; border:1px solid var(--bd); background:var(--card); box-shadow:0 24px 60px rgba(0,0,0,.28); animation:modalIn .22s cubic-bezier(.2,.9,.3,1.2)`。
- 结构：head（15/18px padding，标题 14.5/700，✕ 26×26）→ body（15/18px，gap 11px，可滚动）→ foot（右对齐按钮组）。
- 打开时聚焦首个控件；ESC / 点遮罩 / ✕ 关闭。

### 6.12 Toast `.toast`

- 容器：`fixed; right:18px; bottom:18px; z-index:99; flex-column; gap:8px; pointer-events:none`。
- 条目：`background:var(--card); border:1px solid var(--bd); border-left:3px solid var(--primary); border-radius:9px; box-shadow:0 10px 26px rgba(0,0,0,.2); padding:9px 14px; font-family:mono; font-size:11.5px; color:var(--fg-2); max-width:340px;` 入场 `toastIn .2s`；2.5s 自动消失；最多叠 3 条。

### 6.13 空态 / 骨架

- 空态 `.empty`：`flex-column; align-items:center; gap:7px; padding:58px 20px;` 图标块 46×46（13px 圆角、`bge` 底、`bd` 边、`fg-4` 图标 20px）+ 主文案 13px `fg-2` + 说明 10.5px `fg-4` + 操作按钮。
- 骨架 `.skel`：`bge` 底、`border-radius:6px`、高度按行内容（12/20/32px），不做 shimmer 动画。

### 6.14 聊天流 DNA（/agent、策略智能体共用）

- 消息行：avatar 32×32（6px 圆角，AI 用 `info` 底白字，用户用 `avatar-user-bg`）→ 列（head：角色 550 + 时间 12px `fg-3` + 标签 chip）→ 气泡（`bgc` 底、12px 圆角、`padding:11px 15px`、`bubble-shadow`、13px/1.65）。
- 用户气泡：`user-bg` 底、`user-fg` 字、右对齐。
- 迭代步进器 `.iter-card`：`primary 40%` 虚线边、`primary 4%` 底、10px 圆角；步点 20px 圆（主色实心，done 态 55% 混合），rail 连接线 2px `primary 45%`；右侧计数 mono 10px。
- 工具链 `.chain-node`：`up 40%` 边 + `up 8%` 底 + 10px 圆角；头行 12px（caret + 工具名 mono 600 + 参数 mono 10.5 `fg-4` + 耗时 + 成功 chip）；body `pre` mono 11px `bg` 底。
- 思考折叠 `.collapse-toggle`：12px `fg-3`，hover `info`。

### 6.15 侧栏导航 `.nav-item`

- 基础：`height auto; padding:7px 10px 7px 13px; line-height:19px（总高 33px）; border-radius:8px; font-size:13px; color:var(--fg-2); gap:9px;` 图标 16px `fg-3`。
- hover：`fg 5%` 底 + `fg` 字。
- 选中 `.on`：`primary 9%` 底 + 主色字 550 + 图标主色 + **左侧 3px 主色竖条**（`::before`，top/bottom 22%，2px 圆角）。
- 分组标题 `.nav-group-t`：`padding:13px 13px 5px; font-size:10.5px; letter-spacing:.16em; color:var(--fg-4)`。
- 底部状态行 `.sider-foot`：1px 顶边、8/10px padding、8px 状态点（`up` 实心 + 16% 光环）、版本号 mono 10.5 `fg-4`。

### 6.16 代码编辑器 chrome（策略编辑器）

- **恒深色，不随主题**：编辑器底 `#1e1e1e`，行号列 `#252526`/`#858585`，代码 12.5px mono、行高 1.55。
- Dark+ 语义色：关键字 `#c586c0`/`#569cd6`、字符串 `#ce9178`、注释 `#6a9955` 斜体、数字 `#b5cea8`、函数 `#dcdcaa`、类名 `#4ec9b0`。
- 状态栏：`#007acc` 底或 `bge` 底 + mono 10.5px（`Python · UTF-8 · Ln 12, Col 4 · Spaces: 4`）。
- 产品实现直接用 Monaco（`@monaco-editor/react`），主题名自建 `quantcell-dark`，token 色按上表。

### 6.17 状态点 / 指示灯行

- `.dot`：8px 圆；ok = `up` 实心 + `0 0 0 3px up 16%` 光环；warn = `warn` 同理；off = `bge` 底 + `bd-2` 1.5px 边。
- 系统状态行：左侧点 + 名称 12px `fg-2` + 右侧 mono 值 10.5px `fg-4`；行距 10px。

---

## 7. 交互与路由

- **视图路由**：hash 直达（`#strategy` 等），首载解析 + `hashchange` 监听；切换写回 `history.replaceState`。
- **二级页**（策略编辑器/回测配置/研究详情）：不占侧栏项，**高亮父菜单**（编辑器→策略管理、配置→回测中心、详情→策略研究）。
- **返回**：二级页有「← 返回」，回来源视图（lastView 记忆）；列表内返回用 `data-back`。
- **预填**：入口携带上下文——行「去回测」带该行策略名、「一键转回测」带研究标题、编辑器「去回测」带当前策略。
- **列表交互**：行点击选中并联动详情块；工具栏过滤即时生效并重置分页；页大小变更页码归 1；跳页钳制边界。
- **提交类动作**：按钮点击 → toast 确认 + 列表插入「运行中」行（进度条）→ 完成态切换 + 行高亮一次。
- **危险动作**（停止 Worker、清空会话）：确认弹窗，danger 按钮。

## 8. 动效

| 场景 | 参数 |
|---|---|
| 主题切换 | 颜色类属性 `160ms ease-out`（background-color/border-color/color/box-shadow），布局属性不参与过渡 |
| 视图切换 | `viewIn .18s ease-out`（透明度 + 4px 上移） |
| 弹窗 | `modalIn .22s cubic-bezier(.2,.9,.3,1.2)`（上移 14px + scale .98 → 1） |
| Toast | `toastIn .2s` 同上缓动；离场 240ms 淡出下移 |
| 进行中脉冲 | `pulse 2.2s ease-in-out infinite`（opacity 1 → .35） |
| 侧栏折叠 | `flex-basis .18s ease-out` |
| 降级 | `@media (prefers-reduced-motion: reduce)` 关闭全部动画 |

## 9. 无障碍

- 图标按钮必须 `aria-label`；主题切换 `aria-pressed`；当前导航项 `aria-current="page"`。
- 焦点环统一：`:focus-visible { outline: 2px solid var(--info); outline-offset: 2px }`。
- 对比度：正文/语义文字在各自底色上 ≥ 4.5:1（亮档 `--warn` 用 `#b45309` 而非 `#daaa3f` 即为此约束）；纯装饰图形不受限。
- 键盘：列表行、卡片可选中项支持 Enter/Space；弹窗焦点捕获 + ESC 关闭。
- 状态不只用颜色表达：进行中 = 点 + 文字、成功/失败 = chip 文字（颜色为辅助）。

## 10. 与 QuantCell 主题系统接入（迁移映射）

### 10.1 palette 槽位映射（`frontend/src/theme/builtin.ts`）

| 本规范 token | 现有 palette 字段 | 动作 |
|---|---|---|
| `--canvas` | （无） | **新增** `canvas` |
| `--bg` | `background` | 值已一致（`#ffffff`/`#17191c`），保留 |
| `--bgc` | `surface` | 暗色改 `#141414 → #1d1f23`；亮色不变 |
| `--bge` | `surfaceRaised` | 改 `#ffffff → #f5f6f8`（亮）/ `#1f1f1f → #232529`（暗） |
| `--fg` | `foreground` | 一致，保留 |
| `--fg-2` | `textSecondary` | 改 `#666 → rgba(20,20,20,.72)` / `#e5e7eb → rgba(250,250,249,.68)` |
| `--fg-3` | `textTertiary` | 改 `#999 → rgba(20,20,20,.52)` / `#9ca3af → rgba(250,250,249,.48)` |
| `--fg-4` | （无） | **新增** `textQuaternary` |
| `--bd` | `border` | 改 `#d1d5db → rgba(20,20,20,.13)` / `#374151 → rgba(250,250,249,.12)` |
| `--bd-2` | （无） | **新增** `borderStrong`；`borderSubtle` 保留供图表轴 |
| `--primary` | `primary` | 一致 |
| `--info/--up/--down` | `info/success/error` | 一致 |
| `--warn` | `warning` | 亮色改 `#eac54f → #b45309`（可读性；暗色 `#daaa3f` 不变） |
| `--on-primary` | （无） | **新增** `onPrimary` |
| `--user-bg/--user-fg` | （无） | **新增** `userBubbleBg`/`userBubbleFg`（暗色用 color-mix 派生） |
| `--card-shadow`/`--bubble-shadow` | （无） | **新增** `shadowCard`/`shadowBubble` |
| `--glow-1/2` | （无） | 可选新增 `canvasGlowA/B`（不用辉光的页面可忽略） |

**注意**：这次是「向 demo 对齐」的有意视觉变更（文本/边框从实色灰阶改为 alpha 阶梯、warning 加深），不再是此前主题重构的「像素守恒」口径。迁移时同步更新 `fields.ts` 契约、`theme.test.ts` 守卫、`getCssVars`/`paletteToTradingToken` 映射与 `docs/theme.md` 槽位表。

### 10.2 antd token 映射（`paletteToTradingToken` / ConfigProvider）

| antd token | 取本规范 |
|---|---|
| `colorBgLayout` | `--canvas` |
| `colorBgContainer` | `--bgc` |
| `colorBgElevated` | `--bge` |
| `colorText` | `--fg` |
| `colorTextSecondary` | `--fg-2` |
| `colorTextTertiary` | `--fg-3` |
| `colorTextQuaternary` | `--fg-4` |
| `colorBorder` / `colorBorderSecondary` | `--bd` / `--bd` |
| `colorPrimary` | `--primary` |
| `colorSuccess` / `colorWarning` / `colorError` / `colorInfo` | `--up` / `--warn` / `--down` / `--info` |
| `borderRadius` / `borderRadiusLG` | 8 / 10 |
| `controlHeight` | 32（紧凑 24/30） |
| `fontSize` | 13 |

antd 组件的 hover/active 派生色继续交给 algorithm（`colorPrimaryHover` 等），不写死。

### 10.3 CSS 变量通道

现有 `--qc-*` 变量集扩展为上表全量（`--qc-canvas`、`--qc-text-quaternary`、`--qc-border-strong`、`--qc-on-primary` 等）；demo 中的 `--fg-2` 等在迁移时映射为 `--qc-text-secondary` 等规范名（demo 的短名仅原型内部使用）。

---

## 11. 迁移顺序建议（产品落地）

1. **Token 层**：`builtin.ts` 补新增槽位 + 改值 → `fields.ts` 契约 → `theme.test.ts` 同步 → `getCssVars` 扩展。
2. **antd 桥**：按 §10.2 更新 `paletteToTradingToken` / ConfigProvider；全局 `fontSize:13`、`controlHeight:32`、`borderRadius:8`。
3. **布局骨架**：`ConsoleLayout`（Header 52 / Sider 216·64 / main padding / 视图切换动画）→ 侧栏 nav-item 三态。
4. **基础组件**：Button/Chip/Card/KPI/Tabs/Seg/Input → 表格 `.bt` + 工具栏 + 分页（新组件 `DataTable` 封装 antd Table：`size="small"`、分页条自绘、toolbar 插槽）。
5. **列表页逐页替换**：策略管理 → 回测中心 → 因子/研究/数据/模型（顺序按使用频率）。
6. **二级页**：策略编辑器（Monaco 主题 + 双 Tab）→ 回测配置（表单栅格）→ 研究详情。
7. **弹窗/Toast 统一**：antd Modal 定制为 §6.11 尺寸/圆角/动效；全局 toast 用 antd message 定制或自建。
8. **图表**：ECharts/klinecharts 的 axis/split 取 `--bd`、涨跌取 `--up/--down`、主线取 `--info`（与现有 `chart*` token 对齐，替换成新值即可）。

每步完成后跑：`bun run test`、`bunx tsc -b`、`bunx eslint src`、`node docs/testing/check-coverage.mjs`，并按 `docs/testing/README.md` 落 L1 验证。

## 12. 像素级验收清单

| # | 检查项 | 判定 |
|---|---|---|
| V1 | token 全量 26 槽位在 `getCssVars` 输出且亮暗两套与 §2.1 逐值相等 | 脚本断言 |
| V2 | 同视口截图 diff：Header 高度 52、Sider 216/64、卡片 padding 12/14、圆角 10、正文字号 13 | 目测 + devtools |
| V3 | 表格：th 10.5/`fg-4`/`bge` 底，td 12px、行高 32±2、hover/选中 tint 公式 | devtools |
| V4 | 分页：28px 钮、当前页 tint、省略号算法、<860px 压缩形态 | 交互测试 |
| V5 | 按钮三变体高度/圆角/hover 色 | devtools |
| V6 | 弹窗 560px/14px 圆角/遮罩 44% + blur/入场缓动 | 目测 |
| V7 | 亮暗切换：全站颜色类属性 160ms 过渡、无布局跳动、首帧不闪 | 录屏 |
| V8 | mono 数字全部 `tabular-nums`（抽查 KPI/表格/时间戳） | devtools |
| V9 | 对比度：`--warn` 亮档在 `bgc` 上 ≥4.5:1 | 计算器 |
| V10 | 与 demo 同视图并排比对无「可感知」差异（间距/字号/色相） | 并排截图 |

---

## 附录 A：demo 视图索引（基准对照）

| hash | 视图 | 迁移优先级 |
|---|---|---|
| `#home` | 首页看板（KPI/任务/状态/最近） | P1 |
| `#strategy` | 策略管理（表格+工具栏+分页+详情） | P1 |
| `#strategy-editor` | 策略编辑器（Monaco/预览 Tab） | P2 |
| `#backtest` | 回测中心（任务表+详情+曲线） | P1 |
| `#backtest-config` | 回测配置（表单） | P2 |
| `#sagent` | 策略智能体（worker 卡+决策流） | P2 |
| `#agent` | 智能体工作台（聊天+迭代足迹+Dream） | P3 |
| `#charts` | 行情图表（蜡烛图+MA+成交量） | P2 |
| `#factors` | 因子分析（因子表+IC 柱） | P3 |
| `#research` | 策略研究（研究卡+转回测） | P3 |
| `#research-detail` | 研究详情（结论+产物+Top5） | P3 |
| `#data` | 数据管理（数据源+同步+存储） | P3 |
| `#models` | 模型中心（模型卡+曲线+shadow 对照） | P3 |

## 附录 B：demo 内已知非规范实现（迁移时按规范实现，不照抄）

- 代码编辑器为手绘高亮（产品用 Monaco + 自建主题）。
- 蜡烛图/权益曲线为内联 SVG 静态点集（产品用 klinecharts/ECharts）。
- 分页/过滤为客户端内存实现（产品走服务端分页 + `useGlobalPageSize`）。
- hash 路由为原型路由（产品用 react-router，保留同样的父菜单高亮与返回栈语义）。
