/**
 * 研究模块共用 chip 渲染（design-spec §6.2 `.qc-chip`，列表卡片/表格与详情页头共用）。
 * 颜色只存语义槽位（ok/info/warn/down/quiet），文字一律走 i18n key 的调用方翻译。
 */
import type { TFunction } from 'i18next';
import type { ResearchSession, ResearchStatus } from '@/api/research';

/** 状态 → chip 语义槽位：运行中 info（脉冲点）、完成 ok、暂停 warn、失败 down、排队/取消 quiet */
const STATUS_VARIANT: Record<ResearchStatus, string> = {
  pending: 'quiet',
  running: 'info',
  paused: 'warn',
  completed: 'ok',
  failed: 'down',
  cancelled: 'quiet',
};

const STATUS_I18N: Record<ResearchStatus, string> = {
  pending: 'research_status_pending',
  running: 'research_status_running',
  paused: 'research_status_paused',
  completed: 'research_status_completed',
  failed: 'research_status_failed',
  cancelled: 'research_status_cancelled',
};

/** 状态 chip（pending 且有排队位次时文案带「第 N 位」） */
export const researchStatusChip = (
  row: Pick<ResearchSession, 'status' | 'queue_position'>,
  t: TFunction,
) => {
  const label = [t(STATUS_I18N[row.status] ?? row.status)];
  if (row.status === 'pending' && row.queue_position) {
    label.push(t('research_queue_position', { pos: row.queue_position }));
  }
  return (
    <span className={`qc-chip ${STATUS_VARIANT[row.status] ?? 'quiet'}`}>
      {row.status === 'running' && <span className="qc-pdot" />}
      {label.join(' · ')}
    </span>
  );
};

/** 场景 chip（旧数据无 scenario 时按 factor 兜底，与列表历史渲染口径一致） */
export const researchScenarioChip = (
  row: Pick<ResearchSession, 'scenario'>,
  t: TFunction,
) => {
  const scenario = row.scenario === 'strategy' || row.scenario === 'model' ? row.scenario : 'factor';
  return <span className="qc-chip info">{t(`research_scenario_${scenario}`)}</span>;
};

/** 模式 chip：quick 被 extend 后用主色 tint 区分「快速→深入」（PRD §12 #9） */
export const researchModeChip = (
  row: Pick<ResearchSession, 'mode' | 'extended_at'>,
  t: TFunction,
) => {
  const extended = row.mode === 'quick' && row.extended_at;
  return (
    <span className={`qc-chip ${extended ? 'pri' : 'quiet'}`}>
      {row.mode === 'quick'
        ? (extended ? t('research_mode_quick_extended') : t('research_mode_quick'))
        : t('research_mode_deep')}
    </span>
  );
};
