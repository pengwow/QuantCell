/**
 * 回测概览指标卡片清单 + 可见性规则（纯函数，便于单测）。
 *
 * 口径（见 docs/superpowers/specs/2026-10-19-shared-capital-symbol-metrics-design.md）：
 * - symbol：按品种自身成交算出来的贡献类指标
 * - account：共享账户口径指标（引擎只有一条净值流，物理上无法按品种拆分）
 * - placeholder：引擎/后端暂未实现的恒 0 占位指标
 * 共享资金池模式下查看单个品种时只展示 symbol 类，避免把账户级数字当成品种指标。
 */

export type MetricScope = 'symbol' | 'account' | 'placeholder';
export type MetricColor = 'positive' | 'negative' | 'neutral';
export type MetricFormat = 'percent' | 'number' | 'int' | 'hours';

export interface MetricCardSpec {
  key: string;
  label: string;
  format: MetricFormat;
  /** 着色规则：多数指标按值正负，少数固定色或依赖其它指标（如最终权益 vs 初始权益） */
  color: (value: number, get: (key: string) => number) => MetricColor;
  scope: MetricScope;
  /** 可选口径说明：仅在口径易被误读的指标上提供，渲染为 label 旁的 Tooltip 提示 */
  hint?: string;
}

/** 按数值正负着色（0 视为 positive，与原实现一致） */
const bySign = (value: number): MetricColor => (value >= 0 ? 'positive' : 'negative');
/** 固定着色（忽略入参） */
const fixed = (color: MetricColor) => (): MetricColor => color;

/**
 * 19 张卡片。**数组顺序 = 页面展示顺序，必须与改造前逐项相对次序一致**（保证「全部」视图与
 * 独立资金池模式行为不变）；`scope` 只决定可见性（共享模式品种视角只看 `symbol`），
 * 不参与排序，所以这里是原顺序而非按 scope 分组。
 * 后端硬编码 0 的 11 张占位指标已按审计结论删除（见 2026-10-19-backtest-metrics-semantics-audit-design.md §四）。
 */
export const METRIC_CARDS: MetricCardSpec[] = [
  { key: 'total_return', label: '总收益率', format: 'percent', color: bySign, scope: 'symbol' },
  {
    key: 'cagr',
    label: '年化收益率',
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: '简化口径：等于区间总收益率，非真实年化',
  },
  { key: 'sharpe_ratio', label: '夏普比率', format: 'number', color: fixed('neutral'), scope: 'account' },
  { key: 'max_drawdown', label: '最大回撤', format: 'percent', color: fixed('negative'), scope: 'account' },
  { key: 'win_rate', label: '胜率', format: 'percent', color: fixed('neutral'), scope: 'symbol' },
  { key: 'profit_factor', label: '盈亏比', format: 'number', color: fixed('neutral'), scope: 'symbol' },
  { key: 'total_trades', label: '交易次数', format: 'int', color: fixed('neutral'), scope: 'symbol' },
  { key: 'winning_trades', label: '盈利交易', format: 'int', color: fixed('positive'), scope: 'symbol' },
  { key: 'losing_trades', label: '亏损交易', format: 'int', color: fixed('negative'), scope: 'symbol' },
  { key: 'total_pnl', label: '总盈亏', format: 'number', color: bySign, scope: 'symbol' },
  { key: 'initial_equity', label: '初始权益', format: 'number', color: fixed('neutral'), scope: 'account' },
  {
    key: 'final_equity',
    label: '最终权益',
    format: 'number',
    color: (value, get) => (value >= get('initial_equity') ? 'positive' : 'negative'),
    scope: 'account',
  },
  { key: 'equity_peak', label: '权益峰值', format: 'number', color: fixed('neutral'), scope: 'account' },
  // 卡尔马比率：共享资金池下分子是品种收益率、分母是账户回撤（混口径）→ 品种视角隐藏；
  // 独立资金池模式下它是有意义的（品种自身收益/回撤）。组合视图口径为账户收益率/账户回撤。
  {
    key: 'calmar_ratio',
    label: '卡尔马比率',
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: '组合视图=账户收益率/账户回撤；共享资金池品种视角不适用',
  },
  { key: 'expectancy', label: '期望收益', format: 'percent', color: bySign, scope: 'symbol' },
  { key: 'avg_trade', label: '平均交易', format: 'percent', color: bySign, scope: 'symbol' },
  { key: 'best_trade', label: '最佳交易', format: 'percent', color: fixed('positive'), scope: 'symbol' },
  { key: 'worst_trade', label: '最差交易', format: 'percent', color: fixed('negative'), scope: 'symbol' },
  { key: 'total_commission', label: '总手续费', format: 'number', color: fixed('negative'), scope: 'account' },
];

/**
 * 可见性：共享资金池 + 单品种视角 → 只保留按品种归因的贡献类指标；
 * 其余情形（「全部」视图 / 独立资金池模式）保持全部 19 张。
 */
export function visibleMetricCards(capitalMode: string | undefined, selectedSymbol: string): MetricCardSpec[] {
  const isSharedSymbolView = capitalMode === 'shared' && selectedSymbol !== 'all';
  return isSharedSymbolView ? METRIC_CARDS.filter((m) => m.scope === 'symbol') : METRIC_CARDS;
}

/**
 * 指标值 → 展示字符串。后端返回的百分比类指标已是百分比数值
 * （如 12.35 表示 12.35%），直接补单位即可。
 */
export function formatMetricValue(spec: MetricCardSpec, value: number): string {
  switch (spec.format) {
    case 'percent':
      return `${value.toFixed(2)}%`;
    case 'int':
      return value.toFixed(0);
    case 'hours':
      return `${value.toFixed(2)}h`;
    default:
      return value.toFixed(2);
  }
}
