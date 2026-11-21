/**
 * 回测配置页头副标（page-sub）的纯格式化函数。
 * 只对真实表单值做形制转换，不做任何默认值编造。
 */

/** 1000000 → "1,000,000"（demo page-sub：初始资金 100,000 USDT 的千分位形制） */
export const formatCashGrouped = (v: number): string => v.toLocaleString('en-US');

/** 0.001 → "0.1%"；0.0005 → "0.05%"（demo page-sub：手续费 0.05% 单边的百分数形制） */
export const formatFeePercent = (v: number): string =>
  `${(v * 100).toFixed(4).replace(/\.?0+$/, '')}%`;

/** 秒 → 紧凑 mono 时长（demo 头部「耗时 42s」形制）。
 * ≥48h 返回 null：跨天的耗时是陈旧/重启任务的产物，没有摘要价值（区间已在头部单独展示）——
 * 省略比展示「耗时 1459037s」更诚实。 */
export const formatElapsedCompact = (seconds: number): string | null => {
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${String(s).padStart(2, '0')}s`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`;
  return null;
};
