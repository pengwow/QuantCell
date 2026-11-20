/**
 * Worker 交易明细 Tab（成交 + 挂单合并单列表）
 *
 * 两条数据通路合并为一张表，靠状态列区分（不拆子标签）：
 * - 成交明细（GET /monitoring/trades，FILLED 为主体）：逐笔回报，含完整历史与已实现盈亏
 * - 活跃挂单（GET /strategy/orders?status=OPEN）：订单同步链路写入，仅第一页置顶展示
 * 合并后按时间倒序（挂单为“当前进行时”恒在最上）。
 * 保留：高级筛选 / 3s 轮询（仅 tab 激活时）/ CSV 导出 /「实时」Badge。
 */

import { useCallback, useMemo, useState } from 'react';
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
  Tooltip,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import { formatQuantity, formatTimestamp, formatUSD, truncateId } from '@/utils/format';
import { downloadCsv, timestampedFilename } from '@/utils/exportCsv';
import { PER_PAGE_OPTIONS } from '../../constants/pagination';
import type { Side, PositionSide, TradeQueryParams } from '@/types/worker';

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

const STATUS_OPTIONS = Object.keys(STATUS_LABEL_KEYS);

// 订单状态 → §6.2 chip（OPEN 进行中带 pulse 圆点；未知状态回退 quiet）
const renderOrderStatusChip = (status: string, label: string) => (
  <span className={`qc-chip${STATUS_CHIP_CLS[status] ?? ' quiet'}`}>
    {status === 'OPEN' && <span className="qc-pdot" />}
    {label}
  </span>
);

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

const ORDER_TYPE_OPTIONS = Object.keys(ORDER_TYPE_LABEL_KEYS);

// 合并行模型：成交行（kind=trade）与订单行（kind=order）共用列结构
interface MergedRow {
  key: string;
  kind: 'trade' | 'order';
  /** 成交行 → fill_id（单笔成交标识）；订单行 → client_order_id */
  order_id: string;
  symbol: string;
  side: string;
  /** 声明值（仓位归属，不从 side 推导）；老后端响应无此键为 undefined */
  position_side?: PositionSide;
  reduce_only?: boolean;
  order_type: string;
  quantity: number;
  /** 仅订单行：委托价（市价单为空） */
  price?: number | null;
  /** trade → 成交价；order → 成交均价 */
  avg_fill_price?: number | null;
  filled_quantity: number;
  status: string;
  /** 仅成交行：配对回填后的已实现盈亏 */
  realized_pnl?: number | null;
  created_at: string;
}

interface FilterValues {
  symbol?: string;
  side?: string;
  order_type?: string;
  status?: string;
  time_range?: [Dayjs, Dayjs];
}

interface WorkerOrderTabProps {
  workerId: number;
  /** tab 是否激活；激活时才进行 3s 轮询 */
  active?: boolean;
}

// §6.7 分页档位：12 的倍数（与全站 DataTable 同一套），20 非 12 倍数档位已弃用
const PAGE_SIZE = 12;

const WorkerOrderTab: React.FC<WorkerOrderTabProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<FilterValues>();
  // 状态文案国际化：标签/筛选/汇总统一走这里，未知枚举（历史脏数据）回退原文
  const statusLabel = (status: string) =>
    STATUS_LABEL_KEYS[status] ? t(STATUS_LABEL_KEYS[status]) : status;
  // 订单类型文案国际化，同上
  const orderTypeLabel = (type: string) =>
    ORDER_TYPE_LABEL_KEYS[type] ? t(ORDER_TYPE_LABEL_KEYS[type]) : type;
  const [loading, setLoading] = useState(false);
  // initialized：首帧数据是否已返回。轮询刷新只做局部 setState 更新，
  // 不再把整个面板替换成 Spin——DOM 被替换会丢失浏览器滚动位置（页面跳回顶部）
  const [initialized, setInitialized] = useState(false);
  const [rows, setRows] = useState<MergedRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(PAGE_SIZE);
  const [filters, setFilters] = useState<FilterValues>({});
  const [filterCollapsed, setFilterCollapsed] = useState(false);

  // 拉取合并数据：成交（服务端分页）+ 挂单（第一页并入）
  const fetchMerged = useCallback(
    async (applied: FilterValues = filters, targetPage = page, targetSize = pageSize) => {
      setLoading(true);
      try {
        const symbol = applied.symbol || undefined;
        // 方向筛选值为 canonical 小写，响应已统一（铁律1），无需大小写补丁
        const side = applied.side || undefined;
        const orderType = applied.order_type || undefined;
        const timeParams =
          applied.time_range?.length === 2
            ? {
                start_time: applied.time_range[0].toISOString(),
                end_time: applied.time_range[1].toISOString(),
              }
            : {};
        // 状态路由：空/FILLED → 成交明细主体；其余状态 → 订单表；空状态额外合并第一页 OPEN
        const status = applied.status || undefined;
        const tradesNeeded = !status || status === 'FILLED';
        const mergeOpen = !status;
        const ordersNeeded = mergeOpen || (!!status && status !== 'FILLED');

        const tradeParams: TradeQueryParams | undefined = tradesNeeded
          ? {
              symbol,
              side: side,   // canonical 值直传，后端归一兜底
              order_type: orderType,
              ...timeParams,
              page: targetPage,
              page_size: targetSize,
            }
          : undefined;
        // 订单表请求参数：可选筛选项仅在有值时写入（Record 索引签名不接受 undefined）
        const orderParams: Record<string, string | number> | undefined = (() => {
          if (!ordersNeeded) return undefined;
          const p: Record<string, string | number> = {
            status: mergeOpen ? 'OPEN' : status!,
            page: 1,
            page_size: 50,
          };
          if (symbol) p.symbol = symbol;
          if (side) p.side = side;
          if (orderType) p.order_type = orderType;
          if (timeParams.start_time) p.start_time = timeParams.start_time;
          if (timeParams.end_time) p.end_time = timeParams.end_time;
          return p;
        })();

        const [tradeRes, orderRes] = await Promise.all([
          tradeParams
            ? workerApi.getWorkerTrades(workerId, tradeParams)
            : Promise.resolve(undefined),
          orderParams
            ? workerApi.getOrders(workerId, orderParams)
            : Promise.resolve(undefined),
        ]);

        const tradeRows: MergedRow[] = (tradeRes?.items ?? []).map((tr) => ({
          key: `trade-${tr.fill_id}`,
          kind: 'trade',
          order_id: tr.fill_id,
          symbol: tr.symbol,
          side: tr.side || '',                       // 响应已 canonical，不再翻转
          position_side: tr.position_side,
          reduce_only: tr.reduce_only,
          order_type: (tr.order_type || 'MARKET').toUpperCase(),
          quantity: tr.quantity,
          avg_fill_price: tr.price,
          filled_quantity: tr.quantity, // 成交行：本身即全部已成交
          status: 'FILLED',
          realized_pnl: tr.realized_pnl,
          created_at: tr.entry_time || tr.created_at,
        }));
        const orderRows: MergedRow[] = (orderRes?.items ?? []).map((o) => ({
          key: `order-${o.client_order_id || o.venue_order_id}`,
          kind: 'order',
          order_id: o.client_order_id || o.venue_order_id || '',
          symbol: o.symbol,
          side: o.side || '',                        // 响应已 canonical，不再翻转
          position_side: o.position_side,
          reduce_only: o.reduce_only,
          order_type: (o.order_type || '').toUpperCase(),
          quantity: o.quantity,
          price: o.price,
          avg_fill_price: o.avg_fill_price,
          filled_quantity: o.filled_quantity ?? 0,
          status: o.status,
          created_at: o.created_at,
        }));

        // 挂单置顶仅在第一页（历史翻页无意义），成交行紧随其后
        const merged = targetPage === 1 && mergeOpen ? [...orderRows, ...tradeRows] : tradeRows;
        setRows(merged);
        // 分页 total 仅含成交：挂单独立置顶展示、不计入分页
        // （若并入 total，首页行数会 > pageSize 且 < total，触发 antd 受控分页警告）
        setTotal(tradeRes?.total ?? orderRes?.total ?? 0);
      } catch (error) {
        console.error('获取交易明细失败:', error);
        setRows([]);
        setTotal(0);
      } finally {
        setLoading(false);
        setInitialized(true);
      }
    },
    [workerId, filters, page, pageSize],
  );

  // 3s 轮询
  usePolling(
    () => fetchMerged(),
    { interval: 3000, enabled: active },
  );

  // 应用筛选（重置回第一页）
  const handleApplyFilter = (values: FilterValues) => {
    setFilters(values);
    setPage(1);
    fetchMerged(values, 1, pageSize);
  };

  const handleResetFilter = () => {
    form.resetFields();
    setFilters({});
    setPage(1);
    fetchMerged({}, 1, pageSize);
  };

  const handleManualRefresh = () => {
    fetchMerged(filters);
  };

  const handlePageChange = (nextPage: number, nextSize: number) => {
    setPage(nextPage);
    setPageSize(nextSize);
    fetchMerged(filters, nextPage, nextSize);
  };

  // 导出当前合并行
  const handleExport = () => {
    downloadCsv(
      timestampedFilename('worker_trades', workerId),
      rows,
      [
        { header: t('worker_order_id'), accessor: (r) => r.order_id },
        { header: t('symbol'), accessor: 'symbol' },
        { header: t('direction'), accessor: 'side' },
        { header: t('position_side'), accessor: (r: MergedRow) => r.position_side ?? '' },
        { header: t('reduce_only'), accessor: (r: MergedRow) => (r.reduce_only == null ? '' : r.reduce_only ? 'true' : 'false') },
        { header: t('type'), accessor: 'order_type' },
        { header: t('quantity'), accessor: 'quantity' },
        { header: t('worker_order_price'), accessor: (r) => r.price ?? '' },
        { header: t('worker_avg_fill_price'), accessor: (r) => r.avg_fill_price ?? '' },
        { header: t('filled_quantity'), accessor: 'filled_quantity' },
        { header: t('status'), accessor: 'status' },
        { header: t('realized_pnl'), accessor: (r) => r.realized_pnl ?? '' },
        { header: t('create_time'), accessor: (r) => formatTimestamp(r.created_at) },
      ],
    );
  };

  // 表格列：成交行与订单行共用列结构，空缺字段显示 '-'
  const columns: TableColumnsType<MergedRow> = [
    {
      title: t('worker_order_id'),
      dataIndex: 'order_id',
      key: 'order_id',
      width: 190,
      render: (id: string, record: MergedRow) => (
        <Tooltip title={record.kind === 'trade' ? 'fill_id' : 'client_order_id'}>
          <span className="qc-mono">{truncateId(id, 8, 6)}</span>
        </Tooltip>
      ),
    },
    {
      title: t('symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 110,
      // 标识类中性 mono 文本（§6.5）：symbol 不是状态，上色会冒充语义
      render: (symbol: string) => <span className="qc-mono">{symbol}</span>,
    },
    {
      title: t('direction'),
      dataIndex: 'side',
      key: 'side',
      width: 80,
      // 方向值涨跌色（§6.5 数值列口径）：买 up / 卖 down
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
      // 类别值不上色（§6.5）：订单类型是中性类别，不是状态
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
      title: t('worker_order_price'),
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price?: number | null) =>
        price !== undefined && price !== null
          ? formatUSD(price)
          : <span style={{ color: 'var(--qc-text-tertiary)' }}>-</span>,
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
      title: t('filled_quantity'),
      key: 'filled',
      align: 'right',
      width: 150,
      render: (_: unknown, record: MergedRow) =>
        record.kind === 'trade' ? (
          <span className="qc-mono">{formatQuantity(record.filled_quantity)}</span>
        ) : (
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
      render: (status: string) => renderOrderStatusChip(status, statusLabel(status)),
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
    {
      title: t('create_time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      // §6.5 时间列：mono 11px fg-3 口径
      render: (time: string) => (
        <span className="qc-mono" style={{ fontSize: 11.5, color: 'var(--qc-text-tertiary)' }}>
          {time ? formatTimestamp(time) : '—'}
        </span>
      ),
    },
  ];

  // 汇总标签：当前合并行中订单行的状态计数（成交总数由分页 total 呈现）
  const summaryItems = useMemo(() => {
    const items: { status: string; count: number }[] = [];
    rows
      .filter((r) => r.kind === 'order')
      .forEach((r) => {
        const found = items.find((it) => it.status === r.status);
        if (found) found.count += 1;
        else items.push({ status: r.status, count: 1 });
      });
    return items;
  }, [rows]);

  // 行拆分：挂单行独立置顶展示（无分页），成交行走服务端分页
  const openOnlyRows = useMemo(() => rows.filter((r) => r.kind === 'order'), [rows]);
  const tradeOnlyRows = useMemo(() => rows.filter((r) => r.kind === 'trade'), [rows]);
  // 状态筛选为非 FILLED 时订单表为主体：rows 全为订单行且带分页
  const orderMainMode = !!filters.status && filters.status !== 'FILLED';

  // 仅首帧未返回数据时用 Spin 占位；之后轮询不触发此分支，DOM 结构保持稳定
  if (!initialized) {
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  }

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
              onClick={handleExport}
              disabled={rows.length === 0}
              size="small"
            >
              {t('worker_export_csv')}
            </Button>
          </Space>
        }
      >
        {/* 活跃挂单提示行：只统计第一页可见的订单行（语义 chip + mono 计数，非彩色 Tag） */}
        {summaryItems.length > 0 && (
          <div style={{ marginBottom: 12 }}>
            <Space size="small" wrap>
              {summaryItems.map(({ status, count }) => (
                <span key={status} className={`qc-chip${STATUS_CHIP_CLS[status] ?? ' quiet'}`}>
                  {statusLabel(status)}
                  <span className="qc-count-chip">{count}</span>
                </span>
              ))}
            </Space>
          </div>
        )}

        {/* 筛选面板 */}
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
                options={ORDER_TYPE_OPTIONS.map((v) => ({ value: v, label: orderTypeLabel(v) }))}
                style={{ width: 170 }}
              />
            </Form.Item>
            <Form.Item name="status" label={t('status')}>
              <Select
                placeholder={t('all')}
                allowClear
                options={STATUS_OPTIONS.map((s) => ({ value: s, label: statusLabel(s) }))}
                style={{ width: 130 }}
              />
            </Form.Item>
            <Form.Item name="time_range" label={t('backtest_time')}>
              <RangePicker
                showTime={{ format: 'HH:mm:ss' }}
                format="YYYY-MM-DD HH:mm:ss"
              />
            </Form.Item>
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

        {rows.length === 0 ? (
          <QcEmpty title={t('no_order_data')} />
        ) : (
          <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
            {/* 挂单置顶表：独立于分页（不计入 total/pageSize），仅在合并模式且有挂单时渲染 */}
            {!orderMainMode && openOnlyRows.length > 0 && (
              <div>
                <div className="qc-card-sub" style={{ marginBottom: 6 }}>
                  {t('worker_open_orders')} ({openOnlyRows.length})
                </div>
                <DataTable
                  columns={columns}
                  dataSource={openOnlyRows}
                  rowKey="key"
                  pagination={false}
                />
              </div>
            )}
            {/* 成交/订单明细主体：纯服务端分页（remote：rows 已是服务端裁好的当页） */}
            <DataTable
              columns={columns}
              dataSource={orderMainMode ? rows : tradeOnlyRows}
              rowKey="key"
              remote
              loading={loading && initialized}
              pagination={{
                current: page,
                pageSize,
                total,
                onChange: handlePageChange,
                pageSizeOptions: PER_PAGE_OPTIONS,
              }}
            />
          </Space>
        )}
      </Card>
    </div>
  );
};

export default WorkerOrderTab;
