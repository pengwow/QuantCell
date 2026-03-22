/**
 * 交易详情表格组件
 * 功能：展示交易记录的详细信息，支持分页和收益颜色标识
 * 适配后端返回格式：{ trade_id, side, direction, quantity, price, volume, commission, timestamp, formatted_time, status }
 */
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';

// 后端返回的交易数据接口
export interface Trade {
  trade_id: string;
  client_order_id?: string;
  venue_order_id?: string;
  position_id?: string;
  instrument_id?: string;
  side?: string;
  Side?: string;
  direction?: string;
  Direction?: string;
  quantity: number;
  price: number;
  volume: number;
  commission: string;
  timestamp: number;
  formatted_time: string;
  status?: string;
  Status?: string;
}

// 组件属性接口
export interface TradeTableProps {
  data: Trade[];
  loading?: boolean;
  pagination?: boolean;
}

/**
 * 格式化价格，保留4位小数
 */
const formatPrice = (price: number): string => {
  if (typeof price !== 'number') return '-';
  return price.toFixed(4);
};

/**
 * 格式化数量，保留4位小数
 */
const formatQuantity = (quantity: number): string => {
  if (typeof quantity !== 'number') return '-';
  return quantity.toFixed(4);
};

/**
 * 格式化金额，保留2位小数
 */
const formatVolume = (volume: number): string => {
  if (typeof volume !== 'number') return '-';
  return volume.toFixed(2);
};

const TradeTable = ({ data, loading = false, pagination = true }: TradeTableProps) => {
  // 表格列定义
  const columns: ColumnsType<Trade> = [
    {
      title: '时间',
      dataIndex: 'formatted_time',
      key: 'formatted_time',
      render: (value: string) => value || '-',
      sorter: (a, b) => (a.timestamp || 0) - (b.timestamp || 0),
    },
    {
      title: '方向',
      dataIndex: 'side',
      key: 'side',
      render: (value: string, record: Trade) => {
        const isBuy = value?.toUpperCase() === 'BUY' || record.direction?.includes('买入');
        return (
          <Tag color={isBuy ? 'green' : 'red'}>
            {record.direction || value || '-'}
          </Tag>
        );
      },
    },
    {
      title: '价格',
      dataIndex: 'price',
      key: 'price',
      render: (value: number) => formatPrice(value),
      align: 'right',
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      render: (value: number) => formatQuantity(value),
      align: 'right',
    },
    {
      title: '金额',
      dataIndex: 'volume',
      key: 'volume',
      render: (value: number) => formatVolume(value),
      align: 'right',
    },
    {
      title: '手续费',
      dataIndex: 'commission',
      key: 'commission',
      render: (value: string) => value || '-',
      align: 'right',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => {
        const statusMap: Record<string, { color: string; text: string }> = {
          'FILLED': { color: 'green', text: '已成交' },
          'PENDING': { color: 'orange', text: '待成交' },
          'CANCELLED': { color: 'red', text: '已取消' },
        };
        const status = statusMap[value?.toUpperCase()] || { color: 'default', text: value || '-' };
        return <Tag color={status.color}>{status.text}</Tag>;
      },
    },
    {
      title: '交易标的',
      dataIndex: 'instrument_id',
      key: 'instrument_id',
      render: (value: string) => value || '-',
      ellipsis: true,
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey={(record) => record.trade_id || `${record.timestamp}-${Math.random()}`}
      loading={loading}
      pagination={
        pagination
          ? {
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total, range) =>
                `第 ${range[0]}-${range[1]} 条，共 ${total} 条`,
              defaultPageSize: 10,
              pageSizeOptions: ['10', '20', '50', '100'],
            }
          : false
      }
      size="small"
      scroll={{ x: 'max-content' }}
    />
  );
};

export default TradeTable;
