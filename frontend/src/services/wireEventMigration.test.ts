/**
 * P2-10：migrate_event 纯函数测试
 * 与后端 worker/events.py 的 EVENTS_SCHEMA_VERSION=1 语义对齐
 */
import { describe, expect, it } from 'vitest';

import { KNOWN_EVENT_SCHEMA_VERSION, migrate_event } from './wireEventMigration';

describe('migrate_event', () => {
  it('缺失 schema_version 视为 v0，原样放行（向后兼容读旧版后端）', () => {
    const legacy = { type: 'strategy_event', worker_id: 1 };
    expect(migrate_event(legacy)).toEqual(legacy);
  });

  it('v1 事件透传', () => {
    const v1 = { type: 'worker_event', schema_version: 1, data: { worker_id: 1 } };
    expect(migrate_event(v1)).toEqual(v1);
  });

  it('高于已知版本返回 null（调用方应丢弃）', () => {
    expect(migrate_event({ type: 'worker_event', schema_version: KNOWN_EVENT_SCHEMA_VERSION + 1 })).toBeNull();
  });

  it('schema_version 非数字类型按 v0 兼容放行', () => {
    // 与后端严格校验不同：前端对存量异常 payload 宽容处理，不因脏字段丢事件
    const dirty = { type: 'strategy_event', schema_version: '1' };
    expect(migrate_event(dirty)).toEqual(dirty);
  });

  it('非对象输入返回 null', () => {
    expect(migrate_event(null)).toBeNull();
    expect(migrate_event('oops')).toBeNull();
    expect(migrate_event([1, 2])).toBeNull();
  });
});
