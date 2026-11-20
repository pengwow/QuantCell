import { describe, expect, it } from 'vitest';
import {
  AUDIT_STATUSES,
  auditDayBuckets,
  dreamProgress,
  formatAuditArgs,
  formatElapsed,
  isTrainTaskTerminal,
  loopJobState,
  memoryRunChars,
  memoryRunState,
  retrainGates,
} from './workbenchFormat';
import type { ToolAuditRow } from '@/api/agentApi';

describe('isTrainTaskTerminal', () => {
  it('只有 done/error/cancelled 是终态', () => {
    expect(isTrainTaskTerminal('done')).toBe(true);
    expect(isTrainTaskTerminal('error')).toBe(true);
    expect(isTrainTaskTerminal('cancelled')).toBe(true);
    expect(isTrainTaskTerminal('queued')).toBe(false);
    expect(isTrainTaskTerminal('running')).toBe(false);
    expect(isTrainTaskTerminal(null)).toBe(false);
    expect(isTrainTaskTerminal(undefined)).toBe(false);
  });
});

describe('formatElapsed', () => {
  it('按秒/分/时三档取最小可读单位', () => {
    expect(formatElapsed(0)).toBe('0s');
    expect(formatElapsed(42_000)).toBe('42s');
    expect(formatElapsed(65_000)).toBe('1m05s');
    expect(formatElapsed(3_723_000)).toBe('1h02m');
  });

  it('缺值/负值显示占位符', () => {
    expect(formatElapsed(null)).toBe('-');
    expect(formatElapsed(undefined)).toBe('-');
    expect(formatElapsed(-1)).toBe('-');
    expect(formatElapsed(Number.NaN)).toBe('-');
  });
});

describe('formatAuditArgs', () => {
  it('JSON 文本格式化缩进', () => {
    expect(formatAuditArgs('{"a":1,"b":[2]}')).toBe('{\n  "a": 1,\n  "b": [\n    2\n  ]\n}');
  });

  it('非 JSON 与空值不抛错', () => {
    expect(formatAuditArgs('not-json')).toBe('not-json');
    expect(formatAuditArgs(null)).toBe('-');
    expect(formatAuditArgs('')).toBe('-');
  });
});

describe('AUDIT_STATUSES', () => {
  it('与后端 registry 落库的 5 种 result_status 对齐', () => {
    expect([...AUDIT_STATUSES]).toEqual([
      'success',
      'error',
      'blocked_approval',
      'blocked_scope',
      'invalid_params',
    ]);
  });
});

describe('memoryRunState / memoryRunChars', () => {
  it('区分 updated / no-op / 失败 / 从未运行', () => {
    expect(memoryRunState(null)).toBe('never');
    expect(memoryRunState({ ts_iso: 't', ok: false })).toBe('failed');
    expect(memoryRunState({ ts_iso: 't', ok: true, detail: { updated: true } })).toBe('updated');
    expect(memoryRunState({ ts_iso: 't', ok: true, detail: { updated: false } })).toBe('noop');
    // detail 缺失时按 no-op（ok=true 但没改写的唯一合理解释）
    expect(memoryRunState({ ts_iso: 't', ok: true })).toBe('noop');
  });

  it('字符数只认后端上报的数字，不编造', () => {
    expect(memoryRunChars({ ts_iso: 't', ok: true, detail: { updated: true, chars: 418 } })).toBe(418);
    expect(memoryRunChars({ ts_iso: 't', ok: true, detail: 'updated' })).toBeNull();
    expect(memoryRunChars(null)).toBeNull();
  });
});

describe('dreamProgress', () => {
  it('cursor 夹到 [0, entries] 后给百分比', () => {
    expect(dreamProgress(5, 5)).toEqual({ processed: 5, total: 5, pending: 0, pct: 100 });
    expect(dreamProgress(121, 128)).toEqual({ processed: 121, total: 128, pending: 7, pct: 95 });
    expect(dreamProgress(999, 10)).toEqual({ processed: 10, total: 10, pending: 0, pct: 100 });
    expect(dreamProgress(3, 0)).toEqual({ processed: 0, total: 0, pending: 0, pct: 0 });
  });
});

describe('loopJobState', () => {
  it('未挂载 > 未运行 > 成功/失败', () => {
    expect(loopJobState(null)).toBe('off');
    expect(loopJobState({ mounted: false, last_run: { ts_iso: 't', ok: true } })).toBe('off');
    expect(loopJobState({ mounted: true, last_run: null })).toBe('idle');
    expect(loopJobState({ mounted: true, last_run: { ts_iso: 't', ok: true } })).toBe('ok');
    expect(loopJobState({ mounted: true, last_run: { ts_iso: 't', ok: false } })).toBe('failed');
  });
});

describe('retrainGates', () => {
  it('任一闸关闭即 anyOff（必须出警示条）', () => {
    expect(retrainGates({ auto_retrain: true, auto_promote: true }).anyOff).toBe(false);
    expect(retrainGates({ auto_retrain: false, auto_promote: true }).anyOff).toBe(true);
    expect(retrainGates({ auto_retrain: true, auto_promote: false }).anyOff).toBe(true);
    expect(retrainGates(undefined)).toEqual({ autoRetrain: false, autoPromote: false, anyOff: true });
  });
});

describe('auditDayBuckets', () => {
  it('按本地自然日聚合，窗口外的行不计入', () => {
    const now = new Date(2026, 10, 18, 12, 0, 0);
    const row = (d: Date, status = 'success'): ToolAuditRow => ({
      id: 1,
      tool: 'get_kline',
      result_status: status,
      created_at: d.toISOString(),
    });
    const buckets = auditDayBuckets(
      [
        row(new Date(2026, 10, 18, 9, 0, 0)),
        row(new Date(2026, 10, 18, 10, 0, 0), 'error'),
        row(new Date(2026, 10, 11, 9, 0, 0)),
      ],
      7,
      now,
    );
    expect(buckets).toHaveLength(7);
    // 窗口是含今天在内的 7 天（11-12 .. 11-18），11-11 那行被丢弃
    expect(buckets[0]).toEqual({ date: '2026-11-12', total: 0, failed: 0 });
    expect(buckets[6]).toEqual({ date: '2026-11-18', total: 2, failed: 1 });
    expect(buckets.reduce((sum, b) => sum + b.total, 0)).toBe(2);
  });
});
