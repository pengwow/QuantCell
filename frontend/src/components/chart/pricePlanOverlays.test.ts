/**
 * planToOverlayLevels 纯映射守护：非法价位过滤 + mid 档不画线 + 空输入。
 * createOverlay/clear 链路复用 fillMarkers 已验证的 signalTag 契约，不做 chart 级单测。
 */
import { describe, it, expect } from 'vitest';
import { planToOverlayLevels } from './pricePlanOverlays';
import type { PricePlan } from '../../types/pricePlan';

const mkPlan = (levels: Partial<PricePlan['levels'][number]>[]): PricePlan =>
  ({
    strategy: 'test',
    ref_price: 100,
    levels,
    summary: {},
    warnings: [],
  }) as unknown as PricePlan;

describe('planToOverlayLevels', () => {
  it('映射 buy/sell/tp 档位（price/action/label）', () => {
    const plan = mkPlan([
      { index: 0, price: 99, action: 'buy', target_position: 0.1, label: '低位挂买' },
      { index: 1, price: 100, action: 'mid', target_position: 0, label: '中枢' },
      { index: 2, price: 105, action: 'tp', target_position: 0, label: '篮子止盈' },
      { index: 3, price: 97, action: 'sell', target_position: 0.2, label: '高位挂卖' },
    ]);
    expect(planToOverlayLevels(plan)).toEqual([
      { price: 99, action: 'buy', label: '低位挂买' },
      { price: 105, action: 'tp', label: '篮子止盈' },
      { price: 97, action: 'sell', label: '高位挂卖' },
    ]);
  });

  it('过滤非法价位（0 / 负数 / NaN）与空计划', () => {
    const plan = mkPlan([
      { index: 0, price: 0, action: 'buy', target_position: 0.1, label: 'x' },
      { index: 1, price: NaN, action: 'sell', target_position: 0.1, label: 'y' },
      { index: 2, price: -5, action: 'buy', target_position: 0.1, label: 'z' },
      { index: 3, price: 120, action: 'buy', target_position: 0.2, label: 'ok' },
    ]);
    expect(planToOverlayLevels(plan)).toEqual([{ price: 120, action: 'buy', label: 'ok' }]);
    expect(planToOverlayLevels(mkPlan([]))).toEqual([]);
    expect(planToOverlayLevels(null)).toEqual([]);
    expect(planToOverlayLevels(undefined)).toEqual([]);
  });
});
