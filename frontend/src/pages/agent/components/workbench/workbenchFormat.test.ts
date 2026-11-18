import { describe, expect, it } from 'vitest';
import {
  AUDIT_STATUSES,
  formatAuditArgs,
  formatElapsed,
  isTrainTaskTerminal,
} from './workbenchFormat';

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
