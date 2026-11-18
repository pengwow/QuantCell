/**
 * 右栏 ① 决策流：GET /workers/{id}/decisions（录制文件 worker_{id}.jsonl，时间倒序）。
 * 紧凑行样式对齐 agent_workbench_demo（时间 + 动作徽标 + 置信条 + 决策者），
 * 数据走 workbenchStore 缓存（useWorkbenchData 5s 轮询），详情复用回测侧 DecisionDetailDrawer。
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button, Empty, Spin, Tag, Tooltip } from 'antd';
import { getWorkerDecisionDetail } from '@/api/workerApi';
import type { CascadeDecisionRecord } from '@/types/backtest';
import DecisionDetailDrawer, { fmtDecisionTs } from '@/pages/backtest/DecisionDetailDrawer';
import { useWorkbenchStore } from '../../store/workbenchStore';

const ACTION_COLORS: Record<string, string> = { buy: 'green', sell: 'red', hold: 'default' };
const VISIBLE_ROWS = 50;

const timeOf = (ts?: string) => (ts ? (fmtDecisionTs(ts) || '').slice(11, 19) || fmtDecisionTs(ts) : '--:--:--');

export default function DecisionsTab() {
  const { t } = useTranslation();
  const workerId = useWorkbenchStore((s) => s.workerId);
  const entry = useWorkbenchStore((s) => s.decisions);
  const [detail, setDetail] = useState<CascadeDecisionRecord | null>(null);

  const active = !!entry && entry.workerId === workerId;
  const rows = useMemo(() => (active ? entry.data.decisions.slice(0, VISIBLE_ROWS) : []), [active, entry]);
  const total = active ? entry.data.total : 0;

  if (!workerId) {
    return <Empty description={t('wb_select_worker')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  if (!active) {
    return (
      <div className="wb-center-spin">
        <Spin size="small" />
      </div>
    );
  }

  return (
    <div className="wb-decisions">
      <div className="wb-list-meta">
        {t('total_items', { total })}
      </div>
      {rows.length === 0 ? (
        <Empty description={t('wb_no_decisions')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="wb-dec-list">
          {rows.map((r) => (
            <button
              type="button"
              key={`${r._seq}:${r.fingerprint}`}
              className="wb-dec-row"
              onClick={() => setDetail(r)}
            >
              <span className="wb-dec-time">{timeOf(r._ts)}</span>
              <Tag color={ACTION_COLORS[r.action] || 'default'} className="wb-dec-action">
                {(r.action || '-').toUpperCase()}
              </Tag>
              <span className="wb-dec-conf">
                <span className="wb-dec-conf-label">{t('backtest_confidence')} {typeof r.confidence === 'number' ? r.confidence.toFixed(2) : '-'}</span>
                <span className="wb-conf-bar">
                  <i
                    style={{ width: `${Math.min(100, Math.max(0, (r.confidence ?? 0) * 100))}%` }}
                    className={r.action === 'sell' ? 'down' : r.action === 'buy' ? 'up' : ''}
                  />
                </span>
              </span>
              <Tooltip title={r.fallback_reason ? t('backtest_fallback_reason') : r._decider || r.source}>
                <span className="wb-dec-decider">{r._decider || r.source}</span>
              </Tooltip>
            </button>
          ))}
        </div>
      )}
      {detail && workerId && (
        <DecisionDetailDrawer
          fetchDetail={(seq, fp) => getWorkerDecisionDetail(workerId, seq, fp)}
          record={detail}
          onClose={() => setDetail(null)}
        />
      )}
      {rows.length > 0 && (
        <div className="wb-list-footer">
          <Button type="link" size="small" disabled>
            {t('wb_recent_window', { count: rows.length })}
          </Button>
        </div>
      )}
    </div>
  );
}
