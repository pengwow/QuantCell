/**
 * 挖掘过程事件时间线：实时态（WS 事件）与历史态（run detail.events）共用。
 * 固定高度可滚动，新事件自动滚到底部；warning 行橙色。
 */
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Empty, Tag } from 'antd';
import type { MiningEvent } from '@/api/factor';

const STAGE_COLOR: Record<string, string> = {
  data_load: 'default',
  generating: 'processing',
  evaluating: 'blue',
  dedup: 'purple',
  composite: 'cyan',
  completed: 'green',
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
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('factor_mining_event_empty') || '暂无过程事件'}
      />
    );
  }

  return (
    <div
      style={{
        height: 220,
        overflowY: 'auto',
        border: '1px solid var(--tw-color-border-secondary)',
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
            color: e.level === 'warning' ? 'var(--tw-color-warning)' : undefined,
          }}
        >
          <span
            style={{
              color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)',
              fontVariantNumeric: 'tabular-nums',
              whiteSpace: 'nowrap',
            }}
          >
            {fmtTs(e.ts)}
          </span>
          <Tag color={STAGE_COLOR[e.stage] ?? 'default'} style={{ marginInlineEnd: 0 }}>
            {t(`factor_mining_stage_${e.stage}`) || e.stage}
          </Tag>
          <span>{e.msg}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
};

export default MiningEventLog;
