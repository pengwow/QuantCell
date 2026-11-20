# 主题系统（品牌配色管理）

> 面向项目维护者。终端用户不感知本机制；系统默认跟随浏览器/系统亮暗偏好（既有 useBrowserTheme / 设置页外观配置不变）。

## 一句话

`frontend/src/theme/palettes.ts` 是全项目品牌色**唯一真相源**：一处修改，antd 组件、Tailwind 工具类、纯 CSS、canvas 图表全部自动同步。更换品牌配色**不需要改动任何业务组件代码**。

## 架构：三层映射（参考 VS Code / 主流编辑器主题的实现逻辑）

```
┌─────────────────────────────────────────────────────────────┐
│ L1 语义调色板（唯一真相源）                                   │
│    src/theme/palettes.ts    THEMES{ default: {light, dark} } │
│    src/theme/config.ts      ACTIVE_THEME_ID（一键切换开关）   │
│    src/theme/types.ts       ThemePalette 类型契约            │
└──────────────┬──────────────────┬───────────────┬───────────┘
               │ applyThemeVars() │ paletteToTradingToken()
               ▼                  ▼               ▼
┌──────────────────┐ ┌────────────────────┐ ┌──────────────────────┐
│ ② CSS 变量渠道    │ │ ② antd token 渠道   │ │ ③ 静态快照渠道        │
│ --qc-*（规范名）  │ │ ConfigProvider      │ │ utils/colors.ts      │
│ --tw-color-*别名 │ │ theme.token         │ │ QUANT_COLORS 非React  │
│ → 纯 CSS/工具类  │ │ → 全部 antd 组件    │ │ → canvas/klinecharts │
└──────────────────┘ └────────────────────┘ └──────────────────────┘
```

- `src/theme/index.ts`：三个渠道的映射函数（`getCssVars` / `paletteToTradingToken` / `getPalette`）。
- 模式开关仍是 `<html>.dark` class（index.html 首帧脚本 / useBrowserTheme / 设置页共同维护）；
  App.tsx 的 MutationObserver 检测到 class 变化时调用 `applyThemeVars()` 重写全部 CSS 变量，
  main.tsx 在 React 渲染前做首次注入；index.html 内联 `<style>` 仅兜底首帧页面底色防闪屏。

## 标准语义槽位（ThemePalette）

| 分组 | 槽位 | 语义 |
|------|------|------|
| 品牌主色 | `primary` / `primarySoftBg` | 主色 / 主色浅底（选中高亮） |
| 背景表面 | `background` / `surface` / `surfaceRaised` | 页面 / 卡片 / 浮层 |
| | `surfaceMuted` / `surfaceHover` | 次级底（表头工具条）/ hover 底 |
| | `overlayBase` / `overlayStrong` | 半透明中性叠层两档（随模式自动适配） |
| 文本 | `foreground` / `textSecondary` / `textTertiary` | 正文 / 次级 / 弱化（占位符） |
| 边框 | `border` / `borderSubtle` | 常规边框 / 次级分隔 |
| 状态 | `info` `success` `warning` `error` + `*SoftBg` | 四态 + 各自浅底 |
| 图表交易 | `chartLine` `chartAxis` `chartSplit` `chartMark` | 曲线 / 轴 / 分割 / 标记 |
| | `chartGradientStart/End` `drawdownArea` | 面积渐变 / 回撤阴影 |
| | `chartScreenshotBg` `chartReplayLabel` `chartSeries[8]` | 截图底色 / 标注文字 / 多系列离散 |
| 图表工具条 | `chartToolbarText/TextMuted/Border/Accent/AccentTint` | klinecharts-pro 图纸 chrome（周期条/绘图栏），与页面语义色解耦 |
| 指示灯 | `statusDotOk/Fail/Warn` | 连接状态点 |

**交互状态（hover/active）不手工定义**：antd 组件由 `darkAlgorithm/defaultAlgorithm`
从 `colorPrimary` 等自动派生；CSS 消费走 `surfaceHover` / `overlay*`。这是刻意设计——
状态色属于"派生值",写死反而会和 antd 派生结果漂移。

### 命名映射

| palette 槽位 | CSS 变量（规范名） | 兼容旧名 | antd token |
|---|---|---|---|
| `background` | `--qc-bg` | `--tw-color-background` | `colorBgBase` |
| `foreground` | `--qc-text` | `--tw-color-foreground` | `colorTextBase` |
| `primary` | `--qc-primary` | `--tw-color-primary` | `colorPrimary` |
| `success` | `--qc-success` | `--tw-color-success` | `colorSuccess` |
| … | `--qc-<语义>`（kebab-case） | 九个旧名别名保留 | 见 theme/index.ts |

新代码一律用 `--qc-*`；`--tw-color-*` 是迁移期别名，消费端逐步改名后可删（删除点：`getCssVars`）。

## 管理员工作流：两条改色路径 + 主题包导入

### 路径 A：代码级改内置主题（评审友好）
编辑 `frontend/src/theme/builtin.ts` 里 `default` 亮/暗色值 → 跑守卫测试 → build。适合小改与 brand 微调新增。

### 路径 B：主题包导入（文件/压缩包）—— `frontend/scripts/theme-import.mjs`

```bash
cd frontend

# 1. 导出当前主题（拿到起点模板；--all 连同 packs 里的一起导出）
bun scripts/theme-import.mjs export --out /tmp/my-themes

# 2. 修改 JSON（结构 = { label, light: {...39 个槽位}, dark: {...} }，见 src/theme/fields.ts 契约）
#    也可以拿到别人给的 主题包.json / 主题包.zip，跳过 1-2

# 3. 导入（JSON 或 zip 均可；自动校验字段完整性与取值合法性，非法即列项报错不落盘）
bun scripts/theme-import.mjs import /tmp/my-themes/default.json   # → src/theme/packs/<id>.json

# 4. 一键启用（改写 config.ts 的 ACTIVE_THEME_ID）
bun scripts/theme-import.mjs use default

# 5. 验证 + 生效
bun run test -- src/theme/theme.test.ts   # 守卫（注册表合并、字段完整性、零残留字面量）
bun run build                              # 或开发态直接看热更效果
bun scripts/theme-import.mjs list          # 查看全部已注册主题
```

约定：主题 ID = 包文件名（kebab-case），非法文件名会从 `label` 推导；与内置主题重名的包会被拒绝；
导入的包不删文件就永远注册在列，回滚 = `use default`。坏包（字段缺失/色值非法）在应用加载期直接抛错，
不会出现"静默用错色"。仓库内 `src/theme/packs/ocean.json` 即一个示例包（蓝色变体，当前未激活）。

> 终端用户无任何主题切换入口；`use` 是维护者动作。若未来要开放运行时切换，
> 把 `ACTIVE_THEME_ID` 提升为读配置（settings 页已有 appearance 通路），消费端无需改动。

## 更换品牌配色的操作路径（最常见的任务）

1. 打开 `frontend/src/theme/palettes.ts`，修改 `default` 主题的 `light` / `dark` 两块色值。
   - 只改了一个模式？另一个模式保持原值即可，两块是独立的。
   - 不确定某个槽位被谁消费：全局搜对应 `--qc-` 变量名即可（槽位→变量名对照表见上）。
2. 若页面底色（`background`）也变了：同步 `frontend/index.html` 里内联 `<style>` 的两行
   首帧兜底值（有测试守卫，漏改会挂测试）。
3. 完事：`cd frontend && bun run test -- src/theme/theme.test.ts && bun run build`。
   antd 组件 / CSS / 图表 / canvas 下次构建或刷新后全部生效，业务组件零改动。

## 新增一套自定义主题 + 一键切换

1. `palettes.ts` 复制 `default` 整块改名（如 `ocean`），补齐亮/暗两套完整字段。
2. `config.ts` 把 `ACTIVE_THEME_ID = 'default'` 改为 `'ocean'` ——
   `satisfies keyof typeof THEMES` 保证写错名字在编译期直接报错。
3. 测试 `theme.test.ts` 会校验新主题字段齐全、取值合法。

> 预留的开放方向：把 `ACTIVE_THEME_ID` 从编译期常量提升为运行时读取
> （localStorage / 后端 appearance 配置即设置页已有 appearance.theme 通路），
> 消费端三渠道按 `getPalette(mode)` 取色即可跟随，无需改任何组件。
> 当前刻意不做终端用户切换入口，仅维护者改一行切换。

## 消费端怎么接入（新增组件时遵守）

- **React 组件**（antd）：`theme.useToken()` 取 antd token；交易语义色用 `useQuantColors()`。禁止硬编码。
- **React + inline style / Tailwind**：用 Tailwind 工具类（`bg-surface-muted` 这类，@theme 已注册）
  或 inline `var(--qc-*)`，亮暗自动跟随，通常不需要 `dark:` 变体。
- **pure CSS**：只用 var()，禁止出现 hex / rgb 字面量（守卫测试盯着 global.css/index.css）。
- **非 React canvas（klinecharts overlay / ECharts 静态配置）**：模块顶部从 `@/theme` 导入
  `activeTheme.light`（或 `getPalette(mode)`）派生常量；能进 React 的优先 `useQuantColors()`。

## 守卫测试

`frontend/src/theme/theme.test.ts`（跑 `bun run test`）四条链：
复数主题字段齐全合法 → CSS 变量与 antd token 同源一致 → index.html 首帧兜底同步 →
global.css / index.css 零颜色字面量。修改主题相关代码后跑它，漂移即红灯。

## 豁免清单（有意不接入主题的硬编码色）

| 位置 | 原因 |
|---|---|
| `src/desktop/splash.ts`、`src/desktop/CrashMask.tsx` | Tauri 原生启动屏 / 故障遮罩，独立视觉资产 |
| `WorkerShareModal.tsx` QR 码黑白 | 扫码对比度要求 |
| `pages/factor/FactorCodePanel.tsx` `#1e1e1e/#d4d4d4` | 代码块有意恒深底（O2 注释） |
| 阴影 box-shadow 里的 rgba、极少量半透明中性灰 | elevation/中性叠层，非品牌色 |
| `extension/*` 绘图工具默认色（gannBox `#6C757D/#FF6B6B`、abcd/xabcd `#FFA500`、波浪系 `#4ECDC4` 等） | 与 palette 槽位均不等值；重复出现者已抽模块常量，单次出现保持内联 |
| `klineAnnotations.ts` `COLOR_CONFIG`（买 `#26a666ff` / 卖 `#ff0400ff` 等） | 用户 JSON 注入优先的默认值，与 semantic 槽位不等值 |
| `ChartShell.tsx` `AREA_DEFAULT_BG`（klinecharts 内置蓝 `rgba(22,119,255,…)`） | 引擎默认蓝，接品牌蓝会改变线形图面积色相；已注释标注可选接线方式 |
| `fillMarkers.ts` / `depthOverlay.ts` 成交标记/深度买卖色 | 高饱和 `#00E676/#FF5252` 及其 0.35-alpha 变体，palette 无 alpha 槽位 |
| `useIndicators.ts` `TEMPLATE_PLOT_COLORS`、`ModelSettingsPage.tsx` 供 应商头像色数组 | 无语义离散色（示例/身份色），候选并入主题离散调色板 |

## 已知边界

- `QUANT_COLORS` 静态快照不随运行时亮暗切换（历史设计，投影亮色值）；画布类消费方逐步迁
  `useQuantColors()`。
- klinecharts 主图样式 `setStyles` 在 mount 时按当次主题注册，亮暗切换后部分轴/网格色延迟到图表
  重建才更新（重构前既有行为，非本次引入）。
- 推断值标记：`palettes.ts` 里标注 `ponytail: 推断值` 的槽位（各 *SoftBg 暗色、surfaceHover 等）
  是为亮色像素守恒而新造的暗色值，可按品牌微调，不影响既有亮色还原。
