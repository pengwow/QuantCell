/**
 * 订单簿面板：中间价上卖下买、「从盘口向外累计」的横向深度条。
 * 数据来源：本地 WS 'depth' 推送为主（由 ChartPage 统一持有订阅），
 * REST 快照仅作进入时兜底；两路 symbol 均为 WS 口径（如 BTCUSDT）。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { marketdataApi, type DepthLevel } from '@/api/marketdataApi';
import { wsService } from '@/services/websocketService';
import './orderbook.css';

export interface OrderbookRow {
  price: number;
  qty: number;
  /** 自盘口到该档的累计量（用于深度条宽度） */
  cum: number;
}

interface OrderBookPanelProps {
  /** ws 品种口径，如 BTCUSDT */
  symbol: string;
  /** 渲染档数，与 WS 推流深度档数共用同一配置 */
  depthLevels: 10 | 20;
}

// 自盘口向外累计：显示序上靠盘口的行短、远端行长（两侧对称漏斗）
const cumulate = (levels: DepthLevel[]): OrderbookRow[] => {
  let cum = 0;
  return levels.map(([price, qty]) => ({ price, qty, cum: (cum += qty) }));
};

/** bids/asks 为 [[price, qty], ...] 二元组（内部与 REST 口径一致：bids/asks 均为升序） */
const buildRows = (rawBids: DepthLevel[], rawAsks: DepthLevel[]) => {
  const bids = cumulate([...rawBids].sort((a, b) => b[0] - a[0])); // best bid 置顶，向下延伸
  const asks = cumulate([...rawAsks].sort((a, b) => a[0] - b[0])).reverse(); // 最高卖价置顶
  const maxCum = Math.max(
    bids.length ? bids[bids.length - 1].cum : 0,
    asks.length ? asks[asks.length - 1].cum : 0,
  );
  return { bids, asks, maxCum };
};

export function OrderBookPanel({ symbol, depthLevels }: OrderBookPanelProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<ReturnType<typeof buildRows> | null>(null);

  useEffect(() => {
    let cancelled = false;

    // WS 推送 payload 原样透传给 listener（不含信封），这里只做收窄与品种过滤
    const handler = (data: unknown) => {
      const d = data as { symbol?: string; bids?: DepthLevel[]; asks?: DepthLevel[] } | null;
      if (!d?.bids?.length || !d?.asks?.length) return;
      if (d.symbol && d.symbol.toUpperCase() !== symbol.toUpperCase()) return;
      if (!cancelled) setRows(buildRows(d.bids, d.asks));
    };

    wsService.on('depth', handler);
    // REST 快照兜底：进入页面尚未收到推送前先渲染一帧；失败则静默等 WS
    marketdataApi
      .getDepthSnapshot(symbol, depthLevels)
      .then((snap) => {
        if (!cancelled && snap?.bids?.length) setRows(buildRows(snap.bids, snap.asks));
      })
      .catch(() => {
        /* 等待 WS 推送 */
      });

    return () => {
      cancelled = true;
      wsService.off('depth', handler);
    };
  }, [symbol, depthLevels]);

  if (!rows || (!rows.bids.length && !rows.asks.length)) {
    return <div className="ob-empty">{t('chart.orderbook.noData')}</div>;
  }

  const bestBid = rows.bids[0]?.price ?? 0;
  const bestAsk = rows.asks[rows.asks.length - 1]?.price ?? 0;
  // 价差 = 最低卖价 - 最高买价；旧实现写反（bestBid - bestAsk 恒为负被 clamp 成 0.00）
  const spread = Math.max(bestAsk - bestBid, 0);

  const renderRow = (row: OrderbookRow, side: 'ask' | 'bid') => (
    <div className={`ob-row ob-${side}`} key={`${side}-${row.price}`}>
      <span className={`ob-price ${side === 'ask' ? 'is-down' : 'is-up'}`}>{row.price}</span>
      <span className="ob-qty">{row.qty}</span>
      <span
        className="ob-bar"
        style={{ width: `${rows.maxCum > 0 ? (row.cum / rows.maxCum) * 100 : 0}%` }}
      />
    </div>
  );

  return (
    <div className="ob-book">
      <div className="ob-head">
        <span>{t('chart.orderbook.price')}</span>
        <span>{t('chart.orderbook.amount')}</span>
      </div>
      <div className="ob-rows">
        {rows.asks.map((r) => renderRow(r, 'ask'))}
        <div className="ob-mid">
          <span className="ob-mid-value">{spread.toFixed(2)}</span>
          <span className="ob-mid-label">{t('chart.orderbook.spread')}</span>
        </div>
        {rows.bids.map((r) => renderRow(r, 'bid'))}
      </div>
    </div>
  );
}
