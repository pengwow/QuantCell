/**
 * Worker 决策 tab：cascade 策略在 paper/testnet 运行期的决策轻列表。
 * 数据源 GET /workers/{id}/decisions（录制文件 worker_{id}.jsonl，时间倒序）。
 * 详情 Drawer 复用回测侧组件，四区块内容口径完全一致。
 */
import { useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Space, Spin, Table, Tag, Tooltip, Typography } from 'antd';
import { getWorkerDecisionDetail, getWorkerDecisions } from '../../api/workerApi';
import type { CascadeDecisionRecord } from '../../types/backtest';
import DecisionDetailDrawer, { fmtDecisionTs, humanizeFallbackReason } from '../../pages/backtest/DecisionDetailDrawer';

const PAGE_SIZE = 200;
const ACTION_COLORS: Record<string, string> = { buy: 'green', sell: 'red', hold: 'default' };

interface Props {
  workerId: number;
  active: boolean; // tab 激活才请求，避免所有 tab 全量拉取
}

export default function WorkerDecisionsTab({ workerId, active }: Props) {
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
        {error && <Alert type="warning" showIcon message={`决策列表加载失败：${error}`} />}
        <Card
          title={
            <Space wrap>
              <span>决策记录</span>
              <Typography.Text type="secondary">共 {total} 条</Typography.Text>
              {rows.length > 0 && (
                <Tag color={fallbackCount > 0 ? 'orange' : 'green'}>
                  降级 {fallbackCount} / {rows.length} 条
                </Tag>
              )}
            </Space>
          }
          extra={<Typography.Text type="secondary" style={{ fontSize: 12 }}>最近 {rows.length} 条（含历史运行）</Typography.Text>}
        >
          {rows.length === 0 && !loading ? (
            <Empty description="该 Worker 未运行过 cascade 决策策略，或尚未产生决策（P2 之前的旧录制文件不展示）" />
          ) : (
            <Table
              size="small"
              rowKey={(r) => `${r._seq}:${r.fingerprint}`}
              dataSource={rows}
              pagination={{ pageSize: PAGE_SIZE, showSizeChanger: false }}
              columns={[
                {
                  title: '时间',
                  dataIndex: '_ts',
                  width: 180,
                  render: (ts: string) => (
                    <Tooltip title={ts || '-'}>
                      <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{fmtDecisionTs(ts)}</span>
                    </Tooltip>
                  ),
                },
                {
                  title: '动作',
                  dataIndex: 'action',
                  width: 80,
                  render: (a: string) => <Tag color={ACTION_COLORS[a] || 'default'}>{a}</Tag>,
                },
                {
                  title: '置信度',
                  dataIndex: 'confidence',
                  width: 100,
                  render: (v: number) => (typeof v === 'number' ? v.toFixed(4) : '-'),
                },
                { title: '决策者', dataIndex: '_decider', width: 130, render: (v: string) => v || '-' },
                {
                  title: '降级原因',
                  dataIndex: 'fallback_reason',
                  ellipsis: true,
                  render: (reason: string) =>
                    reason ? (
                      <Tooltip title={reason}>
                        <span>{humanizeFallbackReason(reason)}</span>
                      </Tooltip>
                    ) : (
                      <span style={{ color: '#8c8c8c' }}>—</span>
                    ),
                },
                {
                  title: '操作',
                  width: 80,
                  fixed: 'right',
                  render: (_: unknown, record: CascadeDecisionRecord) =>
                    record._seq == null ? (
                      <Tooltip title="旧录制无行号定位键">
                        <Button size="small" disabled>详情</Button>
                      </Tooltip>
                    ) : (
                      <Button size="small" onClick={() => setDetailRecord(record)}>详情</Button>
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
