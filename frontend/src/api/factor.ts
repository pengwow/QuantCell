import { apiRequest } from './index';

/** 因子库明细（内置 + 自定义） */
export interface FactorDetail {
  name: string;
  expression: string;
  category: string;
  label: string;
  builtin: boolean;
  supported: boolean;
}

/** /instruments 返回的品种及其可用周期 */
export interface InstrumentInfo {
  symbol: string;
  intervals: string[];
}

export interface FactorAnalyzeParams {
  factor_name: string;
  instruments: string[];
  interval: string;
  candle_type?: string;
  start_time?: string | null;
  end_time?: string | null;
  method?: 'spearman' | 'pearson';
  n_groups?: number;
  window?: number;
  forward?: number;
}

/** 多因子对比：2-5 个因子共用一组分析参数（独立 interface，避免 factor_name 单数冲突） */
export interface FactorCompareParams {
  factor_names: string[];
  instruments: string[];
  interval: string;
  candle_type?: string;
  start_time?: string | null;
  end_time?: string | null;
  method?: 'spearman' | 'pearson';
  n_groups?: number;
  window?: number;
  forward?: number;
}

/** 多因子对比结果行：单因子 inspection + 分析核心指标 */
export interface FactorCompareRow {
  factor_name: string;
  label: string;
  coverage: number | null;
  turnover: number | null;
  ic_mean: number | null;
  ic_ir: number | null;
  annualized_ir: number | null;
  t_stat: number | null;
  ic_positive_rate: number | null;
  long_short_return: number | null;
  monotonicity_spearman: number | null;
  stability_autocorr: number | null;
  n_groups: number;
  bar_count: number;
}

export interface FactorCompareResult {
  factors: FactorCompareRow[];
  ic_series: { dates: string[]; series: Record<string, (number | null)[]> };
}

/** 因子异步任务状态值 */
export type FactorJobStatusValue = 'pending' | 'running' | 'completed' | 'failed';

/** 因子异步任务状态（WS 推送 / GET /jobs/{id}，不含结果大 payload） */
export interface FactorJobStatus {
  job_id: string;
  kind: 'analyze' | 'compare';
  status: FactorJobStatusValue;
  progress: number;
  stage: string | null;
  message: string | null;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 因子生命周期五态 */
export type LifecycleStatus = 'DISCOVERED' | 'INSPECTED' | 'PAPER_TRADING' | 'LIVE' | 'RETIRED';

/** 因子档案条目：明细 + 生命周期/最近指标/快照统计 */
export interface FactorCatalogItem extends FactorDetail {
  lifecycle_status: LifecycleStatus;
  last_metrics: {
    snapshot_id: number;
    bar_count: number;
    ic_mean: number | null;
    ic_ir: number | null;
    ic_positive_rate: number | null;
    long_short_return: number | null;
    monotonicity_spearman: number | null;
    stability_autocorr: number | null;
    created_at: string;
  } | null;
  last_snapshot_at: string | null;
  snapshot_count: number;
}

/** 因子分析快照摘要（列表项，不含 IC 大数组） */
export interface FactorSnapshotSummary {
  id: number;
  factor_name: string;
  params: FactorAnalyzeParams;
  bar_count: number;
  created_at: string | null;
  ic_mean: number | null;
  ic_ir: number | null;
  ic_positive_rate: number | null;
  long_short_return: number | null;
  monotonicity_spearman: number | null;
  stability_autocorr: number | null;
  ic_series_len: number;
}

export interface FactorAnalyzeResult {
  factor_name: string;
  instruments: string[];
  interval: string;
  bar_count: number;
  stats: { mean: number; std: number; min: number; max: number };
  ic: {
    method: string;
    series: { t: string; ic: number | null }[];
    mean: number | null;
    std: number | null;
    ir: number | null;
    positive_rate: number | null;
  };
  groups: { group: number; mean_forward_return: number }[];
  long_short_return: number | null;
  monotonicity: { spearman: number; p_value: number; score: number | null };
  stability: { window: number; mean_autocorr: number | null };
  series: { dates: string[]; close: number[]; factor: Record<string, number> };
  inspection?: {
    coverage: number | null;
    turnover: number | null;
    decay: { lag: number; spearman: number | null; pearson: number | null }[];
    ic_stats: {
      n: number;
      ic_mean: number | null;
      ic_std: number | null;
      ic_ir: number | null;
      periods_per_year: number;
      annualized_ir: number | null;
      t_stat: number | null;
    };
  };
}

export const factorApi = {
  listDetail: () => apiRequest.get<{ factors: FactorDetail[] }>('/factor/list-detail'),
  add: (factor_name: string, expression: string) =>
    apiRequest.post('/factor/add', { factor_name, expression }),
  remove: (name: string) =>
    apiRequest.delete(`/factor/delete/${encodeURIComponent(name)}`),
  validate: (expression: string) =>
    apiRequest.post<{ valid: boolean }>('/factor/validate', { expression }),
  analyze: (p: FactorAnalyzeParams) =>
    apiRequest.post<FactorAnalyzeResult>('/factor/analyze', p),
  compare: (p: FactorCompareParams) =>
    apiRequest.post<FactorCompareResult>('/factor/compare', p),
  analyzeAsync: (p: FactorAnalyzeParams) =>
    apiRequest.post<{ job_id: string; status: string }>('/factor/analyze-async', p),
  compareAsync: (p: FactorCompareParams) =>
    apiRequest.post<{ job_id: string; status: string }>('/factor/compare-async', p),
  getFactorJob: (id: string) =>
    apiRequest.get<FactorJobStatus>(`/factor/jobs/${id}`),
  getFactorJobResult: <T,>(id: string) =>
    apiRequest.get<T>(`/factor/jobs/${id}/result`),
  instruments: (candle_type = 'spot') =>
    apiRequest.get<{ symbols: InstrumentInfo[] }>('/factor/instruments', { candle_type }),
  catalog: () => apiRequest.get<{ factors: FactorCatalogItem[] }>('/factor/catalog'),
  updateLifecycle: (name: string, status: LifecycleStatus) =>
    apiRequest.post(`/factor/catalog/${encodeURIComponent(name)}/lifecycle`, { status }),
  saveSnapshot: (p: FactorAnalyzeParams) => apiRequest.post<{ id: number }>('/factor/snapshots', p),
  listSnapshots: (name: string) =>
    apiRequest.get<{ snapshots: FactorSnapshotSummary[] }>('/factor/snapshots', { factor_name: name }),
  deleteSnapshot: (id: number) => apiRequest.delete(`/factor/snapshots/${id}`),
};
