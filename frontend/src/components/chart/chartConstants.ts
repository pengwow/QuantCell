import type { PeriodType } from 'klinecharts';
import type { ChartPeriodItem } from './ChartPeriodBar';

// 周期类型（klinecharts PeriodType）
export interface PeriodItem {
  label: string;
  value: string;
  span: number;
  type: PeriodType;
}

// 周期配置
export const PERIODS: PeriodItem[] = [
  { label: '1m', value: '1m', span: 1, type: 'minute' },
  { label: '5m', value: '5m', span: 5, type: 'minute' },
  { label: '15m', value: '15m', span: 15, type: 'minute' },
  { label: '30m', value: '30m', span: 30, type: 'minute' },
  { label: '1H', value: '1h', span: 60, type: 'minute' },
  { label: '4H', value: '4h', span: 240, type: 'minute' },
  { label: '1D', value: '1d', span: 1, type: 'day' },
  { label: '1W', value: '1w', span: 1, type: 'week' },
];

// 更多周期
export const MORE_PERIODS: PeriodItem[] = [
  { label: '2H', value: '2h', span: 120, type: 'minute' },
  { label: '1M', value: '1M', span: 1, type: 'month' },
  { label: '1Y', value: '1y', span: 1, type: 'year' },
];

// 上方工具栏平铺展示的全部周期（原「更多」里的 2H/1M/1Y 一并铺开）
export const PERIOD_BAR_ITEMS: ChartPeriodItem[] = [...PERIODS, ...MORE_PERIODS].map(p => ({
  label: p.label,
  value: p.value,
}));

// period value → klinecharts setPeriod 参数（在 PERIODS / MORE_PERIODS 中查表）
export const findPeriodItem = (value: string): PeriodItem | undefined =>
  PERIODS.find(p => p.value === value) || MORE_PERIODS.find(p => p.value === value);
