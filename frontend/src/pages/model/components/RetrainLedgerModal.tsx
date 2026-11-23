/**
 * 重训台账（只读 Modal）：GET /rl/lifecycle/state 的三段展示——
 * 重训候选（candidates）/ 待审晋升（pending_promotions）/ 晋升记录（promotions）。
 * 列名取端点真实字段（RetrainCandidate.to_dict / lifecycle promotions 条目），
 * 不照抄原型假列。审批操作走 POST /models/{id}/promote 人审通路，不在本 Modal 范围。
 */
import { useEffect, useState } from 'react';
import { Alert, Button, Modal, Spin, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import dayjs from 'dayjs';
import i18n from '@/i18n/config';
import { rlApi } from '@/api/rlApi';
import type { RlLifecycleState, RlPromotionRecord, RlRetrainCandidate } from '@/api/rlApi';

/** 双闸 → 一句话：双开 / 双关走短文案，混合态逐闸点名（调用方保证入参已从端点取到真值） */
export const retrainGateText = (retrain?: boolean, promote?: boolean): string => {
  if (retrain && promote) return i18n.t('rl_ledger.gate_both_on');
  if (!retrain && !promote) return i18n.t('rl_ledger.gate_both_off');
  const gate = (v?: boolean) => i18n.t(v ? 'rl_ledger.gate_on' : 'rl_ledger.gate_off');
  return i18n.t('rl_ledger.gate_mixed', { retrain: gate(retrain), promote: gate(promote) });
};

// 晋升状态 chip（qc-chip 档位与 UnifiedModelTable 同口径）：待审琥珀 / 成功绿 / 失败红
const PROMOTION_CHIP: Record<string, { cls: string; labelKey: string }> = {
  pending: { cls: 'warn', labelKey: 'rl_ledger.status_pending' },
  auto_promoted: { cls: 'ok', labelKey: 'rl_ledger.status_auto_promoted' },
  auto_promote_failed: { cls: 'down', labelKey: 'rl_ledger.status_auto_promote_failed' },
};

const statusChip = (t: TFunction, status?: string) => {
  const hit = status ? PROMOTION_CHIP[status] : undefined;
  if (!hit) return <span className="qc-chip quiet">{status || '-'}</span>;
  return <span className={`qc-chip ${hit.cls}`}>{t(hit.labelKey)}</span>;
};

const RETRAIN_REASON: Record<string, string> = {
  oos_decay: 'rl_ledger.reason_oos_decay',
  data_stale: 'rl_ledger.reason_data_stale',
};

const fmtTime = (v?: string) => {
  const raw = (v || '').trim();
  if (!raw) return '-';
  const d = dayjs(raw);
  return d.isValid() ? d.format('MM-DD HH:mm') : raw;
};

// 证据里只有数值列值得展示（age_days / train_sharpe / oos_sharpe），缺失/非数值一律 '-'
const fmtNum = (v: unknown, digits = 2) => {
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN;
  return Number.isFinite(n) ? n.toFixed(digits) : '-';
};

const evidenceSummary = (e: Record<string, unknown> | undefined, t: TFunction) => {
  if (!e || typeof e !== 'object') return '-';
  const seg: string[] = [];
  const oos = fmtNum(e.oos_sharpe);
  const train = fmtNum(e.train_sharpe);
  const age = fmtNum(e.age_days, 0);
  if (oos !== '-') seg.push(`OOS ${oos}`);
  if (train !== '-') seg.push(t('rl_ledger.evidence_train', { v: train }));
  if (age !== '-') seg.push(t('rl_ledger.evidence_age_days', { v: age }));
  return seg.length ? seg.join(' · ') : '-';
};

const mono = (v: unknown) => <span className="qc-mono">{v ? String(v) : '-'}</span>;

const candidateColumns = (t: TFunction): ColumnsType<RlRetrainCandidate> => [
  { title: t('rl_ledger.col_family'), dataIndex: 'family', ellipsis: true, render: mono },
  { title: t('rl_ledger.col_model'), dataIndex: 'model_id', ellipsis: true, render: mono },
  {
    title: t('rl_ledger.col_reason'),
    dataIndex: 'reason',
    width: 110,
    render: (v: string) => (RETRAIN_REASON[v] ? t(RETRAIN_REASON[v]) : v || '-'),
  },
  {
    title: t('rl_ledger.col_evidence'),
    key: 'evidence',
    ellipsis: true,
    render: (_, r) => <span className="qc-mono">{evidenceSummary(r.evidence, t)}</span>,
  },
];

const promotionColumns = (t: TFunction): ColumnsType<RlPromotionRecord> => [
  {
    title: t('rl_ledger.col_time'),
    dataIndex: 'created_at',
    width: 110,
    render: (v: string) => <span className="qc-mono">{fmtTime(v)}</span>,
  },
  { title: t('rl_ledger.col_family'), dataIndex: 'family', ellipsis: true, render: mono },
  { title: 'champion', dataIndex: 'champion_id', ellipsis: true, render: mono },
  { title: 'challenger', dataIndex: 'challenger_id', ellipsis: true, render: mono },
  { title: t('rl_ledger.col_status'), dataIndex: 'status', width: 110, render: (v: string) => statusChip(t, v) },
];

const tableProps = (t: TFunction) =>
  ({ size: 'small', pagination: false, locale: { emptyText: t('rl_ledger.empty') } }) as const;

// 三段共用的小节头：标题 + 行数（mono 弱化）
const SectionHead = ({ title, count }: { title: string; count: number }) => (
  <div className="mb-1 mt-3 flex items-center gap-2 first:mt-0">
    <span className="text-xs font-semibold">{title}</span>
    <span className="qc-mono text-[11px] text-[color:var(--qc-text-tertiary)]">{count}</span>
  </div>
);

interface RetrainLedgerModalProps {
  open: boolean;
  onClose: () => void;
}

export default function RetrainLedgerModal({ open, onClose }: RetrainLedgerModalProps) {
  const { t } = useTranslation();
  const [state, setState] = useState<RlLifecycleState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 每次打开都重拉（只读快照，不做常驻轮询）；失败不写死兜底数据，直接给错误态
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setState(null);
    setError(null);
    setLoading(true);
    rlApi
      .lifecycleState()
      .then((d) => {
        if (alive) setState(d);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open]);

  const candidates = state?.candidates ?? [];
  const pending = state?.pending_promotions ?? [];
  const promotions = state?.promotions ?? [];
  // 与副标同款守卫：双闸字段必须都是布尔才展示，缺字段不落假缺省
  const gatesInfo =
    typeof state?.auto_retrain_enabled === 'boolean' && typeof state?.auto_promote_enabled === 'boolean'
      ? {
          text: retrainGateText(state.auto_retrain_enabled, state.auto_promote_enabled),
          bothOn: state.auto_retrain_enabled && state.auto_promote_enabled,
        }
      : null;

  return (
    <Modal
      className="qc-modal"
      open={open}
      onCancel={onClose}
      width={920}
      title={
        <span className="flex items-center gap-2">
          {t('rl_ledger.title')}
          {gatesInfo && (
            <span className={`qc-chip ${gatesInfo.bothOn ? 'ok' : 'warn'}`}>{gatesInfo.text}</span>
          )}
        </span>
      }
      footer={<Button onClick={onClose}>{t('rl_ledger.close')}</Button>}
    >
      {error ? (
        <Alert type="error" showIcon title={t('rl_ledger.load_failed')} description={error} />
      ) : loading || !state ? (
        <div className="flex items-center justify-center py-10">
          <Spin />
        </div>
      ) : (
        <>
          <SectionHead title={t('rl_ledger.section_candidates')} count={candidates.length} />
          {/* candidates 的 family 必填且当日唯一（选目按族去重），可作稳定 key */}
          <Table {...tableProps(t)} columns={candidateColumns(t)} dataSource={candidates} rowKey="family" />

          <SectionHead title={t('rl_ledger.section_pending')} count={pending.length} />
          {/* ponytail: 台账条目无稳定主键（challenger_id 可缺失/重复），行序即展现序，用数组下标当 key */}
          <Table {...tableProps(t)} columns={promotionColumns(t)} dataSource={pending} rowKey={(_, i) => String(i)} />

          <SectionHead title={t('rl_ledger.section_promotions')} count={promotions.length} />
          <Table {...tableProps(t)} columns={promotionColumns(t)} dataSource={promotions} rowKey={(_, i) => String(i)} />
        </>
      )}
    </Modal>
  );
}
