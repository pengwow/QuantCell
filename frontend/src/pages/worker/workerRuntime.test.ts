import { describe, it, expect } from 'vitest';
import { formatWorkerRuntime } from './workerRuntime';

const NOW = Date.parse('2026-11-23T10:00:00.000Z');

describe('formatWorkerRuntime', () => {
  it('running 从 started_at 算到 now', () => {
    expect(formatWorkerRuntime({ status: 'running', started_at: '2026-11-22T19:38:00.000Z' }, NOW)).toBe('14h 22m');
  });

  it('有 stopped_at 用定值，不随 now 变化', () => {
    const w = { status: 'stopped' as const, started_at: '2026-11-20T00:00:00.000Z', stopped_at: '2026-11-20T05:12:00.000Z' };
    expect(formatWorkerRuntime(w, NOW)).toBe('5h 12m');
    expect(formatWorkerRuntime(w, NOW + 86_400_000)).toBe('5h 12m');
  });

  it('paused / error 无 stopped_at 时省略，不冒充运行时长', () => {
    expect(formatWorkerRuntime({ status: 'paused', started_at: '2026-11-20T00:00:00.000Z' }, NOW)).toBe('—');
    expect(formatWorkerRuntime({ status: 'error', started_at: '2026-11-20T00:00:00.000Z' }, NOW)).toBe('—');
  });

  it('无 started_at / 起点晚于终点 → —', () => {
    expect(formatWorkerRuntime({ status: 'running' }, NOW)).toBe('—');
    expect(formatWorkerRuntime({ status: 'running', started_at: '2026-11-24T00:00:00.000Z' }, NOW)).toBe('—');
  });
});