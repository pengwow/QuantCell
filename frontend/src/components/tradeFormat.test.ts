import { describe, expect, it } from 'vitest';

import { fmtNum } from './tradeFormat';

describe('fmtNum（交易表展示边界）', () => {
  it('正常数字按位数格式化', () => {
    expect(fmtNum(1.23456, 4)).toBe('1.2346');
    expect(fmtNum(0, 2)).toBe('0.00');
  });

  it('缺值渲染 — 而不是抛 TypeError（cascade 旧数据 trades 缺 quantity 实录）', () => {
    expect(fmtNum(undefined, 4)).toBe('—');
    expect(fmtNum(null, 4)).toBe('—');
  });

  it('非有限值同样降级（NaN / Infinity 来自缺失字段的乘法）', () => {
    expect(fmtNum(Number.NaN, 4)).toBe('—');
    expect(fmtNum(Number.POSITIVE_INFINITY, 2)).toBe('—');
  });
});
