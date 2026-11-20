/**
 * K 线图深度轮廓 overlay（depthProfile）
 *
 * 在最后可见 K 线右侧空白区，按盘口累计量画横向量条（asks 红 / bids 绿），
 * 效果同 Binance 深度轮廓：离参考价越近累计越大、条越长，半透明不遮挡 K 线。
 *
 * 实现说明：klinecharts v10 的 Overlay 模板只有声明式 createPointFigures，
 * 没有 v9 的 draw 回调；坐标换算用 chart 公开方法（getVisibleRange /
 * getOffsetRightDistance / getBarSpace / getDataList）与 yAxis.convertToPixel
 * （自动兼容 y 轴反转，不手工线性映射）。本模块不接 React：数据由 ChartPage
 * 接线（updateDepthSnapshot / setDepthProfileSymbol），注册统一走
 * registerDepthProfileOverlay；渲染效果在接线后浏览器人工确认。
 */
import {
  registerOverlay,
  type OverlayCreateFiguresCallbackParams,
  type OverlayFigure,
  type OverlayTemplate,
} from 'klinecharts';

export interface DepthProfileSnapshot {
  symbol: string;
  /** [[price, qty], ...]，bids 升序 / asks 升序（内部转发口径） */
  bids: [number, number][];
  asks: [number, number][];
  /** 毫秒时间戳，仅用于调试，不参与绘制 */
  timestamp?: number;
}

// 模块级缓存：SHM 单票场景只有一张当前快照，避免把状态塞进 overlay extendData
let snapshot: DepthProfileSnapshot | null = null;
// 当前生效品种（WS 口径，如 BTCUSDT），切换品种时由接线侧同步
let activeSymbol = '';

/** 接线侧喂入最新深度快照；下一次画布绘制即生效 */
export function updateDepthSnapshot(next: DepthProfileSnapshot): void {
  if (!next?.bids?.length || !next?.asks?.length) return;
  snapshot = next;
}

/** 设置 overlay 生效的品种；symbol 不匹配的快照会被忽略，防止切品种串数据 */
export function setDepthProfileSymbol(symbol: string): void {
  activeSymbol = (symbol || '').toUpperCase();
}

// 半透明红绿：涨跌语义色取自 palette success #1a7f37 / error #d1242f，
// 但深度图需要固定的 0.35 alpha 条带底——palette 没有带 alpha 的语义槽位，
// 靠 hex→rgba 拼接又会引入取整误差（0.349 vs 0.35），故保留字面量（离散豁免：alpha 变体）。
const BUY_COLOR = 'rgba(26, 127, 55, 0.35)';
const SELL_COLOR = 'rgba(209, 36, 47, 0.35)';
const BAR_HEIGHT = 3;

/** 自盘口向外的累计直方条（price 越贴近参考价 cum 越大） */
const buildProfile = (
  levels: [number, number][],
  referencePrice: number,
  side: 'ask' | 'bid',
): { price: number; qty: number; cum: number }[] => {
  // bids 取 ≤参考价、asks 取 ≥参考价，均按贴近盘口排序
  const filtered = levels.filter(([price]) =>
    side === 'bid' ? price <= referencePrice : price >= referencePrice,
  );
  const ordered = side === 'bid' ? [...filtered].sort((a, b) => b[0] - a[0]) : filtered;
  let cum = 0;
  return ordered.map(([price, qty]) => ({ price, qty, cum: (cum += qty) }));
};

const depthProfileTemplate: OverlayTemplate = {
  name: 'depthProfile',
  // 常驻装饰层：无锚点、锁死、不参与交互；figures 全部 ignoreEvent
  lock: true,
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: false,
  needDefaultYAxisFigure: false,
  createPointFigures: ({
    chart,
    bounding,
    yAxis,
  }: OverlayCreateFiguresCallbackParams<unknown>): OverlayFigure[] => {
    if (!snapshot || !yAxis || !activeSymbol) return [];
    if (snapshot.symbol.toUpperCase() !== activeSymbol) return [];

    // 右侧空白区：主绘制区右缘 → canvas 右缘（不含 y 轴），没有留白就不画
    const rightGap = chart.getOffsetRightDistance();
    if (rightGap <= BAR_HEIGHT + 4) return [];
    const startX = bounding.right - rightGap;
    const usableWidth = Math.max(1, rightGap - 4);

    // 条形长度比例尺：两侧累计统一归一，量级可直接对比
    const referenceData = chart.getDataList();
    const visibleRange = chart.getVisibleRange();
    const lastBar = referenceData[visibleRange.to];
    if (!lastBar) return [];
    const referencePrice = lastBar.close;
    if (!Number.isFinite(referencePrice)) return [];

    const asks = buildProfile(snapshot.asks, referencePrice, 'ask');
    const bids = buildProfile(snapshot.bids, referencePrice, 'bid');
    if (!asks.length || !bids.length) return [];
    const maxCum = Math.max(asks[asks.length - 1].cum, bids[bids.length - 1].cum);
    if (!(maxCum > 0)) return [];

    const halfHeight = BAR_HEIGHT / 2;
    const paneTop = bounding.top;
    const paneBottom = bounding.top + bounding.height;
    const figures: OverlayFigure[] = [];

    const pushBars = (
      profile: { price: number; cum: number }[],
      color: string,
    ) => {
      for (const bar of profile) {
        const yCenter = yAxis.convertToPixel(bar.price);
        // 档位超出可视价格范围（含上下缓冲半格）则跳过，避免把条画进坐标轴区
        if (yCenter < paneTop - halfHeight || yCenter > paneBottom + halfHeight) continue;
        const width = Math.max(1, (bar.cum / maxCum) * usableWidth);
        figures.push({
          type: 'rect',
          ignoreEvent: true,
          attrs: {
            x: startX,
            y: yCenter - halfHeight,
            width,
            height: BAR_HEIGHT,
            fill: color,
          },
        });
      }
    };

    pushBars(asks, SELL_COLOR);
    pushBars(bids, BUY_COLOR);
    return figures;
  },
};

let registered = false;

/** 幂等注册 overlay 模板；接线侧（T11）在图表初始化时调用一次即可 */
export function registerDepthProfileOverlay(): void {
  if (registered) return;
  registerOverlay(depthProfileTemplate);
  registered = true;
}
