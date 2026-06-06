/**
 * Worker 委托 Tab
 *
 * 展示当前 Worker 的委托（订单）情况：
 * - 标准列顺序：订单ID、交易对、方向、类型、数量、委托价、成交均价、已成交、状态、持仓方向、创建时间、提交时间
 * - 高级筛选：交易对、方向、订单类型、状态、时间范围
 * - 3s 轮询刷新 OPEN 委托（仅 tab 激活时）
 * - 「实时」Badge
 * - 「导出 CSV」按钮
 * - 状态 Tag 颜色统一业界标准
 */

import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
} from 'antd';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import type { Dayjs } from 'dayjs';
import { workerApi } from '@/api/workerApi';
import { usePolling } from '@/hooks/usePolling';
import { formatTimestamp, formatUSD, truncateId, QUANT_COLORS } from '@/utils/format';
import { downloadCsv, timestampedFilename } from '@/utils/exportCsv';

const { RangePicker } = DatePicker;

// 委托状态 -> Tag 颜色（业界标准）
const STATUS_COLOR_MAP: Record<string, string> = {
  OPEN: 'processing',      // 蓝（进行中）
  FILLED: 'success',       // 绿（已成交）
  CANCELED: 'default',     // 灰（已撤销）
  REJECTED: 'error',       // 红（已拒绝）
  ACCEPTED: 'warning',     // 黄（已接受）
  PENDING: 'processing',   // 蓝
  EXPIRED: 'default',      // 灰
};

const STATUS_OPTIONS = [
  { label: 'OPEN', value: 'OPEN' },
  { label: 'FILLED', value: 'FILLED' },
  { label: 'CANCELED', value: 'CANCELED' },
  { label: 'REJECTED', value: 'REJECTED' },
  { label: 'ACCEPTED', value: 'ACCEPTED' },
  { label: 'PENDING', value: 'PENDING' },
  { label: 'EXPIRED', value: 'EXPIRED' },
];

const SIDE_OPTIONS = [
  { label: 'BUY', value: 'BUY' },
  { label: 'SELL', value: 'SELL' },
];

const ORDER_TYPE_OPTIONS = [
  { label: 'MARKET', value: 'MARKET' },
  { label: 'LIMIT', value: 'LIMIT' },
  { label: 'STOP', value: 'STOP' },
  { label: 'STOP_MARKET', value: 'STOP_MARKET' },
  { label: 'TAKE_PROFIT', value: 'TAKE_PROFIT' },
  { label: 'TAKE_PROFIT_MARKET', value: 'TAKE_PROFIT_MARKET' },
];

interface Order {
  id: number;
  client_order_id: string;
  venue_order_id?: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  order_type: string;
  quantity: number;
  price?: number;
  filled_qty: number;
  avg_fill_price?: number;
  status: 'OPEN' | 'FILLED' | 'CANCELED' | 'REJECTED' | 'ACCEPTED' | 'PENDING' | 'EXPIRED';
  position_side?: 'LONG' | 'SHORT' | 'BOTH';
  created_at: string;
  submitted_at?: string;
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

const WorkerOrderTab: React.FC<WorkerOrderTabProps> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [form] = Form.useForm<FilterValues>();
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);
  const [filters, setFilters] = useState<FilterValues>({});
  const [filterCollapsed, setFilterCollapsed] = useState(false);

  // 拉取委托数据
  const fetchOrderData = useCallback(async (appliedFilters: FilterValues = filters) => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (appliedFilters.symbol) params.symbol = appliedFilters.symbol;
      if (appliedFilters.side) params.side = appliedFilters.side;
      if (appliedFilters.order_type) params.order_type = appliedFilters.order_type;
      if (appliedFilters.status) params.status = appliedFilters.status;
      if (appliedFilters.time_range?.length === 2) {
        params.start_time = appliedFilters.time_range[0].toISOString();
        params.end_time = appliedFilters.time_range[1].toISOString();
      }
      const response: any = await workerApi.getOrders(workerId, params);
      // 兼容多种返回结构
      let items: Order[] = [];
      if (response && response.code === 0 && Array.isArray(response.data?.items)) {
        items = response.data.items;
      } else if (response && Array.isArray(response.data)) {
        items = response.data;
      } else if (Array.isArray(response)) {
        items = response;
      }
      setOrders(items);
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error('获取委托数据失败:', error);
      setOrders([]);
    } finally {
      setLoading(false);
    }
  }, [workerId, filters]);

  // 3s 轮询：仅在 tab 激活时启用 OPEN 委托
  usePolling(
    () => fetchOrderData({ ...filters, status: filters.status || 'OPEN' }),
    { interval: 3000, enabled: active },
  );

  // 应用筛选
  const handleApplyFilter = (values: FilterValues) => {
    setFilters(values);
    fetchOrderData(values);
  };

  // 重置筛选
  const handleResetFilter = () => {
    form.resetFields();
    setFilters({});
    fetchOrderData({});
  };

  // 手动刷新
  const handleManualRefresh = () => {
    fetchOrderData(filters);
  };

  // 导出 CSV
  const handleExport = () => {
    downloadCsv(
      timestampedFilename('worker_orders', workerId),
      orders,
      [
        { header: '订单ID', accessor: (o) => o.client_order_id },
        { header: '交易对', accessor: 'symbol' },
        { header: '方向', accessor: 'side' },
        { header: '类型', accessor: 'order_type' },
        { header: '数量', accessor: 'quantity' },
        { header: '委托价', accessor: 'price' },
        { header: '成交均价', accessor: 'avg_fill_price' },
        { header: '已成交', accessor: 'filled_qty' },
        { header: '状态', accessor: 'status' },
        { header: '持仓方向', accessor: 'position_side' },
        { header: '创建时间', accessor: (o) => (o.created_at ? formatTimestamp(o.created_at) : '') },
        { header: '提交时间', accessor: (o) => (o.submitted_at ? formatTimestamp(o.submitted_at) : '') },
      ],
    );
  };

  // 表格列：标准量化展示顺序
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const columns: any = [
    {
      title: '订单ID',
      dataIndex: 'client_order_id',
      key: 'client_order_id',
      width: 180,
      render: (id: string) => (
        <Tooltip title={id || '-'}>
          <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
            {truncateId(id, 8, 6)}
          </span>
        </Tooltip>
      ),
    },
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 110,
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('direction') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'BUY' | 'SELL') => (
        <Tag color={side === 'BUY' ? 'green' : 'red'}>{side}</Tag>
      ),
    },
    {
      title: t('order_type') || '类型',
      dataIndex: 'order_type',
      key: 'order_type',
      width: 110,
      render: (type: string) => <Tag color="orange">{type?.toUpperCase() || '-'}</Tag>,
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => (qty !== undefined ? qty.toFixed(6) : '-'),
    },
    {
      title: '委托价',
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price?: number) =>
        price !== undefined && price !== null
          ? formatUSD(price)
          : <span style={{ color: '#999' }}>市价</span>,
    },
    {
      title: '成交均价',
      dataIndex: 'avg_fill_price',
      key: 'avg_fill_price',
      align: 'right',
      render: (price?: number) =>
        price !== undefined && price !== null ? formatUSD(price) : '-',
    },
    {
      title: t('filled_quantity') || '已成交',
      key: 'filled',
      align: 'right',
      width: 140,
      render: (_: unknown, record: Order) => (
        <span>
          <span style={{ fontWeight: 600, color: QUANT_COLORS.info }}>
            {(record.filled_qty ?? 0).toFixed(6)}
          </span>
          <span style={{ color: '#999' }}> / {(record.quantity ?? 0).toFixed(6)}</span>
        </span>
      ),
    },
    {
      title: t('status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={STATUS_COLOR_MAP[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '持仓方向',
      dataIndex: 'position_side',
      key: 'position_side',
      width: 90,
      render: (pos?: string) => (pos ? <Tag>{pos}</Tag> : '-'),
    },
    {
      title: t('created_at') || '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (time: string) => (time ? formatTimestamp(time) : '-'),
    },
    {
      title: '提交时间',
      dataIndex: 'submitted_at',
      key: 'submitted_at',
      width: 170,
      render: (time?: string) => (time ? formatTimestamp(time) : '-'),
    },
  ];

  // 状态分布：用于顶部小卡片
  const statusSummary = useMemo(() => {
    const map: Record<string, number> = {};
    orders.forEach((o) => {
      map[o.status] = (map[o.status] || 0) + 1;
    });
    return map;
  }, [orders]);

  if (loading && orders.length === 0) {
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      {/* 状态分布小卡片 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {Object.entries(statusSummary).map(([status, count]) => (
          <Col key={status}>
            <Tag
              color={STATUS_COLOR_MAP[status] || 'default'}
              style={{ fontSize: 14, padding: '4px 12px' }}
            >
              {status}: {count}
            </Tag>
          </Col>
        ))}
        {orders.length === 0 && !loading && (
          <Col>
            <span style={{ color: '#999' }}>暂无委托</span>
          </Col>
        )}
      </Row>

      <Card
        title={
          <span>
            {t('current_orders') || '当前委托'}
            {active && (
              <Badge
                status="processing"
                text="实时"
                style={{ marginLeft: 12, color: QUANT_COLORS.info }}
              />
            )}
          </span>
        }
        extra={
          <Space>
            <Button
              icon={<SearchOutlined />}
              onClick={() => setFilterCollapsed(!filterCollapsed)}
              size="small"
            >
              {filterCollapsed ? '收起筛选' : '展开筛选'}
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleManualRefresh}
              loading={loading}
              size="small"
            >
              刷新
            </Button>
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExport}
              disabled={orders.length === 0}
              size="small"
            >
              导出 CSV
            </Button>
          </Space>
        }
      >
        {/* 筛选面板 */}
        {filterCollapsed && (
          <Form
            form={form}
            layout="inline"
            onFinish={handleApplyFilter}
            style={{ marginBottom: 16, rowGap: 8 }}
          >
            <Form.Item name="symbol" label="交易对">
              <Input placeholder="如 BTCUSDT" allowClear style={{ width: 150 }} />
            </Form.Item>
            <Form.Item name="side" label="方向">
              <Select
                placeholder="全部"
                allowClear
                options={SIDE_OPTIONS}
                style={{ width: 100 }}
              />
            </Form.Item>
            <Form.Item name="order_type" label="类型">
              <Select
                placeholder="全部"
                allowClear
                options={ORDER_TYPE_OPTIONS}
                style={{ width: 160 }}
              />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                placeholder="全部"
                allowClear
                options={STATUS_OPTIONS}
                style={{ width: 130 }}
              />
            </Form.Item>
            <Form.Item name="time_range" label="时间">
              <RangePicker
                showTime={{ format: 'HH:mm:ss' }}
                format="YYYY-MM-DD HH:mm:ss"
              />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={loading}>
                  应用
                </Button>
                <Button onClick={handleResetFilter}>重置</Button>
              </Space>
            </Form.Item>
          </Form>
        )}

        {orders.length === 0 ? (
          <Empty
            description={t('no_order_data') || '暂无委托数据'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={orders}
            rowKey="id"
            pagination={{ pageSize: 10, size: 'small', showSizeChanger: true }}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
    </div>
  );
};

export default WorkerOrderTab;
