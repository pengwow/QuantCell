/**
 * 右栏 ② 持仓/订单：GET /workers/{id}/strategy/positions（OPEN 兜底推导）+
 * GET /workers/{id}/strategy/orders（分页契约，取第一页最新 20 条）。
 * 数据走 workbenchStore 缓存（useWorkbenchData 5s 轮询）。
 */
import { Empty, Table } from 'antd';
import type { TableColumnsType } from 'antd';
import { useTranslation } from 'react-i18next';
import { useWorkbenchStore } from '../../store/workbenchStore';
import type { OrderInfo, PositionInfo } from '@/types/worker';
import type { Side } from '@/types/vocab.generated';
import { formatQuantity, formatTimestamp, formatUSD } from '@/utils/format';

const SubTitle = ({ text }: { text: string }) => <div className="wb-section-title">{text}</div>;

/** 方向/动作 → §6.2 qc-chip 档位（多空、买卖各归涨跌语义） */
const SIDE_CHIP_LEVEL: Record<string, string> = { long: 'ok', buy: 'ok', short: 'down', sell: 'down' };

export default function PositionsTab() {
  const { t } = useTranslation();
  const workerId = useWorkbenchStore((s) => s.workerId);
  const positionsEntry = useWorkbenchStore((s) => s.positions);
  const ordersEntry = useWorkbenchStore((s) => s.orders);

  if (!workerId) {
    return <Empty description={t('wb_select_worker')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  // 持仓/订单同轮拉取，以持仓缓存到/未到表示整组的加载态
  if (!positionsEntry || positionsEntry.workerId !== workerId) {
    return <Empty description={t('no_data')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const positions = positionsEntry.data.filter((p) => p.status === 'OPEN' || p.quantity !== 0);

  const positionColumns: TableColumnsType<PositionInfo> = [
    // 标的标识列：mono 文本（§6.5 表格，不再挂蓝色徽章）
    { title: t('symbol'), dataIndex: 'symbol', width: 110, render: (v: string) => <span className="wb-nowrap-mono">{v}</span> },
    {
      title: t('direction'),
      dataIndex: 'position_side',
      width: 80,
      render: (side: PositionInfo['position_side']) => (
        <span className={`qc-chip ${SIDE_CHIP_LEVEL[side] ?? 'quiet'}`}>
          {side === 'long' ? t('position_side_long') : side === 'short' ? t('position_side_short') : t('position_side_both')}
        </span>
      ),
    },
    { title: t('quantity'), dataIndex: 'quantity', align: 'right', width: 100, render: (v: number) => formatQuantity(v) },
    { title: t('entry_price'), dataIndex: 'entry_price', align: 'right', width: 110, render: (v: number) => formatUSD(v) },
    { title: t('worker_mark_price'), dataIndex: 'mark_price', align: 'right', width: 110, render: (v?: number) => (v == null ? '-' : formatUSD(v)) },
    {
      title: t('wb_unrealized_pnl'),
      dataIndex: 'unrealized_pnl',
      align: 'right',
      width: 120,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? 'var(--agent-up)' : 'var(--agent-down)' }}>
          {formatUSD(v, { showSign: true })}
        </span>
      ),
    },
  ];

  const orderColumns: TableColumnsType<OrderInfo> = [
    { title: t('backtest_time'), dataIndex: 'created_at', width: 160, render: (v: string) => <span className="wb-nowrap-mono">{formatTimestamp(v)}</span> },
    { title: t('symbol'), dataIndex: 'symbol', width: 110, render: (v: string) => <span className="wb-nowrap-mono">{v}</span> },
    {
      title: t('backtest_action'),
      dataIndex: 'side',
      width: 80,
      render: (side: Side) => <span className={`qc-chip ${SIDE_CHIP_LEVEL[side] ?? 'quiet'}`}>{(side || '').toUpperCase()}</span>,
    },
    { title: t('quantity'), dataIndex: 'quantity', align: 'right', width: 100, render: (v: number) => formatQuantity(v) },
    { title: t('status'), dataIndex: 'status', width: 100, render: (v: string) => <span className="qc-chip quiet">{(v || '-').toUpperCase()}</span> },
  ];

  return (
    <div className="wb-positions">
      <SubTitle text={t('wb_section_positions')} />
      {positions.length === 0 ? (
        <Empty description={t('wb_no_open_positions')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Table<PositionInfo>
          size="small"
          rowKey={(p) => p.position_id || `${p.symbol}:${p.position_side}`}
          dataSource={positions}
          columns={positionColumns}
          pagination={false}
        />
      )}

      <SubTitle text={t('wb_section_orders')} />
      {!ordersEntry || ordersEntry.workerId !== workerId || ordersEntry.data.length === 0 ? (
        <Empty description={t('no_data')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Table<OrderInfo>
          size="small"
          rowKey={(o) => o.order_id || String(o.client_order_id ?? o.created_at)}
          dataSource={ordersEntry.data.slice(0, 20)}
          columns={orderColumns}
          pagination={false}
        />
      )}
    </div>
  );
}
