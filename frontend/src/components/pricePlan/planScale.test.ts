import { describe, expect, it } from 'vitest';
import { computePriceScale } from './planScale';

describe('computePriceScale 纵轴范围', () => {
  it('levels 与现价共同决定范围，上下留 10% 余量', () => {
    // 价位跨度 95~105，现价 102 落在其中 → raw 范围 95~105，pad = 1
    const s = computePriceScale({ levels: [95, 100, 105], currentPrice: 102 });
    expect(s?.min).toBeCloseTo(94);
    expect(s?.max).toBeCloseTo(106);
  });

  it('现价出界时把现价纳入范围', () => {
    // raw 98~110，pad = 1.2
    const s = computePriceScale({ levels: [98, 100, 102], currentPrice: 110 });
    expect(s?.min).toBeCloseTo(96.8);
    expect(s?.max).toBeCloseTo(111.2);
  });

  it('K 线高低一并纳入', () => {
    const s = computePriceScale({
      levels: [100],
      currentPrice: 100,
      candleHighs: [108, 106],
      candleLows: [92, 94],
    });
    // raw 92~108，pad = 1.6
    expect(s?.min).toBeCloseTo(90.4);
    expect(s?.max).toBeCloseTo(109.6);
  });

  it('无任何有效输入返回 null（调用方跳过绘制）', () => {
    expect(computePriceScale({ levels: [], currentPrice: null })).toBeNull();
  });
});
