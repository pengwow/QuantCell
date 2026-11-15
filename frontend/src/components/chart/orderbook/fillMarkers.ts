/**
 * 策略成交标记：回放（backtestApi.getBacktestDetail().fills_detail）+ 实时（ws 'strategy.fill'）。
 *
 * 绘制复用 ChartShell 的 signalTag overlay 先例（下单信号标注）：
 * 覆盖层 extendData 统一放绘制数据（v10 契约 coordinates 不携带 point 级 extendData），
 * source 字段用于回放/实时两组标记的幂等增删互不干扰。
 */
import type { Chart, Nullable } from 'klinecharts';

export interface FillPoint {
  /** 成交时间（毫秒） */
  timestamp: number;
  side: 'buy' | 'sell';
  price: number;
  quantity: number;
  source: 'backtest' | 'live';
}

const BUY_COLOR = '#00E676';
const SELL_COLOR = '#FF5252';

// 成交 ts 向下取整到所属 bar 起点（barMs 见 extraIndicators.periodToMs），保证落点在 K 网格上
export const alignToBar = (ts: number, barMs: number): number =>
  barMs > 0 ? Math.floor(ts / barMs) * barMs : ts;

/** 单笔成交 → signalTag 标注（两点同价：signalTag 需两点形态，连线退化为点即贴在成交价处） */
export const createFillMarker = (chart: Nullable<Chart>, fill: FillPoint): void => {
  if (!chart || !Number.isFinite(fill.price) || fill.price <= 0 || !Number.isFinite(fill.timestamp)) return;
  const ts = Math.floor(fill.timestamp);
  try {
    chart.createOverlay({
      name: 'signalTag',
      lock: true,
      extendData: {
        text: fill.side === 'buy' ? 'B' : 'S',
        color: fill.side === 'buy' ? BUY_COLOR : SELL_COLOR,
        side: fill.side,
        source: fill.source,
        quantity: fill.quantity,
      },
      points: [
        { timestamp: ts, value: fill.price },
        { timestamp: ts, value: fill.price },
      ],
    });
  } catch (e) {
    console.warn('[FillMarkers] Failed to create fill marker:', e);
  }
};

/** 按 source 清除标记（回放重画前/换品种时调用，幂等：不存在则空操作） */
export const clearFillMarkers = (chart: Nullable<Chart>, source: FillPoint['source']): void => {
  if (!chart) return;
  const overlays = chart.getOverlays({ name: 'signalTag' }) || [];
  for (const o of overlays) {
    const ext = o.extendData as { source?: string } | null | undefined;
    if (ext?.source === source) {
      try {
        chart.removeOverlay({ id: o.id });
      } catch (e) {
        console.warn('[FillMarkers] Failed to remove fill marker:', e);
      }
    }
  }
};
