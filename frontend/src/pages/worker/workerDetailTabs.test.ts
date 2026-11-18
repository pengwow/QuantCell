/**
 * workerDetailTabs 纯数据模块守护测试：
 * tab 收敛 8→6 后，旧 hash 映射必须依旧覆盖旧分享链接，且映射目标全部合法。
 */
import { describe, it, expect } from 'vitest';
import { LEGACY_HASH_MAP, VALID_TABS } from './workerDetailTabs';

describe('workerDetailTabs', () => {
  it('LEGACY_HASH_MAP 的所有映射目标都是合法 tab', () => {
    for (const target of Object.values(LEGACY_HASH_MAP)) {
      expect(VALID_TABS).toContain(target);
    }
  });

  it('覆盖全部下线 tab 的旧 hash 入口', () => {
    // 持仓并入总览
    expect(LEGACY_HASH_MAP['positions']).toBe('overview');
    expect(LEGACY_HASH_MAP['position']).toBe('overview');
    // 委托 + 成交分组 合并为「交易」
    expect(LEGACY_HASH_MAP['orders']).toBe('trades');
    expect(LEGACY_HASH_MAP['tradesGrouped']).toBe('trades');
    // 旧 8 tab 之前的性能页兼容保持不变
    expect(LEGACY_HASH_MAP['performance']).toBe('overview');
    expect(LEGACY_HASH_MAP['stats']).toBe('overview');
    expect(LEGACY_HASH_MAP['trading_stats']).toBe('overview');
  });

  it('合法 tab 不应出现在旧 hash 映射表中（避免当前路由被二次降级）', () => {
    for (const tab of VALID_TABS) {
      expect(LEGACY_HASH_MAP[tab]).toBeUndefined();
    }
  });
});
