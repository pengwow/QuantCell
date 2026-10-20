/**
 * 交易详情表格组件（round-trip 开平配对契约）
 * 契约与后端 backtest_loop._build_round_trip_trades 输出一一对应，
 * 2026-07-25 起引擎只产出该格式，旧格式数据由详情页空态提示
 */
import { Table, Tag, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { Trade, TradeFill } from '../types/backtest';

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
  const { token } = theme.useToken();

  const columns: ColumnsType<Trade> = [
    {
      title: '时间',
      dataIndex: 'formatted_time',
      key: 'formatted_time',
      sorter: (a, b) => a.timestamp - b.timestamp,
    },
    {
      title: '方向',
      dataIndex: 'direction',
      key: 'direction',
      // direction 是持仓方向（long/short）
      render: (value: string) =>
        value === 'long' ? <Tag color="green">多</Tag> : <Tag color="red">空</Tag>,
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
      // 契约只有 round-trip 已平仓交易，状态弱化展示
      render: () => (
        <span style={{ color: token.colorTextTertiary, fontSize: 12 }}>已平仓</span>
      ),
    },
    {
      title: '交易标的',
      dataIndex: 'symbol',
      key: 'symbol',
      render: (value: string) => <span style={{ fontFamily: 'monospace' }}>{value || '-'}</span>,
      ellipsis: true,
    },
  ];

  // 行内展开：逐笔成交明细（开仓 + 平仓 fill）
  const renderFills = (record: Trade) => {
    const fills = record.fills ?? [];
    const cols: ColumnsType<TradeFill> = [
      { title: '成交时间', dataIndex: 'formatted_time', key: 't' },
      {
        title: '方向',
        dataIndex: 'side',
        key: 'side',
        render: (v: string) => (
          <Tag color={v === 'buy' ? 'green' : 'red'}>{v === 'buy' ? '买入' : '卖出'}</Tag>
        ),
      },
      {
        title: '开/平',
        dataIndex: 'offset',
        key: 'off',
        render: (v: string) => <Tag>{v === 'open' ? '开仓' : '平仓'}</Tag>,
      },
      { title: '成交价', dataIndex: 'price', key: 'p', render: (v: number) => v.toFixed(4), align: 'right' },
      { title: '数量', dataIndex: 'quantity', key: 'q', render: (v: number) => v.toFixed(4), align: 'right' },
      { title: '盈亏', dataIndex: 'pnl', key: 'pnl', render: (v: number) => v.toFixed(2), align: 'right' },
    ];
    return (
      <div style={{ padding: '8px 0' }}>
        {fills.length === 0 ? (
          <span style={{ color: '#999' }}>无逐笔明细</span>
        ) : (
          <>
            <Table size="small" rowKey="fill_id" columns={cols} dataSource={fills} pagination={false} />
            <div style={{ color: '#aaa', fontSize: 12, marginTop: 4 }}>
              提示：同向加仓持仓共享开仓成交，部分平仓可能复现同一开仓记录（引擎口径）。
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <Table
      columns={columns}
      dataSource={data}
      expandable={{ expandedRowRender: renderFills }}
      // 旧版多品种结果各品种独立编号 rt-N 会重复，叠加 symbol 保证 rowKey 唯一
      rowKey={(record) => `${record.symbol}-${record.trade_id}`}
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
