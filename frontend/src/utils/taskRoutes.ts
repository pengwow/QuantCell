/**
 * 任务类型 → 前端详情页路径 注册中心
 *
 * 后端五类异步任务（source ∈ task_notices.TASK_TYPES）的终态通知点击后的跳转
 * 落点全部收敛在这里。设计约束（设计规格 §4.1/§7）：
 * - 收件箱 REST 列表不携带 task_id（InboxNotification 未扩列），只有 WS 实时
 *   推送的 metadata 里有 { task_type, task_id, status }。
 *   兜底链 = metadata.task_id 有则跳详情，无则跳列表页。
 * - 回测例外：失败详情页缺少产物视图，无论有无 id 都回列表页看失败原因。
 */

export interface TaskRouteCtx {
  /** 任务域内 uuid（WS metadata.task_id 可携带；REST 列表行恒为 null） */
  id: string | null;
  /** WS metadata 透传的扩展信息（backtest 的 status 等） */
  detail?: Record<string, unknown>;
}

type TaskRouteResolver = (ctx: TaskRouteCtx) => string;

/** key 与后端 task_notices.TASK_TYPES 五域对齐 */
const TASK_ROUTE_RESOLVERS: Record<string, TaskRouteResolver> = {
  backtest: ({ id, detail }) => {
    if (detail?.status === 'failed') return '/backtest';
    return id ? `/backtest/detail/${id}` : '/backtest';
  },
  rl_train: () => '/model-hub?tab=train',
  factor_job: () => '/factor-analysis',
  collector_task: () => '/data-management',
  research: ({ id }) => (id ? `/research/${id}` : '/research'),
};

/** source 是否任务类通知（点击跳转的适用范围） */
export const isTaskSource = (source: string): boolean => source in TASK_ROUTE_RESOLVERS;

/** 完整任务域列表（收件箱页任务过滤器选项顺序） */
export const TASK_SOURCES = Object.keys(TASK_ROUTE_RESOLVERS);

/**
 * 任务通知点击跳转路由；非任务类通知返回 null（行/浮层不跳转）。
 */
export function taskNotificationRoute(source: string, ctx: TaskRouteCtx): string | null {
  const resolver = TASK_ROUTE_RESOLVERS[source];
  return resolver ? resolver(ctx) : null;
}
