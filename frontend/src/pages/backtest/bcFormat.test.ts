import { describe, expect, it } from 'vitest';
import { buildEquityGeometry, formatCashGrouped, formatFeePercent, formatElapsedCompact } from './bcFormat';

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

describe('buildEquityGeometry', () => {
  it('单调上涨序列：首点贴底、末点贴顶，面积路径合到基线', () => {
    const geo = buildEquityGeometry([0, 50, 100]);
    // y 轴向下：值大 → y 小（贴 top=8）
    expect(geo.line.startsWith('M0.00,172.00')).toBe(true);
    expect(geo.line.endsWith('640.00,8.00')).toBe(true);
    expect(geo.area).toContain(`640.00,172.00 L0,172.00`);
    expect(geo.lastX).toBeCloseTo(640);
    expect(geo.lastY).toBeCloseTo(8);
    expect(geo.flat).toBe(false);
  });

  it('下跌序列方向反转、平线 flat 不画面积', () => {
    const down = buildEquityGeometry([100, 50, 0]);
    expect(down.line.startsWith('M0.00,8.00')).toBe(true);
    const flat = buildEquityGeometry([1000, 1000, 1000]);
    expect(flat.flat).toBe(true);
    expect(flat.area).toBe('');
    expect(flat.lastY).toBeCloseTo((8 + 172) / 2);
  });
});
