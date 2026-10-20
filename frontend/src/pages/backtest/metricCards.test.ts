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

/** 改造前「回测概览」的 30 张卡片顺序（「全部」视图必须保持这个顺序） */
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
  'sortino_ratio',
  'calmar_ratio',
  'avg_drawdown',
  'volatility',
  'expectancy',
  'avg_trade',
  'best_trade',
  'worst_trade',
  'total_commission',
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
  it('与改造前的页面展示顺序逐项一致（scope 只管可见性，不参与排序）', () => {
    expect(METRIC_CARDS.map((m) => m.key)).toEqual(FULL_KEYS);
  });
});

describe('口径标注', () => {
  it('全部 30 张卡片都带非空 hint（提示功能无遗漏）', () => {
    for (const card of METRIC_CARDS) {
      expect(card.hint, `${card.key} 缺少指标说明`).toBeTruthy();
      expect(card.hint.trim().length, `${card.key} 的说明为空`).toBeGreaterThan(0);
    }
  });

  it('两种视图下可见的卡片都带 hint（切换品种后提示不丢失）', () => {
    const views = [
      visibleMetricCards('shared', 'ETH/USDT'), // 共享资金池品种视角（12 张）
      visibleMetricCards('shared', 'all'), // 组合视图（30 张）
      visibleMetricCards('per_symbol', 'ETH/USDT'), // 独立资金池（30 张）
    ];
    for (const view of views) {
      expect(view.length).toBeGreaterThan(0);
      for (const card of view) {
        expect(card.hint, `${card.key} 在可见视图里缺少说明`).toBeTruthy();
      }
    }
  });

  it('年化收益率与卡尔马比率的口径说明包含关键信息', () => {
    const cagr = METRIC_CARDS.find((m) => m.key === 'cagr')!;
    expect(cagr.hint).toContain('年化');
    // 共享资金池品种视角不适用（分子分母不同层级），必须带口径说明
    expect(METRIC_CARDS.find((m) => m.key === 'calmar_ratio')!.hint).toContain('品种视角不适用');
  });
});

describe('visibleMetricCards', () => {
  it('共享资金池 + 单品种视角：只保留 12 张贡献类指标', () => {
    expect(keys('shared', 'ETH/USDT')).toEqual(SYMBOL_KEYS);
  });

  it('共享资金池 + 单品种视角：不含账户级与恒 0 占位指标', () => {
    const shown = keys('shared', 'ETH/USDT');
    for (const hidden of ['sharpe_ratio', 'max_drawdown', 'initial_equity', 'final_equity',
      'equity_peak', 'total_commission', 'sortino_ratio', 'calmar_ratio']) {
      expect(shown).not.toContain(hidden);
    }
  });

  it('共享资金池 + 全部视图：展示全部 30 张', () => {
    expect(METRIC_CARDS).toHaveLength(30);
    expect(keys('shared', 'all')).toHaveLength(30);
  });

  it('独立资金池（或缺省）模式单品种视角：展示全部 30 张', () => {
    expect(keys('per_symbol', 'ETH/USDT')).toHaveLength(30);
    expect(keys(undefined, 'ETH/USDT')).toHaveLength(30);
  });
});

describe('formatMetricValue', () => {
  const specOf = (key: string) => METRIC_CARDS.find((m) => m.key === key)!;

  it('百分比/小数/整数/小时各自带单位', () => {
    expect(formatMetricValue(specOf('total_return'), 12.3456)).toBe('12.35%');
    expect(formatMetricValue(specOf('total_pnl'), 1234.567)).toBe('1234.57');
    expect(formatMetricValue(specOf('total_trades'), 12.6)).toBe('13');
    expect(formatMetricValue(specOf('avg_trade_duration_hours'), 3.5)).toBe('3.50h');
  });
});
