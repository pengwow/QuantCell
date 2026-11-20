/**
 * 主题渠道适配层 —— palette 语义词 → 三条消费渠道的单点映射
 *
 *   ① CSS 变量：getCssVars / applyThemeVars 写入 :root（--qc-* 为准，--tw-color-* 为旧名兼容别名）
 *   ② antd token：paletteToTradingToken → ConfigProvider theme.token（App.tsx）
 *   ③ 静态快照：utils/colors.ts 的 QUANT_COLORS 用 light palette 派生（非 React canvas 代码）
 *
 * 三条渠道全部由 src/theme/palettes.ts 派生 —— 修改调色板一处，全站生效。
 */
import { theme as antdTheme } from 'antd';
import { resolveTheme } from './config';
import type { ThemeMode, ThemePalette } from './types';

export type { ThemeMode, ThemePalette, ThemeDefinition } from './types';
export { ACTIVE_THEME_ID } from './config';

/** 当前生效主题（模块加载期解析一次；注册表笔误在此刻抛错） */
export const activeTheme = resolveTheme();

export function getPalette(mode: ThemeMode): ThemePalette {
  return activeTheme[mode];
}

/* ------------------------------------------------------------------ */
/*  渠道 ②：antd token 映射                                            */
/* ------------------------------------------------------------------ */

import type { QuantTradingToken } from './types';

/** palette → antd ConfigProvider token（含 QuantCell 自定义 colorChart* 字段） */
export function paletteToTradingToken(mode: ThemeMode): QuantTradingToken {
  const p = activeTheme[mode];
  return {
    colorPrimary: p.primary,
    colorInfo: p.info,
    colorSuccess: p.success,
    colorWarning: p.warning,
    colorError: p.error,
    colorBgBase: p.background,
    colorTextBase: p.foreground,
    colorBorderSecondary: p.borderSubtle,
    // design-spec §10.2：背景/文本/边框显式覆盖，不再由 algorithm 派生
    colorBgLayout: p.canvas,
    colorBgContainer: p.surface,
    colorBgElevated: p.surfaceRaised,
    colorBorder: p.border,
    // 分割线（抽屉/表格/卡片内部分隔）：antd 默认由 algorithm 派生出一个偏蓝的灰，
    // 与 spec §2.2 的 --bd 不是同一个色，显式对齐
    colorSplit: p.border,
    colorText: p.foreground,
    colorTextSecondary: p.textSecondary,
    colorTextTertiary: p.textTertiary,
    colorTextQuaternary: p.textQuaternary,
    colorChartLine: p.chartLine,
    colorChartAxis: p.chartAxis,
    colorChartSplit: p.chartSplit,
    colorChartMark: p.chartMark,
    colorChartGradientStart: p.chartGradientStart,
    colorChartGradientEnd: p.chartGradientEnd,
    colorDrawdownArea: p.drawdownArea,
    chartSeries: p.chartSeries,
    colorChartScreenshotBg: p.chartScreenshotBg,
    colorChartReplayLabel: p.chartReplayLabel,
  };
}

/* ------------------------------------------------------------------ */
/*  渠道 ①：CSS 变量映射                                                */
/* ------------------------------------------------------------------ */

/**
 * palette → CSS 自定义属性。
 * - `--qc-*`：规范名，新代码一律使用这套；
 * - `--tw-color-*`：历史名（index.css body、scrollbar、prose、Tailwind @theme 桥接仍在用），
 *   作为别名保持取值一致，消费端可在后续迭代中逐步改名。
 */
export function getCssVars(mode: ThemeMode): Record<string, string> {
  const p = activeTheme[mode];
  return {
    /* 规范名 */
    '--qc-canvas': p.canvas,
    '--qc-bg': p.background,
    '--qc-surface': p.surface,
    '--qc-surface-raised': p.surfaceRaised,
    '--qc-surface-muted': p.surfaceMuted,
    '--qc-surface-hover': p.surfaceHover,
    '--qc-overlay': p.overlayBase,
    '--qc-overlay-strong': p.overlayStrong,
    '--qc-text': p.foreground,
    '--qc-text-secondary': p.textSecondary,
    '--qc-text-tertiary': p.textTertiary,
    '--qc-text-quaternary': p.textQuaternary,
    '--qc-border': p.border,
    '--qc-border-subtle': p.borderSubtle,
    '--qc-border-strong': p.borderStrong,
    '--qc-primary': p.primary,
    '--qc-primary-soft-bg': p.primarySoftBg,
    '--qc-on-primary': p.onPrimary,
    '--qc-user-bubble-bg': p.userBubbleBg,
    '--qc-user-bubble-fg': p.userBubbleFg,
    '--qc-shadow-card': p.shadowCard,
    '--qc-shadow-bubble': p.shadowBubble,
    '--qc-glow-1': p.glowCanvasA,
    '--qc-glow-2': p.glowCanvasB,
    '--qc-info': p.info,
    '--qc-success': p.success,
    '--qc-warning': p.warning,
    '--qc-error': p.error,
    '--qc-success-soft-bg': p.successSoftBg,
    '--qc-warning-soft-bg': p.warningSoftBg,
    '--qc-error-soft-bg': p.errorSoftBg,
    '--qc-chart-line': p.chartLine,
    '--qc-chart-axis': p.chartAxis,
    '--qc-chart-split': p.chartSplit,
    '--qc-chart-mark': p.chartMark,
    '--qc-chart-gradient-start': p.chartGradientStart,
    '--qc-chart-gradient-end': p.chartGradientEnd,
    '--qc-chart-drawdown': p.drawdownArea,
    '--qc-chart-screenshot-bg': p.chartScreenshotBg,
    '--qc-chart-replay-label': p.chartReplayLabel,
    '--qc-status-dot-ok': p.statusDotOk,
    '--qc-status-dot-fail': p.statusDotFail,
    '--qc-status-dot-warn': p.statusDotWarn,
    '--qc-chart-toolbar-text': p.chartToolbarText,
    '--qc-chart-toolbar-text-muted': p.chartToolbarTextMuted,
    '--qc-chart-toolbar-border': p.chartToolbarBorder,
    '--qc-chart-toolbar-accent': p.chartToolbarAccent,
    '--qc-chart-toolbar-accent-tint': p.chartToolbarAccentTint,
    /* 旧名兼容别名（值与规范名一一对应） */
    '--tw-color-background': p.background,
    '--tw-color-foreground': p.foreground,
    '--tw-color-primary': p.primary,
    '--tw-color-info': p.info,
    '--tw-color-success': p.success,
    '--tw-color-warning': p.warning,
    '--tw-color-error': p.error,
    '--tw-color-border': p.border,
    '--tw-color-border-secondary': p.borderSubtle,
  };
}

/** 把当前主题的 CSS 变量写入 <html> 内联样式（覆盖 CSS 内定义，故 global.css 不再持有颜色字面量） */
export function applyThemeVars(mode: ThemeMode): void {
  if (typeof document === 'undefined') return;
  const html = document.documentElement;
  for (const [name, value] of Object.entries(getCssVars(mode))) {
    html.style.setProperty(name, value);
  }
}

/* ------------------------------------------------------------------ */
/*  渠道 ②辅助：antd 算法                                             */
/* ------------------------------------------------------------------ */

/**
 * antd 主题算法。darkAlgorithm 会拿 seed 主色**重新生成整套暗色调色板**
 * （`#f97316` → `#d76516`），而 CSS 变量 `--qc-primary` 仍是 palette 值，
 * 于是暗色下「antd 驱动的按钮/选中态」与「`.qc-*` 自绘原语」变成两种橙 —— 
 * 违反 §2.2「品牌橙是唯一强调色」。在算法返回后把 primary 一族钉回 palette。
 *
 * 注意：只钉主色链路（基础/hover/active/边/底）；其余派生 token 仍用 antd 的，
 * 它们不承担品牌色语义，改了反而与 antd 内部（如 hover 阴影）不一致。
 */
export function themeAlgorithm(mode: ThemeMode) {
  const base = mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm;
  const primary = activeTheme[mode].primary;
  if (mode !== 'dark') return base;
  return (seedToken: Parameters<typeof base>[0], mapToken?: Parameters<typeof base>[1]) => ({
    ...base(seedToken, mapToken),
    colorPrimary: primary,
    colorPrimaryHover: `color-mix(in srgb, ${primary} 88%, white)`,
    colorPrimaryActive: `color-mix(in srgb, ${primary} 84%, black)`,
    colorPrimaryBorder: `color-mix(in srgb, ${primary} 45%, transparent)`,
    colorPrimaryBorderHover: `color-mix(in srgb, ${primary} 60%, transparent)`,
    colorPrimaryBg: `color-mix(in srgb, ${primary} 9%, transparent)`,
    colorPrimaryBgHover: `color-mix(in srgb, ${primary} 14%, transparent)`,
  });
}
