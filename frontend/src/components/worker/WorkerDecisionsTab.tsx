/**
 * Worker 决策 tab：cascade 策略在 paper/testnet 运行期的决策轻列表。
 * 数据源 GET /workers/{id}/decisions（录制文件 worker_{id}.jsonl，时间倒序）。
 * 详情 Drawer 复用回测侧组件，四区块内容口径完全一致。
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, Button, Card, Space, Spin, Tooltip, Typography } from 'antd';
import { getWorkerDecisionDetail, getWorkerDecisions } from '../../api/workerApi';
import type { CascadeDecisionRecord } from '../../types/backtest';
import DataTable, { QcEmpty } from '@/components/ui/DataTable';
import DecisionDetailDrawer, { fmtDecisionTs, humanizeFallbackReason } from '../../pages/backtest/DecisionDetailDrawer';

const PAGE_SIZE = 200;

// 决策动作 → §6.2 chip 语义档：buy=up / sell=down / hold=quiet
const ACTION_CHIP_CLS: Record<string, string> = { buy: ' ok', sell: ' down', hold: ' quiet' };

interface Props {
  workerId: number;
  active: boolean; // tab 激活才请求，避免所有 tab 全量拉取
}

export default function WorkerDecisionsTab({ workerId, active }: Props) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<CascadeDecisionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [detailRecord, setDetailRecord] = useState<CascadeDecisionRecord | null>(null);

  useEffect(() => {
    if (!active) return;
    setLoading(true);
    setError('');
    getWorkerDecisions(workerId)
      .then((data) => {
        setRows(data?.decisions || []);
        setTotal(data?.total || 0);
      })
      .catch((e) => setError(e?.message || String(e)))
      .finally(() => setLoading(false));
  }, [active, workerId]);

  const fallbackCount = rows.filter((r) => r.source === 'fallback' || r.fallback_reason).length;

  return (
    <Spin spinning={loading}>
      <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
        {error && <Alert type="warning" showIcon title={t('worker_decision_load_failed', { error })} />}
        <Card
          className="qc-card"
          title={
            <Space wrap>
              <span>{t('worker_decision_records')}</span>
              <Typography.Text type="secondary">{t('total_items', { total })}</Typography.Text>
              {rows.length > 0 && (
                <span className={`qc-chip${fallbackCount > 0 ? ' warn' : ' ok'}`}>
                  {t('worker_decision_fallback_count', { count: fallbackCount, total: rows.length })}
                </span>
              )}
            </Space>
          }
          extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>{t('worker_decision_recent', { count: rows.length })}</Typography.Text>}
        >
          {rows.length === 0 && !loading ? (
            <QcEmpty title={t('worker_decisions_empty')} />
          ) : (
            <DataTable
              rowKey={(r) => `${r._seq}:${r.fingerprint}`}
              dataSource={rows}
              pagination={{ pageSize: PAGE_SIZE, showSizeChanger: false }}
              columns={[
                {
                  title: t('backtest_time'),
                  dataIndex: '_ts',
                  width: 180,
                  // §6.5 时间列：mono 11px fg-3 口径
                  render: (ts: string) => (
                    <Tooltip title={ts || '-'}>
                      <span className="qc-cell-time qc-mono">{fmtDecisionTs(ts)}</span>
                    </Tooltip>
                  ),
                },
                {
                  title: t('backtest_action'),
                  dataIndex: 'action',
                  width: 80,
                  render: (a: string) => (
                    <span className={`qc-chip${ACTION_CHIP_CLS[a] ?? ' quiet'}`}>{a}</span>
                  ),
                },
                {
                  title: t('backtest_confidence'),
                  dataIndex: 'confidence',
                  width: 100,
                  align: 'right',
                  render: (v: number) => (typeof v === 'number' ? <span className="qc-mono">{v.toFixed(4)}</span> : <span className="qc-mono qc-cell-none">—</span>),
                },
                { title: t('backtest_decider'), dataIndex: '_decider', width: 130, render: (v: string) => v || '-' },
                {
                  title: t('backtest_fallback_reason'),
                  dataIndex: 'fallback_reason',
                  ellipsis: true,
                  render: (reason: string) =>
                    reason ? (
                      <Tooltip title={reason}>
                        <span>{humanizeFallbackReason(reason)}</span>
                      </Tooltip>
                    ) : (
                      <span style={{ color: 'var(--qc-text-tertiary)' }}>—</span>
                    ),
                },
                {
                  title: t('action'),
                  width: 80,
                  fixed: 'right',
                  render: (_: unknown, record: CascadeDecisionRecord) =>
                    record._seq == null ? (
                      <Tooltip title={t('worker_decision_no_seq')}>
                        <Button size="small" disabled>{t('detail')}</Button>
                      </Tooltip>
                    ) : (
                      <Button size="small" onClick={() => setDetailRecord(record)}>{t('detail')}</Button>
                    ),
                },
              ]}
            />
          )}
        </Card>
      </Space>
      <DecisionDetailDrawer
        fetchDetail={(seq, fp) => getWorkerDecisionDetail(workerId, seq, fp)}
        record={detailRecord}
        onClose={() => setDetailRecord(null)}
      />
    </Spin>
  );
}
