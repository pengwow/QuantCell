/**
 * Worker 成交记录 Tab
 *
 * 展示 Worker 的历史成交记录（trades）：
 * - 字段补齐：fee、pnl、holding_period
 * - 「导出 CSV」按钮
 * - 时间/数字/颜色格式标准化
 * - 高级筛选：交易对、方向、时间范围
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
} from 'antd';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { useWorkerStore } from '../../store/workerStore';
import type { WorkerTrade } from '../../types/worker';
import { formatTimestamp, formatUSD, QUANT_COLORS } from '../../utils/format';
import { downloadCsv, timestampedFilename } from '../../utils/exportCsv';

const { RangePicker } = DatePicker;

interface WorkerTradesTabProps {
  workerId: number;
}

interface FilterValues {
  symbol?: string;
  side?: string;
  time_range?: [Dayjs, Dayjs];
}

const WorkerTradesTab: React.FC<WorkerTradesTabProps> = ({ workerId }) => {
  const { t } = useTranslation();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 });
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [filters, setFilters] = useState<FilterValues>({});
  const [filterDraft, setFilterDraft] = useState<FilterValues>({});

  const { trades, loadingTrades, fetchTrades } = useWorkerStore();

  useEffect(() => {
    fetchTrades(workerId, {
      symbol: filters.symbol,
      start_time: filters.time_range?.[0]?.toISOString(),
      end_time: filters.time_range?.[1]?.toISOString(),
    });
  }, [workerId, filters, fetchTrades]);

  // 客户端再过滤一次 side（store 可能不支持）
  const filteredTrades = useMemo(() => {
    let result = trades;
    if (filters.side) {
      result = result.filter((trade) => trade.side === filters.side);
    }
    return result;
  }, [trades, filters]);

  // 汇总指标
  const summary = useMemo(() => {
    const totalPnl = filteredTrades.reduce(
      (sum, t) => sum + (t.realized_pnl || 0),
      0,
    );
    const totalFee = filteredTrades.reduce((sum, t) => sum + (t.fee || 0), 0);
    const totalVolume = filteredTrades.reduce(
      (sum, t) => sum + (t.price || 0) * (t.quantity || 0),
      0,
    );
    return { totalPnl, totalFee, totalVolume, totalTrades: filteredTrades.length };
  }, [filteredTrades]);

  // 应用筛选
  const handleApplyFilter = () => {
    setFilters(filterDraft);
  };

  // 重置筛选
  const handleResetFilter = () => {
    setFilterDraft({});
    setFilters({});
  };

  // 手动刷新
  const handleManualRefresh = () => {
    fetchTrades(workerId, {
      symbol: filters.symbol,
      start_time: filters.time_range?.[0]?.toISOString(),
      end_time: filters.time_range?.[1]?.toISOString(),
    });
  };

  // 导出 CSV
  const handleExport = () => {
    downloadCsv(
      timestampedFilename('worker_trades', workerId),
      filteredTrades,
      [
        { header: '成交ID', accessor: 'trade_id' },
        { header: '成交时间', accessor: (t) => (t.created_at ? formatTimestamp(t.created_at) : '') },
        { header: '交易对', accessor: 'symbol' },
        { header: '方向', accessor: 'side' },
        { header: '订单类型', accessor: 'order_type' },
        { header: '价格', accessor: 'price' },
        { header: '数量', accessor: 'quantity' },
        { header: '金额', accessor: 'amount' },
        { header: '手续费', accessor: (t) => (t.fee !== undefined ? `${t.fee} ${t.fee_currency || ''}` : '') },
        { header: '已实现盈亏', accessor: 'realized_pnl' },
        { header: '收益率(%)', accessor: 'realized_pnl_pct' },
        { header: '开仓时间', accessor: (t) => (t.entry_time ? formatTimestamp(t.entry_time) : '') },
        { header: '平仓时间', accessor: (t) => (t.exit_time ? formatTimestamp(t.exit_time) : '') },
      ],
    );
  };

  // 表格列：标准量化展示顺序
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const columns: any = [
    {
      title: t('trade_time') || '成交时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (text: string) => (text ? formatTimestamp(text) : '-'),
    },
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 110,
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('action') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'buy' | 'sell') => (
        <Tag color={side === 'buy' ? 'green' : 'red'}>
          {side === 'buy' ? 'BUY' : 'SELL'}
        </Tag>
      ),
    },
    {
      title: '订单类型',
      dataIndex: 'order_type',
      key: 'order_type',
      width: 110,
      render: (type: string) => (type ? <Tag color="orange">{type.toUpperCase()}</Tag> : '-'),
    },
    {
      title: t('price') || '价格',
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price: number) => formatUSD(price),
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => (qty !== undefined ? qty.toFixed(6) : '-'),
    },
    {
      title: t('amount') || '金额',
      dataIndex: 'amount',
      key: 'amount',
      align: 'right',
      render: (amount: number) => formatUSD(amount),
    },
    {
      title: '手续费',
      dataIndex: 'fee',
      key: 'fee',
      align: 'right',
      width: 120,
      render: (fee: number, record: WorkerTrade) =>
        fee !== undefined ? `${fee.toFixed(4)} ${record.fee_currency || ''}` : '-',
    },
    {
      title: '已实现盈亏',
      dataIndex: 'realized_pnl',
      key: 'realized_pnl',
      align: 'right',
      width: 140,
      render: (pnl: number) => {
        if (pnl === undefined || pnl === null) return '-';
        return (
          <span
            style={{
              fontWeight: 600,
              color: pnl >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
            }}
          >
            {formatUSD(pnl, { showSign: true })}
          </span>
        );
      },
    },
    {
      title: '收益率',
      dataIndex: 'realized_pnl_pct',
      key: 'realized_pnl_pct',
      align: 'right',
      width: 100,
      render: (pct: number) => {
        if (pct === undefined || pct === null) return '-';
        return (
          <span
            style={{
              fontWeight: 600,
              color: pct >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
            }}
          >
            {(pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'}
          </span>
        );
      },
    },
    {
      title: '持仓时长',
      key: 'holding_period',
      width: 110,
      render: (_: unknown, record: WorkerTrade) => {
        if (!record.entry_time || !record.exit_time) return '-';
        const diff = dayjs(record.exit_time).diff(dayjs(record.entry_time), 'minute');
        if (diff < 0) return '-';
        const days = Math.floor(diff / (60 * 24));
        const hours = Math.floor((diff % (60 * 24)) / 60);
        const minutes = diff % 60;
        if (days > 0) return `${days}d ${hours}h ${minutes}m`;
        if (hours > 0) return `${hours}h ${minutes}m`;
        return `${minutes}m`;
      },
    },
  ];

  return (
    <div>
      {/* 汇总指标 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic
              title="总成交笔数"
              value={summary.totalTrades}
              valueStyle={{ color: QUANT_COLORS.info }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic
              title="总成交金额"
              value={summary.totalVolume}
              precision={2}
              prefix="$"
              valueStyle={{ color: QUANT_COLORS.info }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic
              title="总已实现盈亏"
              value={summary.totalPnl}
              precision={2}
              prefix="$"
              valueStyle={{
                color: summary.totalPnl >= 0 ? QUANT_COLORS.positive : QUANT_COLORS.negative,
              }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic
              title="总手续费"
              value={summary.totalFee}
              precision={4}
              prefix="$"
              valueStyle={{ color: QUANT_COLORS.warning }}
            />
          </Card>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <span>{t('trade_records') || '成交记录'}</span>
            {loadingTrades && <Spin size="small" />}
          </Space>
        }
        extra={
          <Space>
            <Button
              icon={<SearchOutlined />}
              size="small"
              onClick={() => setFilterCollapsed(!filterCollapsed)}
            >
              {filterCollapsed ? '收起筛选' : '展开筛选'}
            </Button>
            <Button
              icon={<ReloadOutlined />}
              size="small"
              loading={loadingTrades}
              onClick={handleManualRefresh}
            >
              刷新
            </Button>
            <Button
              icon={<DownloadOutlined />}
              size="small"
              disabled={filteredTrades.length === 0}
              onClick={handleExport}
            >
              导出 CSV
            </Button>
          </Space>
        }
      >
        {/* 筛选面板 */}
        {filterCollapsed && (
          <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <Input
              placeholder="交易对 (如 BTCUSDT)"
              allowClear
              style={{ width: 160 }}
              value={filterDraft.symbol}
              onChange={(e) => setFilterDraft({ ...filterDraft, symbol: e.target.value || undefined })}
            />
            <Select
              placeholder="方向"
              allowClear
              style={{ width: 100 }}
              value={filterDraft.side}
              onChange={(v) => setFilterDraft({ ...filterDraft, side: v })}
              options={[
                { label: 'BUY', value: 'buy' },
                { label: 'SELL', value: 'sell' },
              ]}
            />
            <RangePicker
              showTime={{ format: 'HH:mm:ss' }}
              format="YYYY-MM-DD HH:mm:ss"
              value={filterDraft.time_range}
              onChange={(v) => setFilterDraft({ ...filterDraft, time_range: v as [Dayjs, Dayjs] | undefined })}
            />
            <Button type="primary" onClick={handleApplyFilter}>
              应用
            </Button>
            <Button onClick={handleResetFilter}>重置</Button>
          </div>
        )}

        {filteredTrades.length === 0 ? (
          <Empty
            description={t('no_trade_data') || '暂无成交记录'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            columns={columns}
            dataSource={filteredTrades}
            rowKey="id"
            loading={loadingTrades}
            pagination={{
              ...pagination,
              total: filteredTrades.length,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => {
                setPagination({ current: page, pageSize: pageSize || 10 });
              },
            }}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
    </div>
  );
};

export default WorkerTradesTab;
