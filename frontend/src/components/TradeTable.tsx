/**
 * 交易详情表格组件（round-trip 开平配对契约）
 * 契约与后端 backtest_loop._build_round_trip_trades 输出一一对应，
 * 2026-07-25 起引擎只产出该格式，旧格式数据由详情页空态提示
 */
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Trade } from '../types/backtest';

export type { Trade };

// 组件属性接口
export interface TradeTableProps {
  data: Trade[];
  loading?: boolean;
  pagination?: boolean;
  // 可选行类名（如组合回放中新成交行高亮）
  rowClassName?: (record: Trade) => string;
}

const formatPrice = (price: number): string => price.toFixed(4);

const formatQuantity = (quantity: number): string => quantity.toFixed(4);

const formatVolume = (volume: number): string => volume.toFixed(2);

const TradeTable = ({ data, loading = false, pagination = true, rowClassName }: TradeTableProps) => {
  const columns: ColumnsType<Trade> = [
    {
      title: '时间',
      dataIndex: 'formatted_time',
      key: 'formatted_time',
      sorter: (a, b) => a.timestamp - b.timestamp,
    },
    {
      title: '方向',
      dataIndex: 'side',
      key: 'side',
      // side 是开仓方向（buy/sell），非平仓方向
      render: (value: string) => {
        const isBuy = (value || '').toLowerCase() === 'buy';
        return <Tag color={isBuy ? 'green' : 'red'}>{isBuy ? '买入' : '卖出'}</Tag>;
      },
    },
    {
      title: '开仓价',
      dataIndex: 'entry_price',
      key: 'entry_price',
      render: (value: number) => formatPrice(value),
      align: 'right',
    },
    {
      title: '平仓价',
      dataIndex: 'exit_price',
      key: 'exit_price',
      render: (value: number) => formatPrice(value),
      align: 'right',
    },
    {
      title: '数量',
      dataIndex: 'size',
      key: 'size',
      render: (value: number) => formatQuantity(value),
      align: 'right',
    },
    {
      title: '金额',
      key: 'notional',
      // 契约无金额字段，按开仓价 × 数量计算
      render: (_: unknown, record: Trade) => formatVolume(record.entry_price * record.size),
      align: 'right',
    },
    {
      title: '收益',
      dataIndex: 'pnl',
      key: 'pnl',
      // 已实现盈亏，正绿负红，附收益率
      render: (value: number, record: Trade) => (
        <span style={{ color: value >= 0 ? '#3f8600' : '#cf1322', fontWeight: 500 }}>
          {value.toFixed(4)} ({record.return_pct.toFixed(2)}%)
        </span>
      ),
      align: 'right',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => {
        const statusMap: Record<string, { color: string; text: string }> = {
          FILLED: { color: 'green', text: '已成交' },
          PENDING: { color: 'orange', text: '待成交' },
          CANCELLED: { color: 'red', text: '已取消' },
        };
        const status = statusMap[value?.toUpperCase()] || { color: 'default', text: value || '-' };
        return <Tag color={status.color}>{status.text}</Tag>;
      },
    },
    {
      title: '交易标的',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (value: string) => <span style={{ fontFamily: 'monospace' }}>{value || '-'}</span>,
      ellipsis: true,
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey="trade_id"
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
      rowClassName={rowClassName}
    />
  );
};

export default TradeTable;
