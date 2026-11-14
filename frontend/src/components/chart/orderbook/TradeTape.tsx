/**
 * 成交流水（Trade Tape）：本地 WS 'trades' 推送，列表由新到旧、最多保留 30 条。
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { wsService } from '@/services/websocketService';
import './orderbook.css';

interface TradeItem {
  symbol?: string;
  price: number;
  quantity: number;
  /** 成交时间（毫秒时间戳） */
  time: number;
  /** true = 买方为挂单方，即主动卖 */
  is_buyer_maker: boolean;
}

interface TapeRow {
  /** 渲染序号，避免同价格/时间的重复成交撞 key */
  id: number;
  price: number;
  quantity: number;
  time: number;
  side: 'buy' | 'sell';
}

interface TradeTapeProps {
  /** ws 品种口径，如 BTCUSDT */
  symbol: string;
  /** 最多保留条数 */
  limit?: number;
}

export function TradeTape({ symbol, limit = 30 }: TradeTapeProps) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<TapeRow[]>([]);
  const seqRef = useRef(0);

  useEffect(() => {
    const handler = (data: unknown) => {
      // 后端按小窗口攒批：data 是成交数组；非数组或空批直接忽略
      if (!Array.isArray(data)) return;
      const batch = (data as TradeItem[]).filter(
        (item) => item && (!item.symbol || item.symbol.toUpperCase() === symbol.toUpperCase()),
      );
      if (!batch.length) return;
      setRows((prev) => {
        const incoming: TapeRow[] = batch.map((item) => ({
          id: ++seqRef.current,
          price: item.price,
          quantity: item.quantity,
          time: item.time,
          side: item.is_buyer_maker ? 'sell' : 'buy',
        }));
        return [...incoming, ...prev].slice(0, limit);
      });
    };

    wsService.on('trades', handler);
    return () => wsService.off('trades', handler);
  }, [symbol, limit]);

  if (!rows.length) {
    return <div className="ob-empty">{t('chart.orderbook.noData')}</div>;
  }

  return (
    <div className="ob-tape">
      <div className="ob-head">
        <span>{t('chart.orderbook.price')}</span>
        <span>{t('chart.orderbook.amount')}</span>
        <span />
      </div>
      <div className="ob-rows">
        {rows.map((row) => (
          <div className={`ob-row ob-tapetrade`} key={row.id}>
            <span className={`ob-price ${row.side === 'buy' ? 'is-up' : 'is-down'}`}>
              {row.price}
            </span>
            <span className="ob-qty">{row.quantity}</span>
            <span className="ob-time">
              {new Date(row.time).toLocaleTimeString('en-GB', { hour12: false })}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
