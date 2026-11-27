/**
 * 价格计划（Price Plan）契约类型 —— 与 backend/strategy/price_plan.py 的
 * PricePlan/PricePlanLevel/PricePlanSummary 逐字段对齐（spec §3.1）。
 */

// level 语义：buy=建/加仓（正 target）、sell=减仓（负 target）、tp=篮子止盈、mid=网格中枢
export type PlanAction = 'buy' | 'sell' | 'tp' | 'mid';

export interface PricePlanLevel {
  index: number;
  price: number;
  action: PlanAction;
  target_position: number;
  label: string;
  note?: string | null;
}

export interface PricePlanSummary {
  price_min: number;
  price_max: number;
  entry_price: number;
  extra: Record<string, number | string | null>;
}

export interface PricePlan {
  levels: PricePlanLevel[];
  summary: PricePlanSummary;
  warnings: string[];
}

// POST /strategies/preview 响应：plan + 解析后的参数
export interface PricePlanPreviewResponse extends PricePlan {
  params_resolved: Record<string, unknown>;
}

// 列表展开 chip 数据（worker list plan_summary）
export interface PlanNextTrigger {
  price: number;
  label?: string | null;
  distance_pct: number;
}

export interface WorkerPlanSummary {
  layer_total: number;
  triggered_count: number;
  triggered_indexes?: number[];
  next_trigger: PlanNextTrigger | null;
}

// 详情页 chips：worker 已固化的标的及其固化状态（按存储顺序）
export interface PlanSymbolState {
  symbol: string;
  state: 'fixed' | 'pending';
}

// GET /workers/{id}/plan 响应：pending 或 fixed+运行态
export interface WorkerPlanResponse {
  state: 'fixed' | 'pending';
  /** 当前快照对应的标的（v2 按标的多份存储；缺省为第一个标的） */
  symbol?: string;
  /** 该 worker 全部标的的固化状态（旧 v1 单份 worker 长度为 1） */
  symbols?: PlanSymbolState[];
  ref_price?: number | null;
  plan?: PricePlan | null;
  triggered_count?: number;
  triggered_indexes?: number[];
  next_trigger?: PlanNextTrigger | null;
}
