/**
 * 量化交易语义色 — antd / canvas 渠道适配
 *
 * 所有涉及"涨/跌/盈利/亏损/正负"语义的颜色必须从这里取，
 * 禁止在子组件里硬编码 QUANT_COLORS.positive / QUANT_COLORS.negative 等颜色值。
 *
 * 颜色的"值"统一来自 src/theme/palettes.ts（品牌色唯一真相源）；
 * 本文件只负责把它适配成组件图形消费的 QuantColors 形状。
 *
 * 使用方式：
 *   1. React 组件（推荐，跟随主题切换自动更新）：
 *      const colors = useQuantColors();
 *   2. 非 React 场景 / 静态展示（向后兼容）：
 *      import { QUANT_COLORS } from '@/utils/colors';
 *      注意：静态快照由亮色 palette 派生（paletteToTradingToken('light')），不跟随运行时主题切换。
 */
import { theme, type GlobalToken } from 'antd';
import { activeTheme, paletteToTradingToken } from '@/theme';
import type { QuantTradingToken } from '@/theme/types';

export type { QuantTradingToken as TradingToken } from '@/theme/types';

/** 量化语义色结构 — 与 ConfigProvider token 里的交易字段对齐 */
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
  /** 多系列折线离散调色板（无语义，纯视觉可辨） */
  chartSeries: string[];
}

/** 兼容形状：ConfigProvider 运行时 token（GlobalToken）或静态快照的部分字段 */
type Tokenish = Partial<GlobalToken> & Partial<Omit<QuantTradingToken, keyof GlobalToken>>;

/**
 * 从 antd token（或部分字段）派生完整的量化语义色。
 * 缺省位回退到亮色 palette —— 静态快照场景下等价于亮色值。
 * antd 的 colorSuccess / colorError 已在 ConfigProvider 被映射为
 * QuantCell 自定义正/负收益色，直接取用。
 */
export function deriveQuantColors(t: Tokenish): QuantColors {
  const p = activeTheme.light;
  return {
    positive: t.colorSuccess ?? p.success,
    negative: t.colorError ?? p.error,
    neutral: t.colorTextSecondary ?? t.colorText ?? p.textSecondary,
    warning: t.colorWarning ?? p.warning,
    info: t.colorInfo ?? p.info,
    chartLine: t.colorChartLine ?? t.colorInfo ?? p.chartLine,
    chartAxis: t.colorChartAxis ?? t.colorBorderSecondary ?? p.chartAxis,
    chartSplit: t.colorChartSplit ?? t.colorBorderSecondary ?? p.chartSplit,
    chartMark: t.colorChartMark ?? t.colorTextTertiary ?? p.chartMark,
    chartGradientStart: t.colorChartGradientStart ?? p.chartGradientStart,
    chartGradientEnd: t.colorChartGradientEnd ?? p.chartGradientEnd,
    drawdownArea: t.colorDrawdownArea ?? p.drawdownArea,
    chartSeries: t.chartSeries ?? p.chartSeries,
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
 * 静态快照 — 亮色主题下的量化语义色。
 * 用于非 React 场景 / 向后兼容旧代码（WorkerOverviewTab 等正在逐步迁移）。
 * 警告：这个值不会跟随主题切换，只在非 React 代码里使用。
 */
export const QUANT_COLORS: QuantColors = deriveQuantColors(paletteToTradingToken('light'));
