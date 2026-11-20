/**
 * 回测配置页头副标（page-sub）的纯格式化函数。
 * 只对真实表单值做形制转换，不做任何默认值编造。
 */

/** 1000000 → "1,000,000"（demo page-sub：初始资金 100,000 USDT 的千分位形制） */
export const formatCashGrouped = (v: number): string => v.toLocaleString('en-US');

/** 0.001 → "0.1%"；0.0005 → "0.05%"（demo page-sub：手续费 0.05% 单边的百分数形制） */
export const formatFeePercent = (v: number): string =>
  `${(v * 100).toFixed(4).replace(/\.?0+$/, '')}%`;
