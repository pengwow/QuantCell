import { describe, expect, it } from 'vitest';
import { formatCashGrouped, formatFeePercent } from './bcFormat';

describe('formatCashGrouped', () => {
  it('千分位分组', () => {
    expect(formatCashGrouped(1000000)).toBe('1,000,000');
    expect(formatCashGrouped(100000)).toBe('100,000');
  });

  it('小数资金保留小数', () => {
    expect(formatCashGrouped(1000.5)).toBe('1,000.5');
  });
});

describe('formatFeePercent', () => {
  it('常规费率', () => {
    expect(formatFeePercent(0.001)).toBe('0.1%');
    expect(formatFeePercent(0.0005)).toBe('0.05%');
    expect(formatFeePercent(0.05)).toBe('5%');
  });

  it('零费率不吞零', () => {
    expect(formatFeePercent(0)).toBe('0%');
  });
});
