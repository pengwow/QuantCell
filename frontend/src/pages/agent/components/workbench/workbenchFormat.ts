/**
 * 工作面板（模型 Tab 训练卡 / 审计 Tab）的纯展示函数：
 * 抽成无 React 依赖的模块，便于 vitest(node) 直接跑检查。
 */
import type { RLTrainTaskStatus } from '@/api/rlApi';
import type { AgentLoopJob, AgentRunRecord, ToolAuditRow } from '@/api/agentApi';

/** 终态：不会再有进度变化（停止轮询 / 停止 SSE） */
export const isTrainTaskTerminal = (status?: string | null): boolean =>
  status === 'done' || status === 'error' || status === 'cancelled';

/** 训练卡状态徽标 → §6.2 qc-chip 语义档位（原 antd Tag 色名全量退役） */
export const TRAIN_STATUS_LEVELS: Record<RLTrainTaskStatus, string> = {
  queued: 'quiet',
  running: 'info',
  done: 'ok',
  error: 'down',
  cancelled: 'warn',
};

/**
 * 用时文案：42s / 1m05s / 1h02m。
 * 只到分钟粒度（训练是分钟级任务，秒级抖动没有信息量）。
 */
export const formatElapsed = (ms?: number | null): string => {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '-';
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m${String(s).padStart(2, '0')}s`;
  return `${s}s`;
};

/** audit 的 result_status 实际值域（后端 agent/tools/registry.py 落库口径） */
export const AUDIT_STATUSES = [
  'success',
  'error',
  'blocked_approval',
  'blocked_scope',
  'invalid_params',
] as const;

/** audit 状态徽标 → §6.2 qc-chip 语义档位（原 antd Tag 色名全量退役） */
export const AUDIT_STATUS_LEVELS: Record<string, string> = {
  success: 'ok',
  error: 'down',
  blocked_approval: 'warn',
  blocked_scope: 'warn',
  invalid_params: 'down',
};

/**
 * args_redacted 是后端落库的 JSON 文本（已脱敏），格式化后给 <pre> 展示；
 * 非 JSON / 空值原样返回（截断或历史脏数据不该让行展开崩掉）。
 */
export const formatAuditArgs = (raw?: string | null): string => {
  if (raw == null || raw === '') return '-';
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
};

// ==================== 自迭代 Tab（A–D 卡）的纯展示函数 ====================

/** Dream / job 运行态：成功改写、无新条目（no-op）、失败、从未运行 */
export type LoopRunState = 'updated' | 'noop' | 'failed' | 'never';

/** job 状态点：成功 / 失败 / 已挂载但未运行 / 未挂载（总闸未开） */
export type LoopJobState = 'ok' | 'failed' | 'idle' | 'off';

/**
 * detail 是后端自由结构：优先取 updated 布尔；
 * 字符数兼容 chars / updated_chars 两档（字段未在契约中定死，缺省不显示）。
 */
const runDetailOf = (run: AgentRunRecord | null): Record<string, unknown> | null =>
  run && typeof run.detail === 'object' && run.detail !== null
    ? (run.detail as Record<string, unknown>)
    : null;

/** 本次运行是否改写 MEMORY.md（ok=true 且 detail.updated 为真） */
export const memoryRunState = (run: AgentRunRecord | null | undefined): LoopRunState => {
  if (!run) return 'never';
  if (!run.ok) return 'failed';
  return runDetailOf(run)?.updated === true ? 'updated' : 'noop';
};

/** 改写字符数（后端未上报则为 null，UI 不编数字） */
export const memoryRunChars = (run: AgentRunRecord | null | undefined): number | null => {
  const detail = runDetailOf(run ?? null);
  const raw = detail?.chars ?? detail?.updated_chars;
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
};

/** detail 的展示文本：字符串直出、对象格式化 JSON、其余空串（调用方自行兜底） */
export const formatRunDetail = (detail: unknown): string => {
  if (detail == null) return '';
  if (typeof detail === 'string') return detail;
  try {
    return JSON.stringify(detail, null, 2);
  } catch {
    return String(detail);
  }
};

/**
 * Dream cursor 推进：cursor 是「已消费条数」，entries 是当前总数。
 * 后端可能出现 cursor > entries（history 被裁剪/重建），一律夹到 [0, total]。
 */
export const dreamProgress = (
  cursor: number,
  entries: number,
): { processed: number; total: number; pending: number; pct: number } => {
  const total = Number.isFinite(entries) && entries > 0 ? Math.floor(entries) : 0;
  const processed = Math.min(Math.max(Number.isFinite(cursor) ? Math.floor(cursor) : 0, 0), total);
  return {
    processed,
    total,
    pending: total - processed,
    pct: total === 0 ? 0 : Math.round((processed / total) * 100),
  };
};

/** job 状态：未挂载优先（总闸未开），其次看 last_run */
export const loopJobState = (
  job: Pick<AgentLoopJob, 'mounted' | 'last_run'> | null | undefined,
): LoopJobState => {
  if (!job) return 'off';
  if (!job.mounted) return 'off';
  if (!job.last_run) return 'idle';
  return job.last_run.ok ? 'ok' : 'failed';
};

/** 重训双闸：任一关闭 → 不会自动换模型，顶部警示条必须出现 */
export const retrainGates = (
  gates: { auto_retrain?: boolean; auto_promote?: boolean } | null | undefined,
): { autoRetrain: boolean; autoPromote: boolean; anyOff: boolean } => {
  const autoRetrain = gates?.auto_retrain === true;
  const autoPromote = gates?.auto_promote === true;
  return { autoRetrain, autoPromote, anyOff: !autoRetrain || !autoPromote };
};

/** 按本地自然日聚合审计行（date 为 YYYY-MM-DD，标签由调用方本地化） */
export const auditDayBuckets = (
  rows: ToolAuditRow[],
  days: number,
  now: Date = new Date(),
): { date: string; total: number; failed: number }[] => {
  const span = Math.max(1, Math.floor(days));
  const keys: string[] = [];
  for (let i = span - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    keys.push(`${d.getFullYear()}-${m}-${day}`);
  }
  const buckets = new Map(keys.map((k) => [k, { date: k, total: 0, failed: 0 }]));
  for (const row of rows) {
    const d = new Date(row.created_at);
    if (Number.isNaN(d.getTime())) continue;
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const bucket = buckets.get(`${d.getFullYear()}-${m}-${day}`);
    if (!bucket) continue;
    bucket.total += 1;
    // 失败口径：仅 error；blocked_*/invalid_params 是策略拦截，不算执行失败
    if (row.result_status === 'error') bucket.failed += 1;
  }
  return [...buckets.values()];
};
