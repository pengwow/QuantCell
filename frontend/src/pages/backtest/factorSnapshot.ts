import type { BacktestFactors, FactorSnapshotRow } from '../../types/backtest';

// 二分找最后一个 <= t 的时间戳索引；-1 表示 t 早于首 bar
export function findLastIndexLE(timestamps: number[], t: number): number {
  let lo = 0;
  let hi = timestamps.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (timestamps[mid] <= t) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans;
}

export interface FactorSnapshotResult {
  rows: FactorSnapshotRow[];
  alignedTime: string | null;  // 快照值实际取自的 bar 时刻
}

// 按播放时刻构建当前因子快照行。
// 按时间二分对齐而非数组索引直取：K 线与因子序列长度可能不一致，时间对齐总是正确。
export function buildFactorSnapshotRows(
  factors: BacktestFactors | null | undefined,
  currentMs: number,
): FactorSnapshotResult {
  if (!factors?.names?.length || !factors.time_series?.timestamps?.length) {
    return { rows: [], alignedTime: null };
  }
  const ts = factors.time_series.timestamps;
  const i = findLastIndexLE(ts, currentMs);
  if (i < 0) return { rows: [], alignedTime: null };

  const thresholds = factors.thresholds ?? {};
  const rows = factors.names.map((name) => {
    const col = factors.time_series[name];
    const raw = col ? col[i] : undefined;
    const value = typeof raw === 'number' && Number.isFinite(raw) ? raw : null;

    const th = thresholds[name] ?? {};
    const hasBuy = typeof th.buy === 'number';
    const hasSell = typeof th.sell === 'number';
    // 阈值可能只配单侧，缺失的一侧不参与判定
    let signal: FactorSnapshotRow['signal'] = 'none';
    if (value !== null && (hasBuy || hasSell)) {
      if (hasBuy && value >= (th.buy as number)) signal = 'long';
      else if (hasSell && value <= (th.sell as number)) signal = 'short';
      else signal = 'neutral';
    }
    return {
      name,
      value,
      buy: hasBuy ? th.buy : undefined,
      sell: hasSell ? th.sell : undefined,
      signal,
    };
  });
  return { rows, alignedTime: factors.time_series.formatted_times?.[i] ?? null };
}
