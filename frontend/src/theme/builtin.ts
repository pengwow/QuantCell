/**
 * 内置主题（静态 TS 数据）—— 与 palettes.ts 的 packs 合并层分离，
 * 便于 scripts/theme-import.mjs 在 bun 下直接加载（bun 不吃 Vite 的 import.meta.glob）。
 * 维护者改品牌色仍然只改这份文件；主题包脚本见 docs/theme.md。
 *
 * default 主题的值已按 docs/design-spec.md v1 对齐（文本/边框由实色灰阶改为 alpha 阶梯、
 * 亮色 warning 加深、背景分 canvas/background/surface 三层），不再是"像素守恒"口径。
 */
import type { ThemeDefinition } from './types';

export const BUILTIN_THEMES: Record<string, ThemeDefinition> = {
  default: {
    label: 'QuantCell 默认（橙色品牌）',
    light: {
      // —— 品牌主色 ——
      primary: '#ea580c',
      primarySoftBg: 'rgba(234, 88, 12, 0.10)', // ponytail: 推断值 —— 首个消费者（选中高亮）出现时微调
      onPrimary: '#ffffff',
      // —— 背景与表面 ——
      canvas: '#f2f3f5',
      background: '#ffffff',
      surface: '#ffffff',
      surfaceRaised: '#f5f6f8', // design-spec --bge（内嵌面板/浮层/表头底）
      surfaceMuted: '#f5f5f5', // 继承自 AIChatModal bg-[#f5f5f5]
      surfaceHover: 'rgba(20, 20, 20, 0.05)', // design-spec §2.3 悬浮底
      overlayBase: 'rgba(128, 128, 128, 0.10)', // 继承自 global.css prose 表头底
      overlayStrong: 'rgba(128, 128, 128, 0.15)', // 继承自 global.css 行内代码底
      // —— 文本（alpha 阶梯，design-spec --fg / --fg-2/3/4） ——
      foreground: '#141414',
      textSecondary: 'rgba(20, 20, 20, 0.72)',
      textTertiary: 'rgba(20, 20, 20, 0.52)',
      textQuaternary: 'rgba(20, 20, 20, 0.38)',
      // —— 边框（alpha 阶梯，design-spec --bd / --bd-2） ——
      border: 'rgba(20, 20, 20, 0.13)',
      borderSubtle: '#e5e7eb', // 图表轴 / 弱分隔线保留实色
      borderStrong: 'rgba(20, 20, 20, 0.21)',
      // —— 聊天气泡 ——
      userBubbleBg: '#0969da', // design-spec --user-bg = var(--info)
      userBubbleFg: '#ffffff',
      // —— 阴影 / 辉光（非颜色 token） ——
      shadowCard: '0 1px 2px rgba(16, 20, 26, 0.04)',
      shadowBubble: '0 1px 4px rgba(16, 20, 26, 0.06)',
      glowCanvasA: 'rgba(234, 88, 12, 0.05)',
      glowCanvasB: 'rgba(9, 105, 218, 0.04)',
      // —— 状态色 ——
      info: '#0969da',
      success: '#1a7f37',
      warning: '#b45309', // design-spec --warn 亮档加深（原 #eac54f 对比度不足）
      error: '#d1242f',

      successSoftBg: '#f6ffed', // 继承自 IndicatorEditor Result 底
      warningSoftBg: '#fffbe6', // 继承自 IndicatorEditor Result 底
      errorSoftBg: '#fff2f0', // 继承自 IndicatorEditor Result 底
      // —— 图表 / 交易语义 ——
      chartLine: '#0969da',
      chartAxis: '#d1d5db',
      chartSplit: '#e5e7eb',
      chartMark: '#9ca3af',
      chartGradientStart: 'rgba(9, 105, 218, 0.25)',
      chartGradientEnd: 'rgba(9, 105, 218, 0.02)',
      drawdownArea: 'rgba(209, 36, 47, 0.12)',
      chartScreenshotBg: '#ffffff',
      chartReplayLabel: '#333333',
      chartSeries: ['#0969da', '#91cc75', '#ea580c', '#7c3aed', '#14b8a6', '#d4a017', '#dc2626', '#9a60b4'],
      // —— 系统状态指示灯 ——
      statusDotOk: '#4CAF50',
      statusDotFail: '#F44336',
      statusDotWarn: '#FFC107',
      // —— klinecharts 工具条图纸色（继承 chart-toolbars.css 既有字面量） ——
      chartToolbarText: '#051441',
      chartToolbarTextMuted: '#76808f',
      chartToolbarBorder: '#e5e7eb', // 既有 --k-border 经 --qc-border-subtle 的同角色收敛值
      chartToolbarAccent: '#1677ff',
      chartToolbarAccentTint: 'rgba(22, 119, 255, 0.15)',
    },
    dark: {
      // —— 品牌主色 ——
      primary: '#f97316',
      primarySoftBg: 'rgba(249, 115, 22, 0.16)', // ponytail: 推断值
      onPrimary: '#18100a',
      // —— 背景与表面 ——
      canvas: '#0b0c0e',
      background: '#17191c',
      surface: '#1d1f23', // design-spec --bgc（暗色由 #141414 改为 #1d1f23）
      surfaceRaised: '#232529', // design-spec --bge
      surfaceMuted: '#141414', // 继承自 AIChatModal dark:bg-[#141414]
      surfaceHover: 'rgba(250, 250, 249, 0.05)', // design-spec §2.3 悬浮底
      overlayBase: 'rgba(255, 255, 255, 0.05)', // 继承自 global.css .dark prose 表头底
      overlayStrong: 'rgba(255, 255, 255, 0.10)', // 继承自 global.css .dark 行内代码底
      // —— 文本（alpha 阶梯，design-spec --fg / --fg-2/3/4） ——
      foreground: '#fafaf9',
      textSecondary: 'rgba(250, 250, 249, 0.68)',
      textTertiary: 'rgba(250, 250, 249, 0.48)',
      textQuaternary: 'rgba(250, 250, 249, 0.36)',
      // —— 边框（alpha 阶梯，design-spec --bd / --bd-2） ——
      border: 'rgba(250, 250, 249, 0.12)',
      borderSubtle: '#4b5563', // 图表轴 / 弱分隔线保留实色
      borderStrong: 'rgba(250, 250, 249, 0.22)',
      // —— 聊天气泡 ——
      userBubbleBg: '#3e7aca', // = color-mix(in srgb, #478be6 88%, black) 的预算值（design-spec --user-bg）
      userBubbleFg: '#ffffff',
      // —— 阴影 / 辉光（非颜色 token） ——
      shadowCard: '0 1px 3px rgba(0, 0, 0, 0.22)',
      shadowBubble: '0 2px 8px rgba(0, 0, 0, 0.15)',
      glowCanvasA: 'rgba(249, 115, 22, 0.07)',
      glowCanvasB: 'rgba(71, 139, 230, 0.05)',
      // —— 状态色 ——
      info: '#478be6',
      success: '#57ab5a',
      warning: '#daaa3f',
      error: '#e5534b',
      successSoftBg: 'rgba(87, 171, 90, 0.16)', // ponytail: 推断值 —— 亮值为既有字面量
      warningSoftBg: 'rgba(218, 170, 63, 0.16)',
      errorSoftBg: 'rgba(229, 83, 75, 0.16)',
      // —— 图表 / 交易语义 ——
      chartLine: '#478be6',
      chartAxis: '#4b5563',
      chartSplit: '#374151',
      chartMark: '#9ca3af',
      chartGradientStart: 'rgba(71, 139, 230, 0.35)',
      chartGradientEnd: 'rgba(71, 139, 230, 0.04)',
      drawdownArea: 'rgba(229, 83, 75, 0.18)',
      chartScreenshotBg: '#151517',
      chartReplayLabel: '#ffffff',
      chartSeries: ['#0969da', '#91cc75', '#ea580c', '#7c3aed', '#14b8a6', '#d4a017', '#dc2626', '#9a60b4'],
      // —— 系统状态指示灯 ——
      statusDotOk: '#4CAF50',
      statusDotFail: '#F44336',
      statusDotWarn: '#FFC107',
      // —— klinecharts 工具条图纸色（继承 chart-toolbars.css .dark 覆盖；accent 暗色无覆盖与亮同值） ——
      chartToolbarText: '#f8f8f8',
      chartToolbarTextMuted: '#929aa5',
      chartToolbarBorder: '#292929',
      chartToolbarAccent: '#1677ff',
      chartToolbarAccentTint: 'rgba(22, 119, 255, 0.15)',
    },
  },
};

