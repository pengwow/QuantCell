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

// ===== 内置均值指标常驻图例（demo card-head 的 MA 图例 chips 对应物）=====

// klinecharts 10.0.3 默认指标线色板（dist/index.esm.js 内 DEFAULT 样式 indicator.lines，按线序取色）；
// ChartShell 未覆盖该样式段，画在图上的叠加线就用这套 → 图例 chip 取同值与图内线色对齐。
// ponytail: 常量抄自 klinecharts 源码，升级依赖时需对表；升级路径为改读 chart.getStyles().indicator.lines
export const INDICATOR_LINE_COLORS = ['#FF9600', '#935EBD', '#1677FF', '#E11D74', '#01C5C4'] as const;

// 参与常驻图例的内置 overlay 指标（startIndicator overlay 判定 'MA','EMA','BOLL','SAR','BBI','SMA'
// 中指标弹窗实际可添加的叠加线型；OI/FUNDING/CVD/VOL 等副图不进图例）
export const INDICATOR_LEGEND_NAMES = new Set(['MA', 'EMA', 'BOLL']);

// bar 时间（UTC）：ms → "MM-DD HH:mm"，与页头现价块 px_tag 同格式
// （直接读 getUTC* 字段，不动 dayjs 全局 UTC 配置，口径同 ChartPage 原内联实现）
export const formatUtcBarTime = (ms: number): string => {
  const d = new Date(ms);
  const p2 = (n: number) => String(n).padStart(2, '0');
  return `${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())} ${p2(d.getUTCHours())}:${p2(d.getUTCMinutes())}`;
};
