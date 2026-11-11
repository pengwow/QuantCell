import { useMemo } from 'react';
import { Card, Table, Tag, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import type { ColumnsType } from 'antd/es/table';
import type { BacktestFactors, FactorSnapshotRow } from '../../types/backtest';
import { buildFactorSnapshotRows } from './factorSnapshot';

// 值展示：保留 6 位有效数字，去掉尾随零（如 0.600000 -> 0.6）
const formatValue = (v: number) => String(Number(v.toPrecision(6)));

interface FactorSnapshotProps {
  factors: BacktestFactors | null | undefined;
  currentMs: number;  // 播放当前时刻（毫秒），与交易表格过滤同源
}

// 当前时刻因子快照面板：随播放进度对齐 time_series 最近 bar 展示因子值与信号。
// factors 为空（旧回测无因子数据）时不渲染任何内容。
export default function FactorSnapshot({ factors, currentMs }: FactorSnapshotProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  // 信号文案依赖 t，故随组件在 render 作用域内构建（原模块级常量移入，结构不变）
  const SIGNAL_TAG: Record<FactorSnapshotRow['signal'], { text: string; color?: 'success' | 'error' } | null> = {
    long: { text: t('backtest_factor_signal_long'), color: 'success' },
    short: { text: t('backtest_factor_signal_short'), color: 'error' },
    neutral: { text: t('backtest_factor_signal_neutral') },
    none: null,
  };
  const { rows, alignedTime } = useMemo(
    () => buildFactorSnapshotRows(factors, currentMs),
    [factors, currentMs],
  );

  const columns: ColumnsType<FactorSnapshotRow> = [
    {
      title: t('backtest_factor_name'),
      dataIndex: 'name',
      render: (name: string) => <span style={{ fontFamily: 'monospace' }}>{name}</span>,
    },
    {
      title: t('backtest_factor_current_value'),
      dataIndex: 'value',
      width: 120,
      render: (v: number | null) => (
        <span style={{ fontFamily: 'monospace' }}>{v === null ? '--' : formatValue(v)}</span>
      ),
    },
    {
      title: t('backtest_factor_buy_threshold'),
      dataIndex: 'buy',
      width: 110,
      render: (v?: number) => (typeof v === 'number' ? formatValue(v) : '--'),
    },
    {
      title: t('backtest_factor_sell_threshold'),
      dataIndex: 'sell',
      width: 110,
      render: (v?: number) => (typeof v === 'number' ? formatValue(v) : '--'),
    },
    {
      title: t('backtest_factor_signal'),
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
      title={t('backtest_factor_snapshot_title')}
      style={{ marginTop: 24 }}
      extra={
        alignedTime ? (
          <span style={{ fontSize: 12, color: token.colorTextTertiary }}>
            {t('backtest_factor_align_time', { time: alignedTime })}
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
