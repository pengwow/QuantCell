import { describe, expect, it } from 'vitest';
import { pnlDeltaPp } from './HomePage';

describe('pnlDeltaPp（KPI2「较昨日同期」）', () => {
  it('是百分点差，不是百分比变化', () => {
    // 今日 1.20% vs 昨日同期 1.00% → +0.20pp（百分比变化会是 +20%）
    expect(pnlDeltaPp(1.2, 1.0)).toBeCloseTo(0.2, 10);
    expect(pnlDeltaPp(0.5, 1.5)).toBeCloseTo(-1, 10);
  });

  it('任一值为 null 返回 null（该段不渲染，不写 0.00pp）', () => {
    expect(pnlDeltaPp(null, 1)).toBeNull();
    expect(pnlDeltaPp(1, null)).toBeNull();
    expect(pnlDeltaPp(null, null)).toBeNull();
  });

  it('两位小数内为 0 时归零，避免 -0.00 的假方向', () => {
    expect(pnlDeltaPp(1.00001, 1.0)).toBe(0);
    expect(pnlDeltaPp(1.0, 1.00004)).toBe(0);
  });
});
