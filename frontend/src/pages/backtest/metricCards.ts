/**
 * 回测概览指标卡片清单 + 可见性规则（纯函数，便于单测）。
 *
 * 口径（见 docs/superpowers/specs/2026-10-19-shared-capital-symbol-metrics-design.md）：
 * - symbol：按品种自身成交算出来的贡献类指标
 * - account：共享账户口径指标（引擎只有一条净值流，物理上无法按品种拆分）
 * - placeholder：品种视角不展示的派生/未实现指标（含已算出的账户派生指标与仍未实现的占位项）
 * 共享资金池模式下查看单个品种时只展示 symbol 类，避免把账户级数字当成品种指标。
 */

import i18n from '../../i18n/config';

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
  /**
   * 指标含义说明（必填）：卡片标题后统一渲染 ⓘ，悬浮/点击展示。
   * 设为必填是为了让 TypeScript 在编译期兜住「新增卡片忘写说明」的遗漏。
   */
  hint: string;
}

/** 按数值正负着色（0 视为 positive，与原实现一致） */
const bySign = (value: number): MetricColor => (value >= 0 ? 'positive' : 'negative');
/** 固定着色（忽略入参） */
const fixed = (color: MetricColor) => (): MetricColor => color;

/**
 * 28 张卡片。**数组顺序 = 页面展示顺序，必须与改造前逐项一致**（保证「全部」视图与
 * 独立资金池模式行为不变）；`scope` 只决定可见性（共享模式品种视角只看 `symbol`），
 * 不参与排序，所以这里是原顺序而非按 scope 分组。
 * label/hint 在模块加载时经 i18n.t 求值（非 React 组件，同 useUpdater.ts 模式），语言切换需刷新页面生效。
 */
export const METRIC_CARDS: MetricCardSpec[] = [
  {
    key: 'total_return',
    label: i18n.t('total_return'),
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: i18n.t('backtest_hint_total_return'),
  },
  {
    key: 'cagr',
    label: i18n.t('annual_return'),
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: i18n.t('backtest_hint_cagr'),
  },
  {
    key: 'sharpe_ratio',
    label: i18n.t('sharpe_ratio'),
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: i18n.t('backtest_hint_sharpe_ratio'),
  },
  {
    key: 'deflated_sharpe',
    label: i18n.t('backtest_metric_deflated_sharpe'),
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: i18n.t('backtest_hint_deflated_sharpe'),
  },
  {
    key: 'max_drawdown',
    label: i18n.t('max_drawdown'),
    format: 'percent',
    color: fixed('negative'),
    scope: 'account',
    hint: i18n.t('backtest_hint_max_drawdown'),
  },
  {
    key: 'win_rate',
    label: i18n.t('win_rate'),
    format: 'percent',
    color: fixed('neutral'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_win_rate'),
  },
  {
    key: 'profit_factor',
    label: i18n.t('profit_loss_ratio'),
    format: 'number',
    color: fixed('neutral'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_profit_factor'),
  },
  {
    key: 'total_trades',
    label: i18n.t('total_trades'),
    format: 'int',
    color: fixed('neutral'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_total_trades'),
  },
  {
    key: 'winning_trades',
    label: i18n.t('backtest_metric_winning_trades'),
    format: 'int',
    color: fixed('positive'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_winning_trades'),
  },
  {
    key: 'losing_trades',
    label: i18n.t('backtest_metric_losing_trades'),
    format: 'int',
    color: fixed('negative'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_losing_trades'),
  },
  {
    key: 'total_pnl',
    label: i18n.t('backtest_metric_total_pnl'),
    format: 'number',
    color: bySign,
    scope: 'symbol',
    hint: i18n.t('backtest_hint_total_pnl'),
  },
  {
    key: 'initial_equity',
    label: i18n.t('backtest_metric_initial_equity'),
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: i18n.t('backtest_hint_initial_equity'),
  },
  {
    key: 'final_equity',
    label: i18n.t('backtest_metric_final_equity'),
    format: 'number',
    color: (value, get) => (value >= get('initial_equity') ? 'positive' : 'negative'),
    scope: 'account',
    hint: i18n.t('backtest_hint_final_equity'),
  },
  {
    key: 'equity_peak',
    label: i18n.t('backtest_metric_equity_peak'),
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: i18n.t('backtest_hint_equity_peak'),
  },
  {
    // 卡尔马 = 收益率 ÷ 最大回撤：共享模式下分子是「品种贡献收益率」、分母是「账户回撤」，
    // 口径混合无意义 → 归账户级并在品种视角隐藏（不是恒 0，实盘会出数，见 spec §7）
    key: 'calmar_ratio',
    label: i18n.t('calmar_ratio_short'),
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: i18n.t('backtest_hint_calmar_ratio'),
  },
  {
    key: 'avg_drawdown',
    label: i18n.t('backtest_metric_avg_drawdown'),
    format: 'percent',
    color: fixed('negative'),
    // 依赖账户级 equity_curve（共享分支 per-symbol 是深拷贝），物理上无法按品种拆分 → 归 account
    scope: 'account',
    hint: i18n.t('backtest_hint_avg_drawdown'),
  },
  {
    key: 'volatility',
    label: i18n.t('backtest_metric_annual_volatility'),
    format: 'percent',
    color: fixed('neutral'),
    // 依赖账户级 equity_curve 算对数收益序列 → 归 account
    scope: 'account',
    hint: i18n.t('backtest_hint_volatility'),
  },
  {
    key: 'expectancy',
    label: i18n.t('backtest_metric_expectancy'),
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: i18n.t('backtest_hint_expectancy'),
  },
  {
    key: 'avg_trade',
    label: i18n.t('backtest_metric_avg_trade'),
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: i18n.t('backtest_hint_avg_trade'),
  },
  {
    key: 'best_trade',
    label: i18n.t('backtest_metric_best_trade'),
    format: 'percent',
    color: fixed('positive'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_best_trade'),
  },
  {
    key: 'worst_trade',
    label: i18n.t('backtest_metric_worst_trade'),
    format: 'percent',
    color: fixed('negative'),
    scope: 'symbol',
    hint: i18n.t('backtest_hint_worst_trade'),
  },
  {
    key: 'total_commission',
    label: i18n.t('backtest_metric_total_commission'),
    format: 'number',
    color: fixed('negative'),
    scope: 'account',
    hint: i18n.t('backtest_hint_total_commission'),
  },
  {
    key: 'sqn',
    label: 'SQN',
    format: 'number',
    color: fixed('neutral'),
    // 纯 trades 驱动（逐笔收益率），共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: i18n.t('backtest_hint_sqn'),
  },
  {
    key: 'kelly_criterion',
    label: i18n.t('backtest_metric_kelly_criterion'),
    format: 'number',
    color: fixed('neutral'),
    // 纯 trades 驱动（胜率、平均盈利/亏损），共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: i18n.t('backtest_hint_kelly_criterion'),
  },
  {
    key: 'exposure_time',
    label: i18n.t('backtest_metric_exposure_time'),
    format: 'percent',
    color: fixed('neutral'),
    // 分子是品种持仓并集时长（trades 驱动），分母是账户级常量（data_start_ns/end_ns）——
    // 品种视角独立有意义（"该品种持仓时长占回测总时长的百分比"）
    scope: 'symbol',
    hint: i18n.t('backtest_hint_exposure_time'),
  },
  {
    key: 'duration_days',
    label: i18n.t('backtest_metric_duration_days'),
    format: 'int',
    color: fixed('neutral'),
    // 纯账户级常量 data_start_ns/end_ns，物理上无法按品种拆分 → 归 account
    scope: 'account',
    hint: i18n.t('backtest_hint_duration_days'),
  },
  {
    key: 'avg_trade_duration_hours',
    label: i18n.t('backtest_metric_avg_trade_duration'),
    format: 'hours',
    color: fixed('neutral'),
    // 纯 trades 驱动（逐笔 entry→exit 时长），共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: i18n.t('backtest_hint_avg_trade_duration_hours'),
  },
  {
    key: 'max_trade_duration_hours',
    label: i18n.t('backtest_metric_max_trade_duration'),
    format: 'hours',
    color: fixed('neutral'),
    // 纯 trades 驱动，共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: i18n.t('backtest_hint_max_trade_duration_hours'),
  },
];

/**
 * 可见性：共享资金池 + 单品种视角 → 只保留按品种归因的贡献类指标；
 * 其余情形（「全部」视图 / 独立资金池模式）保持全部 27 张。
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
