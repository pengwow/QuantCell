import { useMemo } from 'react';
import { Card, Table, Tag, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { BacktestFactors, FactorSnapshotRow } from '../../types/backtest';
import { buildFactorSnapshotRows } from './factorSnapshot';

// 值展示：保留 6 位有效数字，去掉尾随零（如 0.600000 -> 0.6）
const formatValue = (v: number) => String(Number(v.toPrecision(6)));

interface FactorSnapshotProps {
  factors: BacktestFactors | null | undefined;
  currentMs: number;  // 播放当前时刻（毫秒），与交易表格过滤同源
}

// 信号 -> Tag 预设状态色（自动跟随 antd 主题 token，禁止硬编码色值）
const SIGNAL_TAG: Record<FactorSnapshotRow['signal'], { text: string; color?: 'success' | 'error' } | null> = {
  long: { text: '看多', color: 'success' },
  short: { text: '看空', color: 'error' },
  neutral: { text: '中性', color: undefined },
  none: null,
};

// 当前时刻因子快照面板：随播放进度对齐 time_series 最近 bar 展示因子值与信号。
// factors 为空（旧回测无因子数据）时不渲染任何内容。
export default function FactorSnapshot({ factors, currentMs }: FactorSnapshotProps) {
  const { token } = theme.useToken();
  const { rows, alignedTime } = useMemo(
    () => buildFactorSnapshotRows(factors, currentMs),
    [factors, currentMs],
  );

  const columns: ColumnsType<FactorSnapshotRow> = [
    {
      title: '因子名称',
      dataIndex: 'name',
      render: (name: string) => <span style={{ fontFamily: 'monospace' }}>{name}</span>,
    },
    {
      title: '当前值',
      dataIndex: 'value',
      width: 120,
      render: (v: number | null) => (
        <span style={{ fontFamily: 'monospace' }}>{v === null ? '--' : formatValue(v)}</span>
      ),
    },
    {
      title: 'Buy 阈值',
      dataIndex: 'buy',
      width: 110,
      render: (v?: number) => (typeof v === 'number' ? formatValue(v) : '--'),
    },
    {
      title: 'Sell 阈值',
      dataIndex: 'sell',
      width: 110,
      render: (v?: number) => (typeof v === 'number' ? formatValue(v) : '--'),
    },
    {
      title: '信号',
      dataIndex: 'signal',
      width: 90,
      render: (s: FactorSnapshotRow['signal']) => {
        const meta = SIGNAL_TAG[s];
        if (!meta) return '--';
        return meta.color ? <Tag color={meta.color}>{meta.text}</Tag> : <Tag>{meta.text}</Tag>;
      },
    },
  ];

  if (!rows.length) return null;

  return (
    <Card
      size="small"
      title="当前因子快照"
      style={{ marginTop: 24 }}
      extra={
        alignedTime ? (
          <span style={{ fontSize: 12, color: token.colorTextTertiary }}>
            对齐 {alignedTime}
          </span>
        ) : undefined
      }
    >
      <Table<FactorSnapshotRow>
        size="small"
        columns={columns}
        dataSource={rows}
        rowKey="name"
        pagination={false}
        scroll={{ y: 260 }}
      />
    </Card>
  );
}
