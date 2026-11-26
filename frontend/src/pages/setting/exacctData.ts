/**
 * 账户总览（/setting/exchange-account）—— 后端快照契约 + 视图归一化纯函数。
 * 数据本体来自 GET /exchanges/account-snapshot（交易所在真实/模拟端点拉取），
 * 本模块只做：类型契约、ccxt 状态映射、估值聚合、CSV 导出。无 mock 数据。
 */

export interface BalanceRow {
  currency: string;
  free: number;
  used: number;
  priceUsdt: number | null;
  valueUsdt: number;
}

export interface PositionRow {
  symbol: string;
  pair: string;
  side: 'long' | 'short';
  mode: string;
  leverage: number;
  qty: number;
  entry: number;
  mark: number;
  notional: number;
  unrealized: number;
  initialMargin: number;
  maintMargin: number;
  liqPrice: number;
  breakeven: number;
  // 币安「保证金比率」= 维持保证金/保证金余额（%），清理逾期预警口径
  marginRatio: number;
}

export interface OrderRow {
  id: string;
  time: number;
  pair: string;
  type: 'limit' | 'market';
  side: 'buy' | 'sell';
  price: number;
  qty: number;
  filled: number;
  status: string; // ccxt 原始状态，展示前经 mapOrderStatus
}

export interface TradeRow {
  id: string;
  time: number;
  pair: string;
  side: 'buy' | 'sell';
  price: number;
  qty: number;
  fee: number;
}

export interface FuturesTotals {
  walletUsdt: number;
  unrealizedUsdt: number;
  equityUsdt: number;
  availableUsdt: number;
  usedUsdt: number;
}

/** GET /exchanges/account-snapshot 的 data 载荷 */
export interface AccountSnapshot {
  exchange: string;
  configured: boolean;
  env: 'live' | 'testnet' | string;
  mode: string;
  quote: string;
  fetchedAt?: number;
  spot: { balances: BalanceRow[]; totalUsdt: number };
  futures: {
    totals: FuturesTotals | null;
    equityUsdt: number | null;
    unrealizedUsdt: number;
    positions: PositionRow[];
  };
  orders: OrderRow[];
  trades: TradeRow[];
  historySymbols?: string[];
  errors?: Record<string, string>;
}

export type OrderStatus = 'open' | 'partial' | 'filled' | 'canceled';

/** ccxt 订单状态 → 页面筛选语义：未成交但有成交量即「部分成交」，closed 即「已成交」 */
export const mapOrderStatus = (status: string, filled: number): OrderStatus => {
  if (status === 'closed') return 'filled';
  if (status === 'open') return filled > 0 ? 'partial' : 'open';
  return 'canceled'; // canceled / expired / rejected 等
};

export const orderInViewStatus = (o: OrderRow): OrderStatus => mapOrderStatus(o.status, o.filled);

/** 持仓浮动盈亏：多 (mark-entry) / 空 (entry-mark)，数量取绝对值 */
export const positionPnl = (p: Pick<PositionRow, 'qty' | 'entry' | 'mark' | 'side'>) =>
  Math.abs(p.qty) * (p.side === 'long' ? p.mark - p.entry : p.entry - p.mark);

/** 现货分布/估值的通用聚合：资产行 + 合约权益合成一个「币种 → USDT 价值」映射 */
export function assetDonut(
  balances: BalanceRow[],
  extra: { name: string; value: number },
  topN = 6
): Array<{ name: string; value: number }> {
  const merged = new Map<string, number>();
  for (const b of balances) {
    if (b.valueUsdt > 0) {
      merged.set(b.currency, (merged.get(b.currency) ?? 0) + b.valueUsdt);
    }
  }
  const rows = [...merged.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
  if (extra.value > 0) {
    const hit = rows.find((r) => r.name === extra.name);
    if (hit) hit.value += extra.value;
    else rows.push({ ...extra });
    rows.sort((a, b) => b.value - a.value);
  }
  if (rows.length <= topN) return rows.map((r) => ({ name: r.name, value: round2(r.value) }));
  const head = rows.slice(0, topN).map((r) => ({ name: r.name, value: round2(r.value) }));
  const rest = rows.slice(topN).reduce((s, r) => s + r.value, 0);
  head.push({ name: 'OTHER', value: round2(rest) });
  return head;
}

const round2 = (n: number) => Number(n.toFixed(2));

/**
 * 行数组导出为 CSV 文本：UTF-8 BOM（Excel 直开不乱码）+ CRLF；
 * 含逗号 / 引号 / 换行的单元格按 RFC 4180 加引号转义。
 */
export function toCsv(headers: string[], rows: (string | number)[][]): string {
  const esc = (cell: string | number) => {
    const s = String(cell);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return '\uFEFF' + [headers, ...rows].map((r) => r.map(esc).join(',')).join('\r\n');
}

/** 千分位定长小数 */
export const fmtNum = (n: number, digits = 2) =>
  (Number.isFinite(n) ? n : 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** 带符号数字（正数补 +） */
export const fmtSigned = (n: number, digits = 2) =>
  `${n >= 0 ? '+' : ''}${fmtNum(n, digits)}`;
