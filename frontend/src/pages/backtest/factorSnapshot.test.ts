import { describe, expect, it } from 'vitest';
import { findLastIndexLE, buildFactorSnapshotRows } from './factorSnapshot';
import type { BacktestFactors } from '../../types/backtest';

const TS = [1000, 2000, 3000, 4000];

const baseFactors: BacktestFactors = {
  names: ['momentum', 'rsi', 'no_threshold', 'dead_factor'],
  thresholds: {
    momentum: { buy: 0.5, sell: -0.5 },
    rsi: { buy: 70 },
    dead_factor: { buy: 1 },
  },
  time_series: {
    timestamps: TS,
    formatted_times: ['t1', 't2', 't3', 't4'],
    momentum: [0.1, 0.6, 0.8, null],
    rsi: [50, 75, 65, 80],
    no_threshold: [1, 2, 3, 4],
    dead_factor: [null, null, null, null],
  },
  trade_factors: [],
  attribution: {},
};

describe('findLastIndexLE', () => {
  it('精确命中返回该索引', () => {
    expect(findLastIndexLE(TS, 2000)).toBe(1);
  });
  it('落在两 bar 之间返回前一根', () => {
    expect(findLastIndexLE(TS, 2500)).toBe(1);
  });
  it('晚于末 bar 返回最后一根', () => {
    expect(findLastIndexLE(TS, 99999)).toBe(3);
  });
  it('早于首 bar 返回 -1', () => {
    expect(findLastIndexLE(TS, 500)).toBe(-1);
  });
  it('空数组返回 -1', () => {
    expect(findLastIndexLE([], 1000)).toBe(-1);
  });
});

describe('buildFactorSnapshotRows', () => {
  it('正常对齐：双阈值因子区分 long/neutral/short', () => {
    const { rows, alignedTime } = buildFactorSnapshotRows(baseFactors, 2500);
    // 对齐到 index 1
    expect(alignedTime).toBe('t2');
    const rsiRow = rows.find((r) => r.name === 'rsi')!;
    expect(rsiRow.value).toBe(75);
    expect(rsiRow.signal).toBe('long');   // 只配 buy：75 >= 70
    const momRow = rows.find((r) => r.name === 'momentum')!;
    expect(momRow.value).toBe(0.6);
    expect(momRow.signal).toBe('long');   // 0.6 >= 0.5
  });

  it('值在双阈值之间为中性，低于 sell 为空头', () => {
    const f = structuredClone(baseFactors);
    f.time_series.momentum = [0.0, 0.3, -0.9, 0.0];
    const { rows } = buildFactorSnapshotRows(f, 2500);
    const mom = rows.find((r) => r.name === 'momentum')!;
    expect(mom.signal).toBe('neutral');   // -0.5 < 0.3 < 0.5
    const { rows: rows2 } = buildFactorSnapshotRows(f, 3500);
    expect(rows2.find((r) => r.name === 'momentum')!.signal).toBe('short'); // -0.9 <= -0.5
  });

  it('无阈值因子只显示数值 signal=none；null 值 signal=none value=null', () => {
    const { rows } = buildFactorSnapshotRows(baseFactors, 2000);
    expect(rows.find((r) => r.name === 'no_threshold')!.signal).toBe('none');
    const dead = rows.find((r) => r.name === 'dead_factor')!;
    expect(dead.value).toBeNull();
    expect(dead.signal).toBe('none');
  });

  it('早于首 bar 返回空行且无对齐时刻', () => {
    const { rows, alignedTime } = buildFactorSnapshotRows(baseFactors, 500);
    expect(rows).toEqual([]);
    expect(alignedTime).toBeNull();
  });

  it('factors 为空/null 安全返回空', () => {
    expect(buildFactorSnapshotRows(null, 1000).rows).toEqual([]);
    expect(buildFactorSnapshotRows(undefined, 1000).rows).toEqual([]);
    expect(buildFactorSnapshotRows({ names: [], thresholds: {}, time_series: { timestamps: [], formatted_times: [] }, trade_factors: [], attribution: {} }, 1000).rows).toEqual([]);
  });
});
