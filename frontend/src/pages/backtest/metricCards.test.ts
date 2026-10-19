import { describe, expect, it } from 'vitest';
import { METRIC_CARDS, formatMetricValue, visibleMetricCards } from './metricCards';

/** 12 张按品种归因的贡献类指标（顺序即展示顺序） */
const SYMBOL_KEYS = [
  'total_return',
  'cagr',
  'win_rate',
  'profit_factor',
  'total_trades',
  'winning_trades',
  'losing_trades',
  'total_pnl',
  'expectancy',
  'avg_trade',
  'best_trade',
  'worst_trade',
];

const keys = (mode: string | undefined, sym: string) =>
  visibleMetricCards(mode, sym).map((m) => m.key);

/** 删掉 11 张恒 0 卡片后的 19 张卡片顺序（「全部」视图必须保持这个顺序） */
const FULL_KEYS = [
  'total_return',
  'cagr',
  'sharpe_ratio',
  'max_drawdown',
  'win_rate',
  'profit_factor',
  'total_trades',
  'winning_trades',
  'losing_trades',
  'total_pnl',
  'initial_equity',
  'final_equity',
  'equity_peak',
  'calmar_ratio',
  'expectancy',
  'avg_trade',
  'best_trade',
  'worst_trade',
  'total_commission',
];

/** 已从清单删除的 11 张后端硬编码 0 的占位指标 */
const REMOVED_KEYS = [
  'sortino_ratio',
  'avg_drawdown',
  'volatility',
  'alpha',
  'beta',
  'sqn',
  'kelly_criterion',
  'exposure_time',
  'duration_days',
  'avg_trade_duration_hours',
  'max_trade_duration_hours',
];

describe('METRIC_CARDS 顺序', () => {
  it('与改造前的页面展示顺序相对次序一致（scope 只管可见性，不参与排序）', () => {
    expect(METRIC_CARDS.map((m) => m.key)).toEqual(FULL_KEYS);
  });
});

describe('METRIC_CARDS 口径标注', () => {
  it('年化收益率带「简化口径」hint', () => {
    const cagr = METRIC_CARDS.find((m) => m.key === 'cagr')!;
    expect(cagr.hint).toBeTruthy();
    expect(cagr.hint).toContain('简化');
  });

  it('卡尔马比率 scope 归为 account（共享模式品种视角隐藏）', () => {
    expect(METRIC_CARDS.find((m) => m.key === 'calmar_ratio')!.scope).toBe('account');
  });

  it('已删除的 11 张占位指标不再出现在清单里', () => {
    const shown = METRIC_CARDS.map((m) => m.key);
    for (const removed of REMOVED_KEYS) {
      expect(shown).not.toContain(removed);
    }
  });
});

describe('visibleMetricCards', () => {
  it('共享资金池 + 单品种视角：只保留 12 张贡献类指标', () => {
    expect(keys('shared', 'ETH/USDT')).toEqual(SYMBOL_KEYS);
  });

  it('共享资金池 + 单品种视角：不含账户级指标', () => {
    const shown = keys('shared', 'ETH/USDT');
    for (const hidden of ['sharpe_ratio', 'max_drawdown', 'initial_equity', 'final_equity',
      'equity_peak', 'total_commission', 'calmar_ratio']) {
      expect(shown).not.toContain(hidden);
    }
  });

  it('共享资金池 + 全部视图：展示全部 19 张', () => {
    expect(METRIC_CARDS).toHaveLength(19);
    expect(keys('shared', 'all')).toHaveLength(19);
  });

  it('独立资金池（或缺省）模式单品种视角：展示全部 19 张', () => {
    expect(keys('per_symbol', 'ETH/USDT')).toHaveLength(19);
    expect(keys(undefined, 'ETH/USDT')).toHaveLength(19);
  });
});

describe('formatMetricValue', () => {
  const specOf = (key: string) => METRIC_CARDS.find((m) => m.key === key)!;

  it('百分比/小数/整数/小时各自带单位', () => {
    expect(formatMetricValue(specOf('total_return'), 12.3456)).toBe('12.35%');
    expect(formatMetricValue(specOf('total_pnl'), 1234.567)).toBe('1234.57');
    expect(formatMetricValue(specOf('total_trades'), 12.6)).toBe('13');
    // hours 格式已无卡片使用，用合成 spec 验证格式化逻辑本身
    expect(formatMetricValue({ ...specOf('total_return'), format: 'hours' }, 3.5)).toBe('3.50h');
  });
});
