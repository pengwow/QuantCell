/**
 * 因子模块跨组件共享常量与纯函数：
 * 分类/生命周期配色、合法状态流转、指标语义评级着色、因子来源归类、数字格式化。
 */
import type { LifecycleStatus } from '@/api/factor';

export const CATEGORY_COLOR: Record<string, string> = {
  price: 'blue',
  momentum: 'green',
  volatility: 'orange',
  volume_price: 'cyan',
  technical: 'purple',
  fundamental: 'default',
  custom: 'geekblue',
  llm_code: 'magenta',
  llm_composite: 'purple',
};

/** 可人工归档的分类白名单（与后端 schemas.EDITABLE_FACTOR_CATEGORIES 对齐） */
export const EDITABLE_CATEGORIES = [
  'custom',
  'price',
  'momentum',
  'volatility',
  'volume_price',
  'technical',
  'fundamental',
] as const;

/** 分类 i18n 标签；缺失翻译时回退原始分类名（左栏/概览/表单共用） */
export const categoryLabel = (c: string, t: (key: string) => string): string => {
  const key = `factor_lib_cat_${c}`;
  const tx = t(key);
  return tx === key ? c : tx;
};

export const STATUS_COLOR: Record<LifecycleStatus, string> = {
  DISCOVERED: 'default',
  INSPECTED: 'blue',
  PAPER_TRADING: 'gold',
  LIVE: 'green',
  RETIRED: 'red',
};

/** 合法的下一状态（与后端 LIFECYCLE_TRANSITIONS 保持一致） */
export const NEXT_STATUS: Record<LifecycleStatus, LifecycleStatus[]> = {
  DISCOVERED: ['INSPECTED', 'RETIRED'],
  INSPECTED: ['DISCOVERED', 'PAPER_TRADING', 'RETIRED'],
  PAPER_TRADING: ['INSPECTED', 'LIVE', 'RETIRED'],
  LIVE: ['PAPER_TRADING', 'RETIRED'],
  RETIRED: [],
};

/** 指标语气：good=绿（好）、mid=蓝（可用）、bad=橙（偏弱）、flat=默认色 */
export type MetricTone = 'good' | 'mid' | 'bad' | 'flat';

/**
 * 统计指标语义评级（研究经验口径，仅着色提示，不改变数值）：
 * IC 强度按绝对值分档（负 IC 可反向使用）；覆盖率/换手率/显著性按常用阈值。
 */
export const rateAbs = (x: number, strong: number, usable: number): MetricTone => {
  const a = Math.abs(x);
  if (a >= strong) return 'good';
  if (a >= usable) return 'mid';
  return 'bad';
};

export const toneOf = (key: string, value: number): MetricTone => {
  switch (key) {
    case 'ic_mean':
      return rateAbs(value, 0.05, 0.03);
    case 'ic_ir':
    case 'annualized_ir':
      return rateAbs(value, 2, 1);
    case 'ic_ir_loose':
      return rateAbs(value, 0.5, 0.3);
    case 't_stat':
    case 'nw_t_stat':
      return rateAbs(value, 2, 1);
    case 'monotonicity':
      return rateAbs(value, 0.8, 0.5);
    case 'stability':
      if (value >= 0.5) return 'good';
      if (value >= 0.2) return 'mid';
      return 'bad';
    case 'long_short_return':
      return value > 0 ? 'good' : value < 0 ? 'bad' : 'flat';
    case 'coverage':
      if (value >= 0.8) return 'good';
      if (value >= 0.5) return 'mid';
      return 'bad';
    case 'turnover':
      if (value <= 0.1) return 'good';
      if (value <= 0.3) return 'mid';
      return 'bad';
    default:
      return 'flat';
  }
};

/** tone → 主题语义色；flat 返回 undefined 走默认文字色 */
export const toneColor = (
  tone: MetricTone,
  c: { positive: string; info: string; warning: string },
): string | undefined =>
  tone === 'good' ? c.positive : tone === 'mid' ? c.info : tone === 'bad' ? c.warning : undefined;

/** 因子来源（左栏筛选与标签共用）：合成/代码优先于内置判定，自定义表达式兜底 */
export type FactorSource = 'builtin' | 'code' | 'composite' | 'expression';

export const factorSource = (f: {
  builtin: boolean;
  kind?: 'expression' | 'code' | 'composite';
  category?: string;
}): FactorSource => {
  if (f.kind === 'composite' || f.category === 'llm_composite') return 'composite';
  if (f.kind === 'code' || f.category === 'llm_code') return 'code';
  return f.builtin ? 'builtin' : 'expression';
};

/** 数字统一格式化：null/undefined → — */
export const num = (v: number | null | undefined, digits = 3): string =>
  v === null || v === undefined ? '—' : v.toFixed(digits);
