import { describe, expect, it } from 'vitest';
import { CHECK_INTERVAL_MS, shouldCheck } from './useUpdater';

describe('shouldCheck', () => {
  const now = 1_700_000_000_000;

  it('无历史记录（首次运行）需要检查', () => {
    expect(shouldCheck(0, now)).toBe(true);
  });

  it('距上次检查不足 24h 跳过', () => {
    expect(shouldCheck(now - CHECK_INTERVAL_MS + 1, now)).toBe(false);
  });

  it('距上次检查达到 24h 需要检查', () => {
    expect(shouldCheck(now - CHECK_INTERVAL_MS, now)).toBe(true);
  });

  it('非法时间戳视为需要检查', () => {
    expect(shouldCheck(Number.NaN, now)).toBe(true);
  });
});
