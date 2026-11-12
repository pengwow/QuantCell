/**
 * wire 事件 schema 版本迁移（P2-10）
 *
 * 独立成文件的原因：websocketService.ts 模块顶层依赖 window（defaultConfig），
 * 无法在 vitest node 环境直接导入；迁移函数是纯逻辑，与浏览器 API 解耦。
 */

/**
 * 当前前端支持的 wire 事件 schema 最高版本（与后端 worker/events.py 对齐）
 */
export const KNOWN_EVENT_SCHEMA_VERSION = 1;

/**
 * 按 schema_version 迁移 wire 事件
 *
 * 语义与后端 worker/protocol.py 的信封校验对齐：
 * - 缺 schema_version 视为 v0，原样放行（向后兼容读旧版后端）
 * - 低于等于 KNOWN_EVENT_SCHEMA_VERSION → 透传
 * - 高于已知版本 → 返回 null，由调用方丢弃（当前前端无法理解未来版本）
 *
 * 当前 v1 无实际迁移步骤，函数为未来 v2+ 的字段改形预留演进点。
 */
export function migrate_event(payload: unknown): Record<string, unknown> | null {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const rec = payload as Record<string, unknown>;
  const version = typeof rec.schema_version === 'number' ? rec.schema_version : 0;
  if (version > KNOWN_EVENT_SCHEMA_VERSION) return null;
  return rec;
}
