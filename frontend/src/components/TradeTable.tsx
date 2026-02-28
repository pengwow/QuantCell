/**
 * 交易详情表格组件
 * 功能：展示交易记录的详细信息，支持分页和收益颜色标识
 * 适用场景：回测结果、交易记录、订单历史等
 */
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';

// 交易数据接口
export interface Trade {
  EntryTime: string;
  ExitTime: string;
  Direction: string;
  EntryPrice: number;
  ExitPrice: number;
  Size: number;
  PnL: number;
  ReturnPct: number;
}

// 组件属性接口
export interface TradeTableProps {
  data: Trade[];
  loading?: boolean;
  pagination?: boolean;
}

/**
 * 格式化日期时间
 */
const formatDateTime = (datetime: string): string => {
  return dayjs(datetime).format('YYYY-MM-DD HH:mm:ss');
};

/**
 * 格式化价格，保留4位小数
 */
const formatPrice = (price: number): string => {
  return price.toFixed(4);
};

/**
 * 格式化仓位，保留2位小数
 */
const formatSize = (size: number): string => {
  return size.toFixed(2);
};

/**
 * 格式化收益，保留2位小数
 */
const formatPnL = (pnl: number): string => {
  return pnl.toFixed(2);
};

/**
 * 格式化收益率，显示百分比
 */
const formatReturnPct = (returnPct: number): string => {
  return `${(returnPct * 100).toFixed(2)}%`;
};

const TradeTable = ({ data, loading = false, pagination = true }: TradeTableProps) => {
  // 表格列定义
  const columns: ColumnsType<Trade> = [
    {
      title: '入场时间',
      dataIndex: 'EntryTime',
      key: 'EntryTime',
      render: (value: string) => formatDateTime(value),
      sorter: (a, b) => dayjs(a.EntryTime).unix() - dayjs(b.EntryTime).unix(),
    },
    {
      title: '出场时间',
      dataIndex: 'ExitTime',
      key: 'ExitTime',
      render: (value: string) => formatDateTime(value),
      sorter: (a, b) => dayjs(a.ExitTime).unix() - dayjs(b.ExitTime).unix(),
    },
    {
      title: '方向',
      dataIndex: 'Direction',
      key: 'Direction',
      render: (value: string) => {
        const isLong = value.toLowerCase() === 'long' || value === '做多';
        return (
          <Tag color={isLong ? 'green' : 'red'}>
            {isLong ? '做多' : '做空'}
          </Tag>
        );
      },
    },
    {
      title: '入场价格',
      dataIndex: 'EntryPrice',
      key: 'EntryPrice',
      render: (value: number) => formatPrice(value),
      align: 'right',
    },
    {
      title: '出场价格',
      dataIndex: 'ExitPrice',
      key: 'ExitPrice',
      render: (value: number) => formatPrice(value),
      align: 'right',
    },
    {
      title: '仓位',
      dataIndex: 'Size',
      key: 'Size',
      render: (value: number) => formatSize(value),
      align: 'right',
    },
    {
      title: '收益',
      dataIndex: 'PnL',
      key: 'PnL',
      render: (value: number) => (
        <span style={{ color: value >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {formatPnL(value)}
        </span>
      ),
      align: 'right',
      sorter: (a, b) => a.PnL - b.PnL,
    },
    {
      title: '收益率',
      dataIndex: 'ReturnPct',
      key: 'ReturnPct',
      render: (value: number) => (
        <span style={{ color: value >= 0 ? '#52c41a' : '#ff4d4f' }}>
          {formatReturnPct(value)}
        </span>
      ),
      align: 'right',
      sorter: (a, b) => a.ReturnPct - b.ReturnPct,
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey={(record, index) => `${record.EntryTime}-${index}`}
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
