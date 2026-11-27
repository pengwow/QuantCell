/**
 * Worker 详情页 tab 常量（纯数据，无 React/antd 依赖）
 *
 * 从 WorkerDetail.tsx 拆出：一是 tab 收敛 8→6 后常量可被单测直接校验
 * （workerDetailTabs.test.ts），二是页面组件只留行为、不留数据定义。
 */

// Tab key 类型
export type TabKey = 'overview' | 'trades' | 'decisions' | 'risk' | 'params' | 'plan' | 'logs';

// 合法 tab key（plan：启动固化的价格计划 + 运行态触发进度）
export const VALID_TABS: TabKey[] = ['overview', 'trades', 'decisions', 'risk', 'params', 'plan', 'logs'];

// 旧 hash -> 新 hash 映射
// TODO(ux-hash-compat): 这是 URL hash 的 UX 兼容（旧分享链接），并非旧数据协议；
// 待旧版分享链接自然淘汰（预计 2026-12）后移除。
// 8→6 tab 收敛迁移：持仓并入总览（position/positions→overview）；
// 委托与成交分组合并为「交易」（orders/tradesGrouped→trades）。
export const LEGACY_HASH_MAP: Record<string, TabKey> = {
  performance: 'overview',
  stats: 'overview',
  trading_stats: 'overview',
  position: 'overview', // 单数兼容
  positions: 'overview',
  orders: 'trades',
  tradesGrouped: 'trades',
};
