import { useEffect, useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Table,
  Tag,
  Spin,
  Select,
  Space,
} from 'antd';
import { useWorkerStore } from '../../store/workerStore';
import type { WorkerTrade } from '../../types/worker';

interface WorkerTradesTabProps {
  workerId: number;
}

const WorkerTradesTab: React.FC<WorkerTradesTabProps> = ({ workerId }) => {
  const { t } = useTranslation();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 10 });
  const [sideFilter, setSideFilter] = useState<string | undefined>(undefined);

  const {
    trades,
    loadingTrades,
    fetchTrades,
  } = useWorkerStore();

  useEffect(() => {
    fetchTrades(workerId);
  }, [workerId, fetchTrades]);

  // 筛选成交记录
  const filteredTrades = useMemo(() => {
    if (!sideFilter) return trades;
    return trades.filter(trade => trade.side === sideFilter);
  }, [trades, sideFilter]);

  // 使用 any 类型避免复杂的 Table columns 类型推断问题
  const columns: any = [
    {
      title: t('trade_time') || '成交时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (text: string) => new Date(text).toLocaleString(),
    },
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('action') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      filters: [
        { text: t('buy') || '买入', value: 'buy' },
        { text: t('sell') || '卖出', value: 'sell' },
      ],
      onFilter: (value: boolean | React.Key, record: WorkerTrade) => String(record.side) === String(value),
      render: (side: 'buy' | 'sell') => (
        <Tag color={side === 'buy' ? 'red' : 'green'}>
          {side === 'buy' ? (t('buy') || '买入') : (t('sell') || '卖出')}
        </Tag>
      ),
    },
    {
      title: t('price') || '价格',
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price: number) => `$${price.toFixed(2)}`,
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
    },
    {
      title: t('amount') || '金额',
      dataIndex: 'amount',
      key: 'amount',
      align: 'right',
      render: (amount: number) => `$${amount.toFixed(2)}`,
    },
    {
      title: t('status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const statusMap: Record<string, { text: string; color: string }> = {
          filled: { text: t('filled') || '已成交', color: 'success' },
          pending: { text: t('pending') || '待成交', color: 'warning' },
          cancelled: { text: t('cancelled') || '已取消', color: 'default' },
        };
        const { text, color } = statusMap[status] || { text: status, color: 'default' };
        return <Tag color={color}>{text}</Tag>;
      },
    },
  ];

  return (
    <Card
      title={
        <Space>
          <span>{t('trade_records') || '成交记录'}</span>
          {loadingTrades && <Spin size="small" />}
        </Space>
      }
      extra={
        <Space>
          <span>{t('filter_by_direction') || '筛选方向'}:</span>
          <Select
            allowClear
            style={{ width: 100 }}
            placeholder={t('all') || '全部'}
            value={sideFilter}
            onChange={setSideFilter}
            options={[
              { label: t('buy') || '买入', value: 'buy' },
              { label: t('sell') || '卖出', value: 'sell' },
            ]}
          />
        </Space>
      }
    >
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
          showTotal: (total) => `${t('total_items') || '共'} ${total} ${t('items') || '条'}`,
          onChange: (page, pageSize) => {
            setPagination({ current: page, pageSize: pageSize || 10 });
          },
        }}
        size="middle"
        scroll={{ x: 'max-content' }}
      />
    </Card>
  );
};

export default WorkerTradesTab;
