import { describe, expect, it } from 'vitest';
import type { KLineData } from 'klinecharts';
import {
  buildHeikinAshiRows,
  buildHlcAreaRows,
  buildRenkoBricks,
  buildRangeBars,
} from './priceChartTransforms';

const bar = (timestamp: number, o: number, h: number, l: number, c: number, v = 10): KLineData =>
  ({ timestamp, open: o, high: h, low: l, close: c, volume: v } as KLineData);

describe('priceChartTransforms', () => {
  it('heikin_ashi: 首根 open=(o+c)/2，close=四价均值，high/low 包络开收', () => {
    const rows = [bar(1, 10, 12, 8, 11), bar(2, 11, 14, 9, 13)];
    const [first, second] = buildHeikinAshiRows(rows);
    expect(first.open).toBeCloseTo(10.5);
    expect(first.close).toBeCloseTo((10 + 12 + 8 + 11) / 4);
    expect(first.high).toBeCloseTo(Math.max(12, 10.5, first.close));
    expect(second.open).toBeCloseTo((first.open + first.close) / 2);
  });

  it('hlc_area: close 压缩为 (h+l+c)/3，OH 与原值一致', () => {
    const rows = [bar(1, 10, 15, 5, 13)];
    const [row] = buildHlcAreaRows(rows);
    expect(row.open).toBe(10);
    expect(row.close).toBeCloseTo((15 + 5 + 13) / 3);
  });

  it('renko: 上涨达 2 格产生 2 块砖；反向不足 2 格不翻转（过滤噪音）', () => {
    const rows = [bar(1, 100, 100.6, 99.4, 100), bar(2, 100, 101.2, 99.8, 101)];
    // 上涨 1.0 = 2 格（boxSize 0.5）→ 2 块砖
    const bricks = buildRenkoBricks(rows, { boxSize: 0.5 });
    expect(bricks.length).toBe(2);
    expect(bricks[0].close).toBeCloseTo(100.5);
    expect(bricks[1].close).toBeCloseTo(101);
    // 回落 0.4 格（<2 格反转阈值）不产生任何砖
    expect(buildRenkoBricks([...rows, bar(3, 101, 101.1, 100.6, 100.6)], { boxSize: 0.5 })).toHaveLength(2);
  });

  it('range: 按区间尺寸切分且 timestamp 严格递增', () => {
    const rows = [bar(1, 100, 100.5, 99.5, 100), bar(2, 100, 103, 99.8, 103)];
    const bars = buildRangeBars(rows, { rangeSize: 1 });
    expect(bars.length).toBe(3);
    bars.forEach((b, i) => {
      if (i > 0) expect(b.timestamp).toBeGreaterThan(bars[i - 1].timestamp);
      expect(Math.abs(b.close - b.open)).toBeCloseTo(1);
    });
  });

  it('数据不足 2 根或含 NaN 行时安全返回空/跳过', () => {
    expect(buildRenkoBricks([bar(1, 1, 1, 1, 1)])).toHaveLength(0);
    expect(buildRangeBars([bar(1, 1, 1, 1, NaN), bar(2, 1, 1, 1, 2)])).toHaveLength(0);
  });
});
