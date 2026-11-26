/**
 * Worker 交易 Tab（币安式四页签：仓位 / 当前委托 / 历史委托 / 历史成交）
 *
 * 旧版单张合并表（成交+挂单靠状态列区分）按业内标准拆分——交易者最高频的问题是
 * 「现在持有什么、亏多少、离强平多远」，仓位是默认页签且字段最全（对齐 Binance/OKX/Bybit）：
 * - 仓位：worker_positions（live/testnet 由 LiveTradeSync.sync_positions 以交易所为准对账落库，
 *   10s 富化杠杆/两平价/强平价/保证金比率；paper 引擎快照，富化列显示 —）
 * - 当前委托 / 历史委托：GET /strategy/orders（订单表由成交回推 + OPEN 挂单）
 * - 历史成交：GET /monitoring/trades 逐笔回报（服务端分页 + 筛选 + CSV）
 *
 * 资产/资金流水页签刻意不做：资产是账户级概念（交易所账户总览页承担），
 * per-worker 资金费无数据链路（已实现盈亏/手续费已在历史成交）。
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Tabs,
  Tooltip,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
import DataTable from '@/components/ui/DataTable';
import { formatQuantity, formatTimestamp, formatUSD, truncateId } from '@/utils/format';
import { downloadCsv, timestampedFilename } from '@/utils/exportCsv';
import type { OrderInfo } from '@/types/worker';
import type { PositionInfo, Side, PositionSide, TradeQueryParams } from '@/types/worker';

const { RangePicker } = DatePicker;

// 状态 -> §6.2 chip 语义档。订单表只写 FILLED（成交回推）与 OPEN（挂单）
const STATUS_CHIP_CLS: Record<string, string> = {
  OPEN: ' info',      // 进行中（带 pulse 圆点）
  FILLED: ' ok',      // 已成交
  CANCELED: ' quiet', // 已撤销
  REJECTED: ' down',  // 已拒绝
};

// 状态 -> i18n key（未知状态回退显示原始英文枚举）
const STATUS_LABEL_KEYS: Record<string, string> = {
  OPEN: 'order_status_open',
  FILLED: 'order_status_filled',
  CANCELED: 'order_status_canceled',
  REJECTED: 'order_status_rejected',
};

// 方向枚举：canonical 小写（铁律1），显示标签走 i18n（买入/卖出）
const SIDE_OPTIONS: Side[] = ['buy', 'sell'];

// 订单类型 -> i18n key（未知类型回退显示原始英文枚举）
const ORDER_TYPE_LABEL_KEYS: Record<string, string> = {
  MARKET: 'order_type_market',
  LIMIT: 'order_type_limit',
  STOP: 'order_type_stop',
  STOP_MARKET: 'order_type_stop_market',
  TAKE_PROFIT: 'order_type_take_profit',
  TAKE_PROFIT_MARKET: 'order_type_take_profit_market',
};

// 订单行模型（成交历史页另由 MergedTradeRow 承载）
interface OrderRow {
  key: string;
  order_id: string;
  symbol: string;
  side: string;
  position_side?: PositionSide;
  reduce_only?: boolean;
  order_type: string;
  quantity: number;
  price?: number | null;
  avg_fill_price?: number | null;
  filled_quantity: number;
  status: string;
  created_at: string;
}

interface MergedTradeRow {
  key: string;
  order_id: string;
  symbol: string;
  side: string;
  position_side?: PositionSide;
  reduce_only?: boolean;
  order_type: string;
  quantity: number;
  avg_fill_price?: number | null;
  filled_quantity: number;
  status: string;
  /** 配对回填后的已实现盈亏（平仓 finalize 行） */
  realized_pnl?: number | null;
  created_at: string;
}

interface FilterValues {
  symbol?: string;
  side?: string;
  order_type?: string;
  time_range?: [Dayjs, Dayjs];
}

interface WorkerOrderTabProps {
  workerId: number;
  /** tab 是否激活；激活时才进行 3s 轮询 */
  active?: boolean;
}

// §6.7 分页档位：12 的倍数（与全站 DataTable 同一套）
const PAGE_SIZE = 12;

// 导出 CSV 时单次拉取的行数上限（orders/trades 接口 page_size 上限均为 100）
const EXPORT_MAX_ROWS = 100;

// 订单接口参数（当前委托/历史委托共用；status/exclude_open 互斥二选一）
const orderParamsOf = (
  applied: FilterValues,
  targetPage: number,
  targetSize: number,
  mode: { status: 'OPEN' } | { exclude_open: true },
) => ({
  symbol: applied.symbol || undefined,
  side: applied.side || undefined, // 交易方向 buy/sell（仓位页签的 side 是 long/short，语义不同）
  order_type: applied.order_type || undefined,
  ...(applied.time_range?.length === 2
    ? {
        start_time: applied.time_range[0].toISOString(),
        end_time: applied.time_range[1].toISOString(),
      }
    : {}),
  ...mode,
  page: targetPage,
  page_size: targetSize,
});

const tradeParamsOf = (applied: FilterValues, targetPage: number, targetSize: number): TradeQueryParams => ({
  symbol: applied.symbol || undefined,
  side: applied.side || undefined, // canonical 值直传，后端归一兜底
  order_type: applied.order_type || undefined,
  ...(applied.time_range?.length === 2
    ? {
        start_time: applied.time_range[0].toISOString(),
        end_time: applied.time_range[1].toISOString(),
      }
    : {}),
  page: targetPage,
  page_size: targetSize,
});

const toOrderRows = (items: OrderInfo[]): OrderRow[] =>
  items.map((o) => ({
    key: `order-${o.client_order_id || o.venue_order_id}`,
    order_id: String(o.client_order_id || o.venue_order_id || ''),
    symbol: String(o.symbol),
    side: String(o.side || ''),
    position_side: o.position_side,
    reduce_only: o.reduce_only,
    order_type: String(o.order_type || '').toUpperCase(),
    quantity: Number(o.quantity || 0),
    price: o.price ?? null,
    avg_fill_price: o.avg_fill_price ?? null,
    filled_quantity: Number(o.filled_quantity ?? 0),
    status: String(o.status),
    created_at: String(o.created_at || ''),
  }));

type SubKey = 'positions' | 'openOrders' | 'orderHistory' | 'tradeHistory';

const WorkerOrderTab: React.FC<WorkerOrderTabProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<FilterValues>();

  const [subTab, setSubTab] = useState<SubKey>('positions');
  const [loading, setLoading] = useState(false);
  // initialized：首帧数据是否已返回。轮询刷新只做局部 setState 更新，
  // 不再把整个面板替换成 Spin——DOM 被替换会丢失浏览器滚动位置（页面跳回顶部）
  const [initialized, setInitialized] = useState(false);
  const [filterCollapsed, setFilterCollapsed] = useState(false);

  // 仓位（交易所对账 / paper 引擎快照）
  const [positions, setPositions] = useState<PositionInfo[]>([]);
  // 当前委托 / 历史委托（同一订单表接口）
  const [openOrders, setOpenOrders] = useState<OrderRow[]>([]);
  const [historyOrders, setHistoryOrders] = useState<OrderRow[]>([]);
  const [orderHistoryTotal, setOrderHistoryTotal] = useState(0);
  // 当前委托徽标用服务端 total（列表只取前 50 行，行数 ≠ 计数）
  const [openCount, setOpenCount] = useState(0);
  // 历史成交（服务端分页）
  const [tradeRows, setTradeRows] = useState<MergedTradeRow[]>([]);
  const [tradeTotal, setTradeTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [filters, setFilters] = useState<FilterValues>({});

  const statusLabel = (status: string) =>
    STATUS_LABEL_KEYS[status] ? t(STATUS_LABEL_KEYS[status]) : status;
  const orderTypeLabel = (type: string) =>
    ORDER_TYPE_LABEL_KEYS[type] ? t(ORDER_TYPE_LABEL_KEYS[type]) : type;

  // ---------- 数据加载（按激活页签） ----------

  // 仓位行数天然个位数（每 symbol 至多一行），接口无分页——分页观感由 DataTable 本地切片补齐
  const fetchPositions = useCallback(
    async (applied: FilterValues) => {
      const items = await workerApi.getPositions(workerId, {
        status: 'OPEN',
        symbol: applied.symbol || undefined,
        side: applied.side || undefined,
      });
      setPositions(items ?? []);
    },
    [workerId],
  );

  const fetchOpenOrders = useCallback(
    async (applied: FilterValues, targetPage: number, targetSize: number) => {
      const res = await workerApi.getOrders(workerId, orderParamsOf(applied, targetPage, targetSize, { status: 'OPEN' }));
      setOpenOrders(toOrderRows(res?.items ?? []));
      setOpenCount(res?.total ?? 0);
    },
    [workerId],
  );

  const fetchHistoryOrders = useCallback(
    async (applied: FilterValues, targetPage: number, targetSize: number) => {
      // 服务端排除 OPEN（total 即历史精确计数）；撤单事件链路未接线，
      // 该页实际以 FILLED 为主——注脚已披露，不造假数据
      const res = await workerApi.getOrders(workerId, orderParamsOf(applied, targetPage, targetSize, { exclude_open: true }));
      setHistoryOrders(toOrderRows(res?.items ?? []));
      setOrderHistoryTotal(res?.total ?? 0);
    },
    [workerId],
  );

  const fetchTrades = useCallback(
    async (applied: FilterValues, targetPage: number, targetSize: number) => {
      const res = await workerApi.getWorkerTrades(workerId, tradeParamsOf(applied, targetPage, targetSize));
      setTradeRows(
        (res?.items ?? []).map((tr) => ({
          key: `trade-${tr.fill_id}`,
          order_id: tr.fill_id,
          symbol: tr.symbol,
          side: tr.side || '',
          position_side: tr.position_side,
          reduce_only: tr.reduce_only,
          order_type: (tr.order_type || 'MARKET').toUpperCase(),
          quantity: tr.quantity,
          avg_fill_price: tr.price,
          filled_quantity: tr.quantity,
          status: 'FILLED',
          realized_pnl: tr.realized_pnl,
          created_at: tr.entry_time || tr.created_at,
        })),
      );
      setTradeTotal(res?.total ?? 0);
    },
    [workerId],
  );

  // 只拉当前页签；数据刷新统一由下方 effect 触发（切页签 / 翻页 / 换档位 / 提交筛选）
  const fetchActive = useCallback(async () => {
    setLoading(true);
    try {
      if (subTab === 'positions') await fetchPositions(filters);
      else if (subTab === 'openOrders') await fetchOpenOrders(filters, page, pageSize);
      else if (subTab === 'orderHistory') await fetchHistoryOrders(filters, page, pageSize);
      else await fetchTrades(filters, page, pageSize);
    } catch (error) {
      console.error('交易页签数据获取失败:', error);
    } finally {
      setLoading(false);
      setInitialized(true);
    }
  }, [subTab, filters, page, pageSize, fetchPositions, fetchOpenOrders, fetchHistoryOrders, fetchTrades]);

  // 四页签计数预取（首帧一次轻量请求 page_size=1 只为 total），
  // 徽标不依赖"是否访问过该页签"；激活页签的实时值由数据加载继续刷新
  const fetchCounts = useCallback(async () => {
    try {
      const [pos, open, hist, trades] = await Promise.all([
        workerApi.getPositions(workerId, { status: 'OPEN' }),
        workerApi.getOrders(workerId, { status: 'OPEN', page: 1, page_size: 1 }),
        workerApi.getOrders(workerId, { exclude_open: true, page: 1, page_size: 1 }),
        workerApi.getWorkerTrades(workerId, { page: 1, page_size: 1 }),
      ]);
      setPositions(pos ?? []);
      setOpenCount(open?.total ?? 0);
      setOrderHistoryTotal(hist?.total ?? 0);
      setTradeTotal(trades?.total ?? 0);
    } catch {
      /* 计数非关键，失败吃掉等轮询 */
    }
  }, [workerId]);

  // 数据拉取：worker 切换 / 切页签 / 翻页 / 换每页档位 / 提交筛选（setFilters+setPage 一次 render 合并）
  useEffect(() => {
    void fetchActive();
  }, [fetchActive]);

  // 计数只跟 worker 走，不随翻页/筛选重发
  useEffect(() => {
    void fetchCounts();
  }, [workerId, fetchCounts]);

  // 3s 轮询（仅激活时）刷新当前页签，闭包由 usePolling 的 taskRef 保持最新
  usePolling(fetchActive, { interval: 3000, enabled: active });

  const handleManualRefresh = () => {
    void fetchActive();
    void fetchCounts();
  };

  const handlePageChange = (nextPage: number, nextSize: number) => {
    // 换每页档位回第一页（翻页码由 DataTable 按新 total 钳制）
    if (nextSize !== pageSize) {
      setPage(1);
      setPageSize(nextSize);
    } else {
      setPage(nextPage);
    }
  };

  // ---------- CSV（按激活页签导出当前筛选下的全量，上限 100 行） ----------

  const handleExport = async () => {
    if (subTab === 'positions') {
      // positions 本身就是筛选后全量（接口无分页）
      downloadCsv(
        timestampedFilename('worker_positions', workerId),
        positions,
        [
          { header: t('symbol'), accessor: 'symbol' },
          { header: t('worker_position_side'), accessor: 'position_side' },
          { header: t('leverage'), accessor: (r) => r.leverage ?? '' },
          { header: t('quantity'), accessor: 'quantity' },
          { header: t('worker_entry_price'), accessor: 'entry_price' },
          { header: t('worker_breakeven_price'), accessor: (r) => r.breakeven_price ?? '' },
          { header: t('worker_mark_price'), accessor: 'current_price' },
          { header: t('worker_liquidation_price'), accessor: (r) => r.liquidation_price ?? '' },
          { header: t('worker_margin_ratio'), accessor: (r) => r.margin_ratio ?? '' },
          { header: t('worker_margin_used'), accessor: 'margin_used' },
          { header: t('unrealized_pnl'), accessor: 'unrealized_pnl' },
        ],
      );
    } else if (subTab === 'openOrders' || subTab === 'orderHistory') {
      // 分页后表格只是当前页，导出按当前筛选重拉全量（接口上限 100 行，见 EXPORT_MAX_ROWS）
      const res =
        subTab === 'openOrders'
          ? await workerApi.getOrders(workerId, orderParamsOf(filters, 1, EXPORT_MAX_ROWS, { status: 'OPEN' }))
          : await workerApi.getOrders(workerId, orderParamsOf(filters, 1, EXPORT_MAX_ROWS, { exclude_open: true }));
      downloadCsv(
        timestampedFilename(subTab === 'openOrders' ? 'worker_open_orders' : 'worker_order_history', workerId),
        toOrderRows(res?.items ?? []),
        [
          { header: t('worker_order_id'), accessor: 'order_id' },
          { header: t('symbol'), accessor: 'symbol' },
          { header: t('direction'), accessor: 'side' },
          { header: t('type'), accessor: 'order_type' },
          { header: t('worker_order_price'), accessor: (r) => r.price ?? '' },
          { header: t('quantity'), accessor: 'quantity' },
          { header: t('filled_quantity'), accessor: 'filled_quantity' },
          { header: t('status'), accessor: 'status' },
          { header: t('create_time'), accessor: (r) => formatTimestamp(r.created_at) },
        ],
      );
    } else {
      const res = await workerApi.getWorkerTrades(workerId, tradeParamsOf(filters, 1, EXPORT_MAX_ROWS));
      downloadCsv(
        timestampedFilename('worker_trades', workerId),
        (res?.items ?? []).map((tr) => ({
          order_id: tr.fill_id,
          symbol: tr.symbol,
          side: tr.side || '',
          position_side: tr.position_side ?? '',
          reduce_only: tr.reduce_only,
          order_type: (tr.order_type || 'MARKET').toUpperCase(),
          quantity: tr.quantity,
          avg_fill_price: tr.price,
          realized_pnl: tr.realized_pnl,
          created_at: tr.entry_time || tr.created_at,
        })),
        [
          { header: t('worker_order_id'), accessor: 'order_id' },
          { header: t('symbol'), accessor: 'symbol' },
          { header: t('direction'), accessor: 'side' },
          { header: t('position_side'), accessor: 'position_side' },
          { header: t('reduce_only'), accessor: (r) => (r.reduce_only == null ? '' : r.reduce_only ? 'true' : 'false') },
          { header: t('type'), accessor: 'order_type' },
          { header: t('quantity'), accessor: 'quantity' },
          { header: t('worker_avg_fill_price'), accessor: (r) => r.avg_fill_price ?? '' },
          { header: t('realized_pnl'), accessor: (r) => r.realized_pnl ?? '' },
          { header: t('create_time'), accessor: (r) => formatTimestamp(r.created_at) },
        ],
      );
    }
  };

  // ---------- 列定义 ----------

  // 保证金比率色档（币安口径：风险随比率升高）：<50 绿 / 50-75 黄 / >75 红
  const renderMarginRatio = (ratio: number) => {
    const cls = ratio < 50 ? ' qc-cell-up' : ratio > 75 ? ' qc-cell-down' : '';
    return <span className={`qc-mono${cls}`}>{ratio.toFixed(2)}%</span>;
  };

  const positionColumns: TableColumnsType<PositionInfo> = [
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string, record: PositionInfo) => (
        <Space size={4}>
          <span className="qc-mono">{symbol}</span>
          <span className="qc-chip quiet">{t('worker_perpetual')}</span>
          {record.leverage ? <span className="qc-chip quiet">{record.leverage}x</span> : null}
        </Space>
      ),
    },
    {
      title: t('quantity'),
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number, record: PositionInfo) => {
        // 多正空负（币安口径：空头数量带负号），方向色强调
        const signed = record.position_side === 'short' ? -Math.abs(qty) : Math.abs(qty);
        const cls = record.position_side === 'short' ? ' qc-cell-down' : ' qc-cell-up';
        return (
          <Space size={4}>
            <span className={`qc-mono${cls}`}>{formatQuantity(signed)}</span>
            <span className="qc-chip quiet">
              {record.position_side === 'long' || record.side === 'long'
                ? t('position_side_long')
                : record.position_side === 'short' || record.side === 'short'
                  ? t('position_side_short')
                  : t('position_side_both')}
            </span>
          </Space>
        );
      },
    },
    {
      title: t('worker_entry_price'),
      dataIndex: 'entry_price',
      key: 'entry_price',
      align: 'right',
      render: (v: number) => <span className="qc-mono">{formatUSD(v)}</span>,
    },
    {
      title: t('worker_breakeven_price'),
      dataIndex: 'breakeven_price',
      key: 'breakeven_price',
      align: 'right',
      // live/testnet 富化值；paper 无 → —
      render: (v?: number | null) =>
        v != null && v > 0 ? <span className="qc-mono">{formatUSD(v)}</span> : <span className="qc-mono qc-cell-none">—</span>,
    },
    {
      title: t('worker_mark_price'),
      dataIndex: 'current_price',
      key: 'current_price',
      align: 'right',
      render: (v?: number | null) =>
        v != null && v > 0 ? <span className="qc-mono">{formatUSD(v)}</span> : '-',
    },
    {
      title: t('worker_liquidation_price'),
      dataIndex: 'liquidation_price',
      key: 'liquidation_price',
      align: 'right',
      render: (v?: number | null) =>
        v != null && v > 0 ? (
          <span className="qc-mono" style={{ color: 'var(--qc-danger, #e05a4e)' }}>{formatUSD(v)}</span>
        ) : (
          <span className="qc-mono qc-cell-none">—</span>
        ),
    },
    {
      title: t('worker_margin_ratio'),
      dataIndex: 'margin_ratio',
      key: 'margin_ratio',
      align: 'right',
      render: (v?: number | null) =>
        v != null && v > 0 ? renderMarginRatio(v) : <span className="qc-mono qc-cell-none">—</span>,
    },
    {
      title: t('worker_margin_used'),
      dataIndex: 'margin_used',
      key: 'margin_used',
      align: 'right',
      render: (v: number) => <span className="qc-mono">{formatUSD(v)}</span>,
    },
    {
      title: t('worker_pnl_roi'),
      dataIndex: 'unrealized_pnl',
      key: 'unrealized_pnl',
      align: 'right',
      render: (pnl: number, record: PositionInfo) => {
        // ROI 分母：优先保证金（交易所口径）；缺失按 杠杆折算名义本金（paper margin 恒 0）
        // ponytail: 无杠杆时退 notional 全额——币本位乘数未入账的近似，见 engine_service 同类注释
        let roi: number | null = null;
        if (record.margin_used > 0) roi = (pnl / record.margin_used) * 100;
        else if (record.leverage && record.entry_price && record.quantity)
          roi = (pnl / ((record.entry_price * record.quantity) / record.leverage)) * 100;
        const cls = pnl >= 0 ? ' qc-cell-up' : ' qc-cell-down';
        return (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: 1.4 }}>
            <span className={`qc-mono${cls}`}>{formatUSD(pnl)}</span>
            {roi != null && Number.isFinite(roi) && (
              <span className={`qc-mono${cls}`} style={{ fontSize: 11.5 }}>
                {roi >= 0 ? '+' : ''}
                {roi.toFixed(2)}%
              </span>
            )}
          </div>
        );
      },
    },
  ];

  const orderColumns: TableColumnsType<OrderRow> = [
    {
      title: t('create_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (time: string) => (
        <span className="qc-mono" style={{ fontSize: 11.5, color: 'var(--qc-text-tertiary)' }}>
          {time ? formatTimestamp(time) : '—'}
        </span>
      ),
    },
    {
      title: t('worker_order_id'),
      dataIndex: 'order_id',
      key: 'order_id',
      width: 190,
      render: (id: string) => (
        <Tooltip title="client_order_id">
          <span className="qc-mono">{truncateId(id, 8, 6)}</span>
        </Tooltip>
      ),
    },
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <span className="qc-mono">{symbol}</span>,
    },
    {
      title: t('direction'),
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: string) => (
        <span className={`qc-mono${side === 'buy' ? ' qc-cell-up' : side === 'sell' ? ' qc-cell-down' : ''}`}>
          {side ? t(side) : '-'}
        </span>
      ),
    },
    {
      title: t('type'),
      dataIndex: 'order_type',
      key: 'order_type',
      width: 120,
      render: (type: string) => (type ? orderTypeLabel(type) : <span className="qc-mono qc-cell-none">—</span>),
    },
    {
      title: t('worker_order_price'),
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price?: number | null) =>
        price !== undefined && price !== null
          ? formatUSD(price)
          : <span className="qc-mono qc-cell-none">—</span>,
    },
    {
      title: t('quantity'),
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => formatQuantity(qty),
    },
    {
      title: t('filled_quantity'),
      key: 'filled',
      align: 'right',
      width: 150,
      render: (_: unknown, record: OrderRow) => (
        <span className="qc-mono">
          {formatQuantity(record.filled_quantity ?? 0)}
          <span style={{ color: 'var(--qc-text-tertiary)' }}> / {formatQuantity(record.quantity ?? 0)}</span>
        </span>
      ),
    },
    {
      title: t('status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <span className={`qc-chip${STATUS_CHIP_CLS[status] ?? ' quiet'}`}>
          {status === 'OPEN' && <span className="qc-pdot" />}
          {statusLabel(status)}
        </span>
      ),
    },
  ];

  const tradeColumns: TableColumnsType<MergedTradeRow> = [
    {
      title: t('create_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (time: string) => (
        <span className="qc-mono" style={{ fontSize: 11.5, color: 'var(--qc-text-tertiary)' }}>
          {time ? formatTimestamp(time) : '—'}
        </span>
      ),
    },
    {
      title: t('worker_order_id'),
      dataIndex: 'order_id',
      key: 'order_id',
      width: 190,
      render: (id: string) => (
        <Tooltip title="fill_id">
          <span className="qc-mono">{truncateId(id, 8, 6)}</span>
        </Tooltip>
      ),
    },
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <span className="qc-mono">{symbol}</span>,
    },
    {
      title: t('direction'),
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: string) => (
        <span className={`qc-mono${side === 'buy' ? ' qc-cell-up' : side === 'sell' ? ' qc-cell-down' : ''}`}>
          {side ? t(side) : '-'}
        </span>
      ),
    },
    {
      title: t('type'),
      dataIndex: 'order_type',
      key: 'order_type',
      width: 120,
      render: (type: string) => (type ? orderTypeLabel(type) : <span className="qc-mono qc-cell-none">—</span>),
    },
    {
      title: t('quantity'),
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => formatQuantity(qty),
    },
    {
      title: t('worker_avg_fill_price'),
      dataIndex: 'avg_fill_price',
      key: 'avg_fill_price',
      align: 'right',
      render: (price?: number | null) =>
        price !== undefined && price !== null ? formatUSD(price) : '-',
    },
    {
      title: t('realized_pnl'),
      dataIndex: 'realized_pnl',
      key: 'realized_pnl',
      align: 'right',
      width: 120,
      render: (pnl?: number | null) => {
        if (pnl === undefined || pnl === null) return <span className="qc-mono qc-cell-none">—</span>;
        // 盈亏只在平仓 finalize 行有值（round-trip 配对回填），该行即整轮建仓→平仓的盈亏归属行
        return (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span className={`qc-mono${pnl >= 0 ? ' qc-cell-up' : ' qc-cell-down'}`}>
              {formatUSD(pnl)}
            </span>
            <span className="qc-chip quiet">{t('trade_closed_tag')}</span>
          </span>
        );
      },
    },
  ];

  // 提交/重置筛选：回第一页，拉取由 fetchActive effect 接管
  const handleApplyFilter = (values: FilterValues) => {
    setFilters(values);
    setPage(1);
  };

  const handleResetFilter = () => {
    form.resetFields();
    setFilters({});
    setPage(1);
  };

  // 仅首帧未返回数据时用 Spin 占位；之后轮询不触发此分支，DOM 结构保持稳定
  if (!initialized) {
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  }

  const tabItems = [
    { key: 'positions', label: `${t('wt_tab_positions')} (${positions.length})` },
    { key: 'openOrders', label: `${t('wt_tab_open_orders')} (${openCount})` },
    // 历史两页签计数用服务端 total（精确），非当前页行数
    { key: 'orderHistory', label: `${t('wt_tab_order_history')} (${orderHistoryTotal})` },
    { key: 'tradeHistory', label: `${t('wt_tab_trade_history')} (${tradeTotal})` },
  ];

  const emptyByTab: Record<SubKey, string> = {
    positions: t('worker_position_empty'),
    openOrders: t('no_order_data'),
    orderHistory: t('no_order_data'),
    tradeHistory: t('no_order_data'),
  };

  return (
    <div>
      <Card
        className="qc-card"
        title={
          <Space size={12}>
            <span>{t('trade_details')}</span>
            {active && (
              <span className="qc-chip info">
                <span className="qc-pdot" />
                {t('worker_realtime')}
              </span>
            )}
          </Space>
        }
        extra={
          <Space>
            <Button
              icon={<SearchOutlined />}
              onClick={() => setFilterCollapsed(!filterCollapsed)}
              size="small"
            >
              {filterCollapsed ? t('worker_collapse_filter') : t('worker_expand_filter')}
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleManualRefresh}
              loading={loading}
              size="small"
            >
              {t('refresh')}
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={() => void handleExport()}
              size="small"
              disabled={
                (subTab === 'positions' && positions.length === 0) ||
                (subTab === 'openOrders' && openCount === 0) ||
                (subTab === 'orderHistory' && orderHistoryTotal === 0) ||
                (subTab === 'tradeHistory' && tradeTotal === 0)
              }
            >
              {t('worker_export_csv')}
            </Button>
          </Space>
        }
      >
        <Tabs
          size="small"
          activeKey={subTab}
          onChange={(k) => {
            setSubTab(k as SubKey);
            setPage(1);
            // 一套筛选走天下（ponytail：per-tab 筛选 state 是过度工程），
            // side 语义不同域（仓位=long/short，订单=buy/sell），切页签必须清空防脏值串场
            form.resetFields();
            setFilters({});
          }}
          items={tabItems}
        />

        {/* 筛选面板（全页签；仓位接口只支持 symbol/持仓方向，订单/成交另加类型与时间） */}
        {filterCollapsed && (
          <Form
            form={form}
            layout="inline"
            onFinish={handleApplyFilter}
            style={{ marginBottom: 16, rowGap: 8 }}
          >
            <Form.Item name="symbol" label={t('trading_pair')}>
              <Input placeholder={t('worker_symbol_placeholder')} allowClear style={{ width: 150 }} />
            </Form.Item>
            {subTab === 'positions' ? (
              <Form.Item name="side" label={t('worker_position_side')}>
                <Select
                  placeholder={t('all')}
                  allowClear
                  options={[
                    { value: 'long', label: t('position_side_long') },
                    { value: 'short', label: t('position_side_short') },
                  ]}
                  style={{ width: 100 }}
                />
              </Form.Item>
            ) : (
              <>
                <Form.Item name="side" label={t('backtest_side')}>
                  <Select
                    placeholder={t('all')}
                    allowClear
                    options={SIDE_OPTIONS.map((v) => ({ value: v, label: t(v) }))}
                    style={{ width: 100 }}
                  />
                </Form.Item>
                <Form.Item name="order_type" label={t('type')}>
                  <Select
                    placeholder={t('all')}
                    allowClear
                    options={Object.keys(ORDER_TYPE_LABEL_KEYS).map((v) => ({ value: v, label: orderTypeLabel(v) }))}
                    style={{ width: 170 }}
                  />
                </Form.Item>
                <Form.Item name="time_range" label={t('backtest_time')}>
                  <RangePicker
                    showTime={{ format: 'HH:mm:ss' }}
                    format="YYYY-MM-DD HH:mm:ss"
                  />
                </Form.Item>
              </>
            )}
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={loading}>
                  {t('worker_apply')}
                </Button>
                <Button onClick={handleResetFilter}>{t('reset')}</Button>
              </Space>
            </Form.Item>
          </Form>
        )}

        {/* 历史委托注脚：撤单/拒单事件链路未接线，历史委托以成交回推 FILLED 为主（如实披露） */}
        {subTab === 'orderHistory' && historyOrders.length > 0 && (
          <div className="qc-card-sub" style={{ marginBottom: 8, color: 'var(--qc-text-tertiary)' }}>
            {t('worker_order_history_note')}
          </div>
        )}

        {subTab === 'positions' ? (
          // 仓位：客户端分页（DataTable 本地切片，total 由 dataSource.length 推得）
          <DataTable
            columns={positionColumns}
            dataSource={positions}
            rowKey="position_id"
            emptyTitle={emptyByTab.positions}
            pagination={{ current: page, pageSize, onChange: handlePageChange }}
          />
        ) : subTab === 'openOrders' ? (
          <DataTable
            columns={orderColumns}
            dataSource={openOrders}
            rowKey="key"
            remote
            loading={loading && initialized}
            emptyTitle={emptyByTab.openOrders}
            pagination={{ current: page, pageSize, total: openCount, onChange: handlePageChange }}
          />
        ) : subTab === 'orderHistory' ? (
          <DataTable
            columns={orderColumns}
            dataSource={historyOrders}
            rowKey="key"
            remote
            loading={loading && initialized}
            emptyTitle={emptyByTab.orderHistory}
            pagination={{ current: page, pageSize, total: orderHistoryTotal, onChange: handlePageChange }}
          />
        ) : (
          <DataTable
            columns={tradeColumns}
            dataSource={tradeRows}
            rowKey="key"
            remote
            loading={loading && initialized}
            emptyTitle={emptyByTab.tradeHistory}
            pagination={{ current: page, pageSize, total: tradeTotal, onChange: handlePageChange }}
          />
        )}
      </Card>
    </div>
  );
};

export default WorkerOrderTab;
