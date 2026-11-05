import { apiRequest } from './index';

/**
 * 研究模块 API（P0.5 起独立为一级模块，后端前缀 /api/v1/research）。
 * 因子专属的接口仍在 api/factor.ts，避免两个模块互相 import。
 */

export type ResearchMode = 'quick' | 'deep';
export type ResearchStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ResearchMetrics {
  ic_mean?: number | null;
  ic_ir?: number | null;
  fitness?: number | null;
  annualized_ir?: number | null;
  long_short_return?: number | null;
  [key: string]: unknown;
}

export interface ResearchGate {
  pass: boolean;
  /** pass / fail / unknown（unknown 表示缺少对比数据，按未通过处理） */
  status?: 'pass' | 'fail' | 'unknown';
  value?: number | string | null;
  floor?: number;
  threshold?: number | null;
  [key: string]: unknown;
}

/** 过程事件（GET /sessions/{id}/events 增量拉取，seq 严格递增） */
export interface ResearchEvent {
  seq: number;
  ts: number;
  level: string;
  stage: string;
  msg: string;
  p?: number | null;
}

/**
 * judge 结构按场景不同：
 * - deep（factor）：icir / oos / corr 三门
 * - quick：只有 redundant 一门，decision 为 null
 * 因此 gates 必须可选，页面按 key 存在性做防御读取。
 */
export interface ResearchJudge {
  decision: boolean | null;
  gates?: {
    icir?: ResearchGate;
    oos?: ResearchGate;
    corr?: ResearchGate;
    redundant?: ResearchGate;
  };
  reason: string;
}

export interface ResearchTrial {
  id: number;
  loop_idx: number;
  candidate_idx: number;
  status: string;
  hypothesis: string | null;
  hypothesis_reason?: string | null;
  hypothesis_prediction?: string | null;
  task: { name?: string; description?: string; formulation?: string } | null;
  code_hash: string | null;
  code?: string | null;
  metrics: ResearchMetrics;
  metrics_oos?: ResearchMetrics;
  oos_flag: string | null;
  oos_note?: string | null;
  feedback: Record<string, unknown> | null;
  judge: ResearchJudge | null;
  decision: boolean | null;
  corr_sota?: number | null;
  corr_library?: number | null;
  promoted_factor_name: string | null;
  quick_run_id: number | null;
  parent_trial_id: number | null;
  replay_of_id: number | null;
  replay_meta?: ResearchReplayMeta | null;
  token_used: number;
  llm_calls: number;
  model?: string | null;
  prompt_hash?: string | null;
  temperature?: number | null;
  duration_ms?: number;
  exception: string | null;
  created_at: string | null;
}

/** 回放元数据：缺字段/差异阈值/不可复现项，刷新后仍可展示 */
export interface ResearchReplayMeta {
  original_trial_id: number;
  partial: boolean;
  missing: string[];
  notes: string[];
  tolerance: { ic_ir: number };
  diff: {
    ic_ir: number | null;
    oos_changed: boolean;
    corr_library: number | null;
  };
  consistent: boolean;
  unreproducible: string[];
}

export interface ResearchReplayResult {
  trial: ResearchTrial;
  original: ResearchTrial;
  replay_meta: ResearchReplayMeta;
}

export interface ResearchSession {
  id: number;
  name: string;
  mode: ResearchMode;
  scenario?: string;
  status: ResearchStatus;
  n_candidates: number;
  loop_n: number;
  loop_done: number;
  step_idx: number;
  token_used: number;
  llm_calls: number;
  max_tokens: number | null;
  max_llm_calls: number | null;
  best_trial_id: number | null;
  best_ic_ir: number | null;
  error: string | null;
  config: Record<string, unknown>;
  backend_job_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  extended_at: string | null;
  trials?: ResearchTrial[];
}

export interface ResearchCreateParams {
  mode: ResearchMode;
  scenario?: string;
  name?: string;
  symbols: string[];
  interval: string;
  candle_type?: 'spot' | 'future';
  start: string;
  end: string;
  n_candidates?: number;
  loop_n?: number;
  tasks_per_loop?: number;
  repair_rounds?: number;
  max_llm_calls?: number;
  max_tokens?: number;
  icir_floor?: number;
  corr_threshold?: number;
  seed_factor?: string | null;
  model_id?: string | null;
  temperature?: number;
  test_ratio?: number;
  wf_folds?: number;
  compose?: boolean;
}

export interface ResearchListParams {
  mode?: ResearchMode;
  status?: ResearchStatus;
  limit?: number;
  offset?: number;
}

export const researchApi = {
  create: (p: ResearchCreateParams) =>
    apiRequest.post<{ session_id: number; job_id: string }>('/research/sessions', p),
  list: (params?: ResearchListParams) =>
    apiRequest.get<{ total: number; sessions: ResearchSession[] }>('/research/sessions', params),
  get: (id: number) => apiRequest.get<ResearchSession>(`/research/sessions/${id}`),
  listTrials: (id: number, include_code = false) =>
    apiRequest.get<{ trials: ResearchTrial[] }>(`/research/sessions/${id}/trials`, {
      include_code,
    }),
  getTrial: (id: number, trialId: number) =>
    apiRequest.get<ResearchTrial>(`/research/sessions/${id}/trials/${trialId}`),
  events: (id: number, after_seq = 0) =>
    apiRequest.get<{ events: ResearchEvent[]; next_seq: number }>(
      `/research/sessions/${id}/events`,
      { after_seq },
    ),
  promote: (id: number, trialId: number) =>
    apiRequest.post<{ factor_name: string }>(
      `/research/sessions/${id}/trials/${trialId}/promote`,
    ),
  replay: (id: number, trialId: number) =>
    apiRequest.post<ResearchReplayResult>(`/research/sessions/${id}/trials/${trialId}/replay`),
  pause: (id: number) => apiRequest.post<ResearchSession>(`/research/sessions/${id}/pause`),
  resume: (id: number) =>
    apiRequest.post<{ session_id: number; job_id: string }>(`/research/sessions/${id}/resume`),
  cancel: (id: number) => apiRequest.post<ResearchSession>(`/research/sessions/${id}/cancel`),
  extend: (
    id: number,
    p: { extra_loops?: number; extra_max_llm_calls?: number; extra_max_tokens?: number },
  ) => apiRequest.post<{ session_id: number; job_id: string }>(`/research/sessions/${id}/extend`, p),
};
