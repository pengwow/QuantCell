/**
 * 最近对账卡片
 *
 * 展示 resume / 运行期周期对账的最近摘要（GET /workers/{id}/reconciliation/summary）。
 * 正常条目收敛为一行状态；异常条目展开非零 break 计数，便于一眼定位账实差异。
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { Button, Card, Empty, Skeleton, Space, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getReconcileSummary } from '../../api/workerApi';
import type { ReconcileSummaryItem } from '../../types/worker';

// 各类 break 的展示名映射（P1-02 三资 + P1-03 专项）；未识别的 key（后端演进新增）直接展示原始 key
const BREAK_LABEL_KEYS: Record<string, string> = {
  position_breaks: 'reconcile_break_position',
  missing_fills: 'reconcile_break_missing_fills',
  extra_fills: 'reconcile_break_extra_fills',
  ghost_orders: 'reconcile_break_ghost_orders',
  orphan_local_orders: 'reconcile_break_orphan_orders',
  open_orders_unverified: 'reconcile_break_unverified',
  cash_break: 'reconcile_break_cash',
  // P1-03 资金费/平仓专项
  venue_absent: 'reconcile_break_venue_absent',
  closed_without_rt: 'reconcile_break_closed_without_rt',
  rt_unfilled_pnl: 'reconcile_break_rt_unfilled_pnl',
};

const WorkerReconcileCard: React.FC<{ workerId: number; active?: boolean }> = ({ workerId, active = true }) => {
  const { t } = useTranslation();
  const [items, setItems] = useState<ReconcileSummaryItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await getReconcileSummary(workerId, 5));
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [workerId]);

  useEffect(() => {
    if (active) void refresh();
  }, [active, refresh]);

  const renderBreaks = (item: ReconcileSummaryItem) => {
    // raw（脏 JSON 降级）或无法解析的条目：直接展示原文片段
    const nonzero = Object.entries(item.counts ?? {}).filter(([, n]) => n > 0);
    if (item.raw) {
      return <Typography.Text type="secondary" ellipsis>{item.raw}</Typography.Text>;
    }
    if (nonzero.length === 0) return null;
    return (
      <Space wrap size={4}>
        {nonzero.map(([key, n]) => (
          <Tag key={key} color="error">
            {t(BREAK_LABEL_KEYS[key] ?? key)} × {n}
          </Tag>
        ))}
      </Space>
    );
  };

  return (
    <Card
      title={t('worker_recent_reconcile')}
      extra={
        <Button type="text" size="small" icon={<ReloadOutlined />} onClick={() => void refresh()} />
      }
      style={{ marginTop: 16 }}
    >
      {loading && items.length === 0 ? (
        <Skeleton active paragraph={{ rows: 2 }} />
      ) : items.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('reconcile_no_records')} />
      ) : (
        <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
          {items.map((item, idx) => {
            const abnormal = item.ok === false || item.level === 'WARNING';
            return (
              <Space key={idx} orientation="vertical" size={2} style={{ display: 'flex' }}>
                <Space size={8} wrap>
                  <span style={{ color: 'var(--ant-color-text-tertiary)', fontSize: 12 }}>
                    {item.timestamp ? dayjs(item.timestamp).format('MM-DD HH:mm') : '--'}
                  </span>
                  <Tag color={abnormal ? 'error' : 'success'}>
                    {abnormal ? t('reconcile_status_abnormal') : t('reconcile_status_ok')}
                  </Tag>
                </Space>
                {renderBreaks(item)}
              </Space>
            );
          })}
        </Space>
      )}
    </Card>
  );
};

export default WorkerReconcileCard;
