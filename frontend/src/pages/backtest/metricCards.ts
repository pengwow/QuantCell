/**
 * 回测概览指标卡片清单 + 可见性规则（纯函数，便于单测）。
 *
 * 口径（见 docs/superpowers/specs/2026-10-19-shared-capital-symbol-metrics-design.md）：
 * - symbol：按品种自身成交算出来的贡献类指标
 * - account：共享账户口径指标（引擎只有一条净值流，物理上无法按品种拆分）
 * - placeholder：品种视角不展示的派生/未实现指标（含已算出的账户派生指标与仍未实现的占位项）
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
 * 27 张卡片。**数组顺序 = 页面展示顺序，必须与改造前逐项一致**（保证「全部」视图与
 * 独立资金池模式行为不变）；`scope` 只决定可见性（共享模式品种视角只看 `symbol`），
 * 不参与排序，所以这里是原顺序而非按 scope 分组。
 */
export const METRIC_CARDS: MetricCardSpec[] = [
  {
    key: 'total_return',
    label: '总收益率',
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: '区间总盈亏 ÷ 初始资金。共享资金池下分母是账户的一笔初始资金，因此各品种收益率之和即账户总收益率',
  },
  {
    key: 'cagr',
    label: '年化收益率',
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: '按数据时间范围复利年化：(1 + 总收益率)^(365 / 回测天数) − 1。回测跨度不足一年时会被放大，跨周期比较请以本指标为准',
  },
  {
    key: 'sharpe_ratio',
    label: '夏普比率',
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: '风险调整后收益：年化收益 ÷ 年化波动率，数值越高表示单位风险换来的收益越多。账户级口径，共享资金池无法按品种拆分',
  },
  {
    key: 'max_drawdown',
    label: '最大回撤',
    format: 'percent',
    color: fixed('negative'),
    scope: 'account',
    hint: '净值从历史最高点回落的最大幅度，衡量最坏情况下的亏损深度。账户级口径，共享资金池无法按品种拆分',
  },
  {
    key: 'win_rate',
    label: '胜率',
    format: 'percent',
    color: fixed('neutral'),
    scope: 'symbol',
    hint: '盈利成交笔数 ÷ 总成交笔数。注意分母是引擎成交笔数（开仓、平仓各计一笔）',
  },
  {
    key: 'profit_factor',
    label: '盈亏比',
    format: 'number',
    color: fixed('neutral'),
    scope: 'symbol',
    hint: '盈利交易的总盈利 ÷ 亏损交易的总亏损绝对值。大于 1 表示整体盈利，等于 1 表示盈亏相抵',
  },
  {
    key: 'total_trades',
    label: '交易次数',
    format: 'int',
    color: fixed('neutral'),
    scope: 'symbol',
    hint: '引擎成交笔数，开仓与平仓各计一笔。与「盈利交易 + 亏损交易」的 round-trip 口径不同，后者按一次完整开平计一笔',
  },
  {
    key: 'winning_trades',
    label: '盈利交易',
    format: 'int',
    color: fixed('positive'),
    scope: 'symbol',
    hint: '平仓盈亏大于 0 的完整交易（round-trip）笔数',
  },
  {
    key: 'losing_trades',
    label: '亏损交易',
    format: 'int',
    color: fixed('negative'),
    scope: 'symbol',
    hint: '平仓盈亏小于等于 0 的完整交易（round-trip）笔数',
  },
  {
    key: 'total_pnl',
    label: '总盈亏',
    format: 'number',
    color: bySign,
    scope: 'symbol',
    hint: '已实现盈亏合计（已扣除手续费）。共享资金池下各品种之和即该品种对账户盈亏的贡献',
  },
  {
    key: 'initial_equity',
    label: '初始权益',
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: '回测起始资金。共享资金池为账户的一笔初始资金，不按品种数量重复计算',
  },
  {
    key: 'final_equity',
    label: '最终权益',
    format: 'number',
    color: (value, get) => (value >= get('initial_equity') ? 'positive' : 'negative'),
    scope: 'account',
    hint: '回测结束时的账户净值，包含未平仓持仓的浮动盈亏',
  },
  {
    key: 'equity_peak',
    label: '权益峰值',
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: '回测期间账户净值达到过的最高点，最大回撤即以它为基准计算',
  },
  {
    // 卡尔马 = 收益率 ÷ 最大回撤：共享模式下分子是「品种贡献收益率」、分母是「账户回撤」，
    // 口径混合无意义 → 归账户级并在品种视角隐藏（不是恒 0，实盘会出数，见 spec §7）
    key: 'calmar_ratio',
    label: '卡尔马比率',
    format: 'number',
    color: fixed('neutral'),
    scope: 'account',
    hint: '年化收益率 ÷ 最大回撤，衡量单位回撤换来的收益。组合视图 = 账户收益率 / 账户回撤；共享资金池的品种视角不适用（分子分母不同层级）',
  },
  {
    key: 'avg_drawdown',
    label: '平均回撤',
    format: 'percent',
    color: fixed('negative'),
    // 依赖账户级 equity_curve（共享分支 per-symbol 是深拷贝），物理上无法按品种拆分 → 归 account
    scope: 'account',
    hint: '沿净值曲线逐点计算相对历史峰值的回撤，再取平均值，反映常态回撤水平（最大回撤只看最深一次）。账户级口径，共享资金池无法按品种拆分',
  },
  {
    key: 'volatility',
    label: '年化波动率',
    format: 'percent',
    color: fixed('neutral'),
    // 依赖账户级 equity_curve 算对数收益序列 → 归 account
    scope: 'account',
    hint: '逐 bar 对数收益的标准差 × √年 bar 数，衡量净值波动剧烈程度，数值越大风险越高。账户级口径，共享资金池无法按品种拆分',
  },
  {
    key: 'expectancy',
    label: '期望收益',
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: '总盈亏 ÷ 成交笔数，即每笔成交的平均盈亏，为正说明策略长期具备正期望',
  },
  {
    key: 'avg_trade',
    label: '平均交易',
    format: 'percent',
    color: bySign,
    scope: 'symbol',
    hint: '逐笔交易收益率的算术平均值，反映单笔交易的平均获利水平',
  },
  {
    key: 'best_trade',
    label: '最佳交易',
    format: 'percent',
    color: fixed('positive'),
    scope: 'symbol',
    hint: '所有交易中最高的单笔收益率',
  },
  {
    key: 'worst_trade',
    label: '最差交易',
    format: 'percent',
    color: fixed('negative'),
    scope: 'symbol',
    hint: '所有交易中最低的单笔收益率，可用于评估单笔风险敞口',
  },
  {
    key: 'total_commission',
    label: '总手续费',
    format: 'number',
    color: fixed('negative'),
    scope: 'account',
    hint: '回测期间累计产生的交易手续费，已从盈亏中扣除',
  },
  {
    key: 'sqn',
    label: 'SQN',
    format: 'number',
    color: fixed('neutral'),
    // 纯 trades 驱动（逐笔收益率），共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: '系统质量数 = √交易笔数 × 逐笔收益均值 ÷ 逐笔收益标准差，综合衡量策略的稳定性与可重复性',
  },
  {
    key: 'kelly_criterion',
    label: '凯利准则',
    format: 'number',
    color: fixed('neutral'),
    // 纯 trades 驱动（胜率、平均盈利/亏损），共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: '建议仓位比例 f = 胜率 − (1 − 胜率) ÷ 盈亏比，负值按 0 处理（表示不建议下注）',
  },
  {
    key: 'exposure_time',
    label: '暴露时间',
    format: 'percent',
    color: fixed('neutral'),
    // 分子是品种持仓并集时长（trades 驱动），分母是账户级常量（data_start_ns/end_ns）——
    // 品种视角独立有意义（"该品种持仓时长占回测总时长的百分比"）
    scope: 'symbol',
    hint: '持仓区间并集时长 ÷ 回测总时长，反映资金在场内的时间占比（重叠持仓不重复计时）',
  },
  {
    key: 'duration_days',
    label: '回测天数',
    format: 'int',
    color: fixed('neutral'),
    // 纯账户级常量 data_start_ns/end_ns，物理上无法按品种拆分 → 归 account
    scope: 'account',
    hint: '回测数据覆盖的自然日数，用于年化类指标的换算基准。账户级常量，所有品种共享同值',
  },
  {
    key: 'avg_trade_duration_hours',
    label: '平均持仓时间',
    format: 'hours',
    color: fixed('neutral'),
    // 纯 trades 驱动（逐笔 entry→exit 时长），共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: '每笔交易从开仓到平仓的平均时长（小时），反映策略的持仓周期',
  },
  {
    key: 'max_trade_duration_hours',
    label: '最长持仓时间',
    format: 'hours',
    color: fixed('neutral'),
    // 纯 trades 驱动，共享分支 per-symbol 条目已注入各自 trades → 品种独立可算
    scope: 'symbol',
    hint: '单笔交易从开仓到平仓的最长时长（小时），可用于识别长期未平仓的异常持仓',
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
