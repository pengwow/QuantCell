/**
 * 量化交易语义色 — 单一真相源
 *
 * 所有涉及"涨/跌/盈利/亏损/正负"语义的颜色必须从这里取，
 * 禁止在子组件里硬编码 QUANT_COLORS.positive / QUANT_COLORS.negative / QUANT_COLORS.info 等 antd v5 风格颜色。
 *
 * 使用方式：
 *   1. 组件内用 React hook（推荐，跟随主题切换自动更新）：
 *      const { token } = theme.useToken();
 *      const { positive, negative, ... } = useQuantColors();
 *
 *   2. 非 React 场景 / 静态展示（向后兼容）：
 *      import { QUANT_COLORS } from '@/utils/colors';
 *      注意：QUANT_COLORS 是 antd 默认亮色 token 快照，不会跟随主题切换。
 */
import { theme, type GlobalToken } from 'antd';

/** 量化语义色结构 — 与 App.tsx ConfigProvider token 里的 tradingToken 字段对齐 */
export interface QuantColors {
  /** 正收益 / 盈利 / 多头 */
  positive: string;
  /** 负收益 / 亏损 / 空头 */
  negative: string;
  /** 中性 / 持平 */
  neutral: string;
  /** 警告 */
  warning: string;
  /** 信息 / 链接 */
  info: string;
  /** 图表主线颜色（累计收益曲线等） */
  chartLine: string;
  /** 图表坐标轴颜色 */
  chartAxis: string;
  /** 图表分割线颜色 */
  chartSplit: string;
  /** 图表标记线颜色（0 轴虚线等） */
  chartMark: string;
  /** 图表面积渐变起点（高透明度） */
  chartGradientStart: string;
  /** 图表面积渐变终点（极低透明度） */
  chartGradientEnd: string;
  /** 最大回撤阴影颜色 */
  drawdownArea: string;
}

/** QuantCell 扩展 token — 在 antd GlobalToken 基础上加上交易语义色。
 * 用 Partial 因为 deriveQuantColors 只读取部分字段，
 * 静态快照也只需要传颜色值，不需要完整 token 对象。 */
export type TradingToken = Partial<GlobalToken> & {
  colorChartLine?: string;
  colorChartAxis?: string;
  colorChartSplit?: string;
  colorChartMark?: string;
  colorChartGradientStart?: string;
  colorChartGradientEnd?: string;
  colorDrawdownArea?: string;
};

/**
 * 从当前 antd theme token 派生出完整的量化语义色。
 * antd 的 colorSuccess / colorError 已经在 ConfigProvider 里被
 * 映射为 QuantCell 自定义的正/负收益色，所以直接用。
 */
export function deriveQuantColors(t: TradingToken): QuantColors {
  return {
    positive: t.colorSuccess ?? '#1a7f37',
    negative: t.colorError ?? '#d1242f',
    neutral: t.colorTextSecondary ?? t.colorText ?? '#595959',
    warning: t.colorWarning ?? '#eac54f',
    info: t.colorInfo ?? '#0969da',
    chartLine: t.colorChartLine ?? t.colorInfo ?? '#0969da',
    chartAxis: t.colorChartAxis ?? t.colorBorderSecondary ?? '#d1d5db',
    chartSplit: t.colorChartSplit ?? t.colorBorderSecondary ?? '#e5e7eb',
    chartMark: t.colorChartMark ?? t.colorTextTertiary ?? '#999',
    chartGradientStart: t.colorChartGradientStart ?? 'rgba(9, 105, 218, 0.25)',
    chartGradientEnd: t.colorChartGradientEnd ?? 'rgba(9, 105, 218, 0.02)',
    drawdownArea: t.colorDrawdownArea ?? 'rgba(209, 36, 47, 0.12)',
  };
}

/**
 * React hook：跟随主题切换自动更新的量化语义色。
 * 在 ConfigProvider 内部组件中使用。
 */
export function useQuantColors(): QuantColors {
  const { token } = theme.useToken();
  return deriveQuantColors(token);
}

/**
 * 静态快照 — antd 默认亮色主题下的语义色。
 * 用于非 React 场景 / 向后兼容旧代码（WorkerOverviewTab 等正在逐步迁移）。
 * 警告：这个值不会跟随主题切换，只在非 React 代码里使用。
 */
export const QUANT_COLORS: QuantColors = deriveQuantColors({
  colorSuccess: '#1a7f37',
  colorError: '#d1242f',
  colorText: '#141414',
  colorTextSecondary: '#595959',
  colorWarning: '#eac54f',
  colorInfo: '#0969da',
  colorChartLine: '#0969da',
  colorChartAxis: '#d1d5db',
  colorChartSplit: '#e5e7eb',
  colorChartMark: '#9ca3af',
  colorChartGradientStart: 'rgba(9, 105, 218, 0.25)',
  colorChartGradientEnd: 'rgba(9, 105, 218, 0.02)',
  colorDrawdownArea: 'rgba(209, 36, 47, 0.12)',
  colorBorderSecondary: '#e5e7eb',
});
