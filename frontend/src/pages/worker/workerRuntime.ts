/**
 * 列表「运行时长」纯函数（demo 14h 22m 形制）。
 * running 从 started_at 算到当前；有 stopped_at 则算到 stopped_at（历史运行时长定值）；
 * 其余状态（paused / error / initializing 且无 stopped_at）没有可信终点 → 输出 '—'，
 * 不拿 updated_at 或当前时间冒充（暂停时长 ≠ 运行时长）。
 */
import dayjs from 'dayjs';
import type { Worker } from '../../types/worker';

type RuntimeInput = Pick<Worker, 'status' | 'started_at' | 'stopped_at'>;

export const formatWorkerRuntime = (worker: RuntimeInput, now: number = Date.now()): string => {
  if (!worker.started_at) return '—';
  const start = dayjs(worker.started_at).valueOf();
  const end = worker.stopped_at ? dayjs(worker.stopped_at).valueOf() : worker.status === 'running' ? now : null;
  if (end == null) return '—';
  const ms = end - start;
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `${h}h ${String(m).padStart(2, '0')}m`;
};