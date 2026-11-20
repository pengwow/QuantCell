/**
 * Worker 状态 → §6.2 语义 chip
 *
 * Worker.tsx / WorkerDetail.tsx / WorkerOrderTab 共用，向色映射只留这一处。
 * label 由调用方用 t(WorkerStatusText[status]) 翻译后传入（i18n 不进工具层）。
 */
import type { WorkerStatus } from '../../types/worker';

/** 瞬态状态（进行中类）：chip 内带 pulse 圆点；终态不带 */
const TRANSIENT_STATUSES = new Set(['initializing', 'starting', 'stopping', 'restarting', 'reloading', 'recovering']);

/** 状态 chip 语义档（§6.2 tint 公式）：运行/进行=ok·info，暂停/恢复=warn，停止/就绪=quiet，错误/中断=down */
const STATUS_CHIP_CLS: Record<string, string> = {
  running: ' ok',
  starting: ' info',
  initializing: ' info',
  reloading: ' info',
  restarting: ' info',
  stopping: ' info',
  recovering: ' warn',
  paused: ' warn',
  stopped: ' quiet',
  initialized: ' quiet',
  error: ' down',
  interrupted: ' down',
};

export const workerStatusChip = (status: WorkerStatus | string, label: string) => (
  <span className={`qc-chip${STATUS_CHIP_CLS[status] ?? ' quiet'}`}>
    {(status === 'running' || TRANSIENT_STATUSES.has(status)) && <span className="qc-pdot" />}
    {label}
  </span>
);
