import { describe, expect, it } from 'vitest';
import { formatCashGrouped, formatFeePercent, formatElapsedCompact } from './bcFormat';

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

describe('formatElapsedCompact', () => {
  it('分级形制（demo「耗时 42s」）', () => {
    expect(formatElapsedCompact(42)).toBe('42s');
    expect(formatElapsedCompact(192)).toBe('3m 12s');
    expect(formatElapsedCompact(7500)).toBe('2h 05m');
    expect(formatElapsedCompact(0)).toBe('0s');
  });

  it('≥48h（陈旧任务）与非法值 → null，重载省略比长串更诚实', () => {
    expect(formatElapsedCompact(1459037)).toBeNull();
    expect(formatElapsedCompact(-1)).toBeNull();
    expect(formatElapsedCompact(NaN)).toBeNull();
  });
});
