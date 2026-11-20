/**
 * 主题类型定义 — 品牌色体系的标准语义层（参考 VS Code / 主流编辑器的 base → semantic → consumer 映射）
 *
 * 三层结构：
 *   1. palette（语义 token，本文件）  —— 唯一需要修改的地方：src/theme/palettes.ts
 *   2. 渠道适配（src/theme/index.ts） —— palette → CSS 变量 / antd token / canvas 静态快照
 *   3. 消费端（组件 / CSS / 图表）    —— 只引用上述映射产物，不持有颜色字面量
 */
import type { GlobalToken } from 'antd';

/** 主题模式 */
export type ThemeMode = 'light' | 'dark';

/** typestyle: 对照 ThemePalette 的字段分组见 palettes.ts 注释 */
export interface ThemePalette {
  /* ===== 品牌主色 ===== */
  /** 主色（按钮、选中态、强调） */
  primary: string;
  /** 主色的浅底（选中行背景、高亮胶囊等） */
  primarySoftBg: string;

  /* ===== 背景与表面 ===== */
  /** 页面背景 */
  background: string;
  /** 常规卡片 / 面板表面（antd 由 algorithm 从 BgBase 派生，CSS 消费用） */
  surface: string;
  /** 浮层表面（Modal / Drawer / Dropdown） */
  surfaceRaised: string;
  /** 中性弱底（次级工具条、表格表头、输入底） */
  surfaceMuted: string;
  /** 列表行 / 控件 hover 底 */
  surfaceHover: string;
  /** 半透明中性叠层（表头底、代码 chip 底等，随模式自动适配） */
  overlayBase: string;
  /** 半透明中性叠层（更强一档） */
  overlayStrong: string;

  /* ===== 文本 ===== */
  /** 正文 / 强调文本 */
  foreground: string;
  /** 次级文本（标签、说明） */
  textSecondary: string;
  /** 弱化文本（占位符、提示） */
  textTertiary: string;

  /* ===== 边框 ===== */
  /** 常规边框 */
  border: string;
  /** 次级分隔线 / 弱边框 */
  borderSubtle: string;

  /* ===== 状态色 ===== */
  info: string;
  success: string;
  warning: string;
  error: string;
  /** 成功语义浅底（Alert / 质徽章背景） */
  successSoftBg: string;
  warningSoftBg: string;
  errorSoftBg: string;

  /* ===== 图表 / 交易语义（对齐 utils/colors.ts 的 TradingToken 契约） ===== */
  chartLine: string;
  chartAxis: string;
  chartSplit: string;
  chartMark: string;
  chartGradientStart: string;
  chartGradientEnd: string;
  /** 最大回撤阴影 */
  drawdownArea: string;
  /** K线截图导出底色（暗 #151517 有意区别于页面底色） */
  chartScreenshotBg: string;
  /** 回测标注文本色 */
  chartReplayLabel: string;
  /** 多系列折线离散调色板（纯视觉可辨，两模式共用一组） */
  chartSeries: string[];

  /* ===== 系统状态指示灯（既有 Material 色值，两模式共用） ===== */
  statusDotOk: string;
  statusDotFail: string;
  statusDotWarn: string;

  /* ===== klinecharts 工具条图纸色（复刻 klinecharts-pro 的独立 chrome，与页面语义色解耦） ===== */
  chartToolbarText: string;
  chartToolbarTextMuted: string;
  chartToolbarBorder: string;
  chartToolbarAccent: string;
  /** hover / 选中底（accent 的 15% 淡层，两值相同故合一槽位） */
  chartToolbarAccentTint: string;
}

/** 主题定义：一个品牌主题 = 亮 + 暗两套完整语义色。新增主题即新增一条记录。 */
export interface ThemeDefinition {
  /** 维护者可读名称（仅日志/文档用） */
  label: string;
  light: ThemePalette;
  dark: ThemePalette;
}

/**
 * antd / 图表消费契约：在 antd GlobalToken 子集上叠加 QuantCell 自定义字段。
 * 由 paletteToTradingToken 从主题 palette 派生，替代原先 App.tsx 里的硬编码 tradingToken。
 */
export type QuantTradingToken = Pick<
  GlobalToken,
  // 注意：colorText / colorTextSecondary 故意不覆盖 —— 由 antd algorithm 按 BgBase 派生，
  // 与重构前 App.tsx tradingToken 行为一致（palette 的 text* 槽位只服务 CSS / canvas 渠道）
  | 'colorPrimary' | 'colorInfo' | 'colorSuccess' | 'colorWarning' | 'colorError'
  | 'colorBgBase' | 'colorTextBase' | 'colorBorderSecondary'
> & {
  colorChartLine: string;
  colorChartAxis: string;
  colorChartSplit: string;
  colorChartMark: string;
  colorChartGradientStart: string;
  colorChartGradientEnd: string;
  colorDrawdownArea: string;
  chartSeries: string[];
  colorChartScreenshotBg: string;
  colorChartReplayLabel: string;
};
