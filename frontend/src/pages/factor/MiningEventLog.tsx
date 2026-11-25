/**
 * 挖掘过程事件时间线：实时态（WS 事件）与历史态（run detail.events）共用。
 * 固定高度可滚动，新事件自动滚到底部；warning 行橙色。
 * （旧 LLM 挖掘退役后暂无页面引用，保留共用原语供研究事件流之外的复用）
 */
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import type { MiningEvent } from '@/api/factor';
import { QcEmpty } from '@/components/ui/DataTable';

/** 阶段 → §6.2 chip 语义槽位（生成/评估=进行中 info，完成=ok，其余 quiet；
 *  全站只允许语义色，不再用 antd 预设彩色 Tag 调色板） */
const STAGE_VARIANT: Record<string, string> = {
  data_load: 'quiet',
  generating: 'info',
  evaluating: 'info',
  dedup: 'quiet',
  composite: 'quiet',
  completed: 'ok',
};

const fmtTs = (iso: string) => {
  // 后端 ISO8601（含 T），只取 HH:mm:ss
  const i = iso.indexOf('T');
  return i >= 0 ? iso.slice(i + 1, i + 9) : iso.slice(11, 19);
};

const MiningEventLog: React.FC<{ events: MiningEvent[] }> = ({ events }) => {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [events.length]);

  if (events.length === 0) {
    return <QcEmpty title={t('factor_mining_event_empty') || '暂无过程事件'} />;
  }

  return (
    <div
      style={{
        height: 220,
        overflowY: 'auto',
        border: '1px solid var(--qc-border)',
        borderRadius: 6,
        padding: 8,
      }}
    >
      {events.map((e) => (
        <div
          key={e.idx}
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'baseline',
            padding: '2px 0',
            color: e.level === 'warning' ? 'var(--qc-warning)' : undefined,
          }}
        >
          <span
            style={{
              color: 'var(--qc-text-tertiary)',
              fontVariantNumeric: 'tabular-nums',
              whiteSpace: 'nowrap',
            }}
          >
            {fmtTs(e.ts)}
          </span>
          <span className={`qc-chip ${STAGE_VARIANT[e.stage] ?? 'quiet'}`}>
            {t(`factor_mining_stage_${e.stage}`) || e.stage}
          </span>
          <span>{e.msg}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
};

export default MiningEventLog;
