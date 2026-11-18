/**
 * 工作面板（模型 Tab 训练卡 / 审计 Tab）的纯展示函数：
 * 抽成无 React 依赖的模块，便于 vitest(node) 直接跑检查。
 */
import type { RLTrainTaskStatus } from '@/api/rlApi';

/** 终态：不会再有进度变化（停止轮询 / 停止 SSE） */
export const isTrainTaskTerminal = (status?: string | null): boolean =>
  status === 'done' || status === 'error' || status === 'cancelled';

/** 训练卡状态徽标色（antd Tag） */
export const TRAIN_STATUS_COLORS: Record<RLTrainTaskStatus, string> = {
  queued: 'default',
  running: 'processing',
  done: 'green',
  error: 'red',
  cancelled: 'orange',
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

export const AUDIT_STATUS_COLORS: Record<string, string> = {
  success: 'green',
  error: 'red',
  blocked_approval: 'orange',
  blocked_scope: 'gold',
  invalid_params: 'volcano',
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
