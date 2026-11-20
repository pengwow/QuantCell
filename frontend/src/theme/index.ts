/**
 * 主题渠道适配层 —— palette 语义词 → 三条消费渠道的单点映射
 *
 *   ① CSS 变量：getCssVars / applyThemeVars 写入 :root（--qc-* 为准，--tw-color-* 为旧名兼容别名）
 *   ② antd token：paletteToTradingToken → ConfigProvider theme.token（App.tsx）
 *   ③ 静态快照：utils/colors.ts 的 QUANT_COLORS 用 light palette 派生（非 React canvas 代码）
 *
 * 三条渠道全部由 src/theme/palettes.ts 派生 —— 修改调色板一处，全站生效。
 */
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
    '--qc-border': p.border,
    '--qc-border-subtle': p.borderSubtle,
    '--qc-primary': p.primary,
    '--qc-primary-soft-bg': p.primarySoftBg,
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
