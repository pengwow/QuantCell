/**
 * 主题包字段契约与校验 —— 单一来源，三处共用：
 *   1. palettes.ts 合并 packs/*.json 时的运行时守卫（包坏了在加载期直接抛错）
 *   2. theme.test.ts 的字段完整性断言
 *   3. scripts/theme-import.mjs 导入/导出时的 CLI 校验
 *
 * 注：effect 字段（shadowCard / shadowBubble）是 box-shadow 值而非颜色，
 * 故不参与 COLOR_RE 校验，只要求非空字符串。
 */
import type { ThemeMode, ThemePalette } from './types';

export const THEME_MODES: ThemeMode[] = ['light', 'dark'];

/** 颜色类槽位（走 COLOR_RE 校验） */
export const THEME_PALETTE_FIELDS = [
  'primary', 'primarySoftBg', 'onPrimary',
  'canvas', 'background', 'surface', 'surfaceRaised', 'surfaceMuted', 'surfaceHover', 'overlayBase', 'overlayStrong',
  'foreground', 'textSecondary', 'textTertiary', 'textQuaternary',
  'border', 'borderSubtle', 'borderStrong',
  'userBubbleBg', 'userBubbleFg',
  'glowCanvasA', 'glowCanvasB',
  'info', 'success', 'warning', 'error', 'successSoftBg', 'warningSoftBg', 'errorSoftBg',
  'chartLine', 'chartAxis', 'chartSplit', 'chartMark', 'chartGradientStart', 'chartGradientEnd',
  'drawdownArea', 'chartScreenshotBg', 'chartReplayLabel', 'chartSeries',
  'statusDotOk', 'statusDotFail', 'statusDotWarn',
  'chartToolbarText', 'chartToolbarTextMuted', 'chartToolbarBorder', 'chartToolbarAccent', 'chartToolbarAccentTint',
] as const satisfies readonly (keyof ThemePalette)[];

/** 非颜色槽位（阴影等自由字符串，只校验非空） */
export const THEME_EFFECT_FIELDS = ['shadowCard', 'shadowBubble'] as const;

/** 合法取值：hex（3~8 位）或 rgba()/rgb() */
export const COLOR_RE = /^(#[0-9a-fA-F]{3,8}|rgba?\([^()]+\))$/;

/** 结构校验。返回错误消息列表（空数组 = 通过），不抛错，方便 CLI 打印全部问题。 */
export function validateThemeData(data: unknown): string[] {
  const errors: string[] = [];
  const d = data as Record<string, unknown> | null;
  if (!d || typeof d !== 'object') return ['顶层必须是对象'];
  if (typeof d.label !== 'string' || !d.label.trim()) errors.push('缺少 label（维护者可读名称）');
  for (const mode of THEME_MODES) {
    const palette = d[mode] as Record<string, unknown> | undefined;
    if (!palette || typeof palette !== 'object') {
      errors.push(`缺少 ${mode} 调色板`);
      continue;
    }
    for (const field of THEME_PALETTE_FIELDS) {
      const v = palette[field];
      if (v === undefined) {
        errors.push(`${mode}.${field} 缺失`);
        continue;
      }
      if (field === 'chartSeries') {
        if (!Array.isArray(v) || v.length < 2) errors.push(`${mode}.chartSeries 必须是 ≥2 个颜色的数组`);
        else v.forEach((c, i) => { if (!COLOR_RE.test(String(c))) errors.push(`${mode}.chartSeries[${i}] 非法: ${c}`); });
      } else if (typeof v !== 'string' || !COLOR_RE.test(v)) {
        errors.push(`${mode}.${field} 非法（须为 hex/rgba）: ${v}`);
      }
    }
    // 阴影等 effect 槽位不是颜色：只要求非空字符串
    for (const field of THEME_EFFECT_FIELDS) {
      const v = palette[field];
      if (typeof v !== 'string' || !v.trim()) errors.push(`${mode}.${field} 必须是非空字符串: ${String(v)}`);
    }
  }
  return errors;
}
