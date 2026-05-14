import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Table,
  Tag,
  Empty,
  Spin,
  Button,
} from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { workerApi } from '@/api/workerApi';

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
  avg_fill_price: number;
  status: 'OPEN' | 'FILLED' | 'CANCELED' | 'REJECTED' | 'ACCEPTED';
  position_id?: string;
  created_at: string;
  submitted_at?: string;
}

interface WorkerOrderTabProps {
  workerId: number;
}

const WorkerOrderTab: React.FC<WorkerOrderTabProps> = ({ workerId }) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    fetchOrderData();
  }, [workerId]);

  const fetchOrderData = async () => {
    setLoading(true);
    try {
      // 调用实际API获取委托数据
      const response: any = await workerApi.getOrders(workerId);

      if (response && response.code === 0 && response.data?.items) {
        setOrders(response.data.items);
      } else if (Array.isArray(response)) {
        // 兼容直接返回数组的格式
        setOrders(response);
      } else {
        setOrders([]);
      }
    } catch (error) {
      console.error('获取委托数据失败:', error);
      setOrders([]);
    } finally {
      setLoading(false);
    }
  };

  const columns: any = [
    {
      title: t('order_id') || '订单ID',
      dataIndex: 'client_order_id',
      key: 'client_order_id',
      width: 180,
      render: (id: string) => (
        <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>
          {id ? `${id.slice(0, 8)}...${id.slice(-6)}` : '-'}
        </span>
      ),
    },
    {
      title: t('symbol') || '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (symbol: string) => <Tag color="blue">{symbol}</Tag>,
    },
    {
      title: t('direction') || '方向',
      dataIndex: 'side',
      key: 'side',
      width: 80,
      render: (side: 'BUY' | 'SELL') => (
        <Tag color={side === 'BUY' ? 'green' : 'red'}>
          {side === 'BUY' ? (t('buy') || '买入') : (t('sell') || '卖出')}
        </Tag>
      ),
    },
    {
      title: t('order_type') || '类型',
      dataIndex: 'order_type',
      key: 'order_type',
      width: 100,
      render: (type: string) => <Tag color="orange">{type?.toUpperCase() || '-'}</Tag>,
    },
    {
      title: t('quantity') || '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      align: 'right',
      render: (qty: number) => qty?.toFixed(6) || '0',
    },
    {
      title: t('price') || '价格',
      dataIndex: 'price',
      key: 'price',
      align: 'right',
      render: (price: number) => (price ? `$${price.toFixed(2)}` : <span style={{ color: '#999' }}>市价</span>),
    },
    {
      title: t('filled_quantity') || '已成交',
      dataIndex: 'filled_qty',
      key: 'filled_qty',
      align: 'right',
      render: (qty: number, record: Order) => (
        <span>
          {qty?.toFixed(6) || '0'} / {record.quantity?.toFixed(6) || '0'}
        </span>
      ),
    },
    {
      title: t('status') || '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const colorMap: Record<string, string> = {
          'OPEN': 'processing',
          'FILLED': 'success',
          'CANCELED': 'default',
          'REJECTED': 'error',
          'ACCEPTED': 'warning',
        };
        return <Tag color={colorMap[status] || 'default'}>{status}</Tag>;
      },
    },
    {
      title: t('created_at') || '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => (time ? new Date(time).toLocaleString() : '-'),
    },
  ];

  if (loading) {
    return <Spin style={{ display: 'block', margin: '100px auto' }} />;
  }

  return (
    <div>
      <Card
        title={t('current_orders') || '当前委托'}
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={fetchOrderData}
            loading={loading}
            size="small"
          >
            {t('refresh') || '刷新'}
          </Button>
        }
      >
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
            pagination={{ pageSize: 10, size: 'small' }}
            size="middle"
            scroll={{ x: 'max-content' }}
          />
        )}
      </Card>
    </div>
  );
};

export default WorkerOrderTab;
