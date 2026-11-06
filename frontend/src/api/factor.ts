import { apiRequest } from './index';

/** 因子库明细（内置 + 自定义） */
export interface FactorDetail {
  name: string;
  expression: string;
  category: string;
  label: string;
  builtin: boolean;
  supported: boolean;
  /** 因子形态：表达式因子 / Python 代码因子（LLM 挖掘保存）/ IC 加权合成因子 */
  kind?: 'expression' | 'code' | 'composite';
  description?: string;
  /** 合成因子的成分数量（kind=composite 时返回） */
  constituents_count?: number;
}

/** 因子形态（与后端 get_factor_definition 返回的 kind 对齐） */
export type FactorKind = 'expression' | 'code' | 'composite';

export interface ExpressionDefinition {
  kind: 'expression';
  name: string;
  expression: string;
  builtin: boolean;
}
export interface CodeFactorDefinition {
  kind: 'code';
  name: string;
  code: string;
  code_hash: string;
  description?: string;
}
export interface CompositeConstituentDef {
  code: string;
  code_hash: string;
  weight: number;
}
export interface FactorTrainWindow {
  start?: string;
  end?: string;
  interval?: string;
  candle_type?: string;
}
export interface CompositeFactorDefinition {
  kind: 'composite';
  name: string;
  method: string;
  description?: string;
  train_window?: FactorTrainWindow;
  constituents: CompositeConstituentDef[];
}
export type FactorDefinition =
  | ExpressionDefinition
  | CodeFactorDefinition
  | CompositeFactorDefinition;

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
  /** 自定义衰减 lag（K线根数）；null/不传 = 默认 [1,2,3,5,10] */
  horizons?: number[] | null;
  /** 单边交易成本基点，默认 0（如 10 = 0.1%） */
  cost_bps?: number;
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
  /** 自定义衰减 lag（K线根数）；null/不传 = 默认 [1,2,3,5,10] */
  horizons?: number[] | null;
  /** 单边交易成本基点，默认 0（如 10 = 0.1%） */
  cost_bps?: number;
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
  nw_t_stat: number | null;
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

/** 合成因子拟合的 train 段时间窗（仅记录） */
export interface CompositeTrainWindow {
  start: string;
  end: string;
  interval: string;
  candle_type: string;
}

/** 挖掘结果内的合成因子成分（权重 + 冻结的逐品种时序统计） */
export interface CompositeConstituent {
  code_hash: string;
  weight: number;
  ts_stats: Record<string, { mean: number; std: number }>;
}

/** 保存合成因子时上送的成分（code 由 candidates 的 hash→code 组装） */
export interface CompositeConstituentPayload {
  code: string;
  weight: number;
  ts_stats: Record<string, { mean: number; std: number }>;
}

/** POST /factor/composite/add 请求体 */
export interface FactorCompositeAddBody {
  factor_name: string;
  description?: string;
  /** 中文展示名（可选）；缺省用 factor_name */
  label?: string;
  constituents: CompositeConstituentPayload[];
  train_window: CompositeTrainWindow;
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

/** 挖掘过程事件（WS type=event 增量 / GET jobs/{id}/events / run detail.events） */
export type MiningEventLevel = 'info' | 'warning';
export interface MiningEvent {
  idx: number;
  ts: string;
  level: MiningEventLevel;
  stage: 'data_load' | 'generating' | 'evaluating' | 'dedup' | 'composite' | 'completed' | string;
  msg: string;
  p: number | null;
}

/** WS factor:job 消息的 data：进度态或事件态 */
export interface FactorJobEventEnvelope {
  job_id: string;
  type: 'event';
  event: MiningEvent;
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
    coverage: number | null;
    turnover: number | null;
    annualized_ir: number | null;
    nw_t_stat: number | null;
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

/** 快照详情：入参 + 完整分析结果（metrics_json 反序列化，零重算） */
export interface FactorSnapshotDetail {
  id: number;
  factor_name: string;
  params: FactorAnalyzeParams;
  bar_count: number;
  created_at: string | null;
  result: FactorAnalyzeResult;
}

/** 分位组合净值曲线（inspection.quantile_nav） */
export interface QuantileNav {
  /** 时间轴 */
  dates: string[];
  /** 单边费率 = cost_bps/10000 */
  fee_rate: number;
  /** 每个分位组一条曲线；空仓期净值由后端延续（1.0 平铺），nav 连续非 null */
  groups: {
    group: number;
    coverage: number;
    /** 双边换手（每 bar） */
    turnover: number;
    /** 毛收益（旧字段，可能含 null） */
    returns: (number | null)[];
    /** 毛净值（旧字段，可能含 null） */
    nav: (number | null)[];
    /** 费后逐期收益（连续无 null） */
    returns_net: number[];
    /** 费后净值（连续无 null） */
    nav_net: number[];
  }[];
  /** 截面多空逐期收益（时序口径下全 null） */
  long_short_returns: (number | null)[];
  /** 截面多空毛净值（null=该数据口径不可构造） */
  long_short_nav: (number | null)[] | null;
  /** 多空双边换手（每 bar） */
  long_short_turnover: number | null;
  /** 费后多空净值（null=该数据口径不可构造） */
  long_short_nav_net: (number | null)[] | null;
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
      nw_t_stat: number | null;
      nw_lag: number;
    };
    quantile_nav?: QuantileNav;
  };
}

export const factorApi = {
  listDetail: () => apiRequest.get<{ factors: FactorDetail[] }>('/factor/list-detail'),
  add: (factor_name: string, expression: string, category?: string, description?: string, label?: string) =>
    apiRequest.post('/factor/add', { factor_name, expression, category, description, label }),
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
  validateCodeFactor: (code: string) =>
    apiRequest.post<{ valid: boolean; error_type?: string; message?: string }>(
      '/factor/code/validate',
      { code },
    ),
  validateExpression: (expression: string) =>
    apiRequest.post<{ valid: boolean; error_type?: string; message?: string }>(
      '/factor/validate',
      { expression },
    ),
  addCodeFactor: (
    factor_name: string,
    code: string,
    description?: string,
    category?: string,
    label?: string,
  ) => apiRequest.post('/factor/code/add', { factor_name, code, description, category, label }),
  addCompositeFactor: (body: FactorCompositeAddBody) =>
    apiRequest.post('/factor/composite/add', body),
  deleteCompositeFactor: (name: string) =>
    apiRequest.delete(`/factor/composite/${encodeURIComponent(name)}`),
  getFactorJob: (id: string) =>
    apiRequest.get<FactorJobStatus>(`/factor/jobs/${id}`),
  getFactorJobResult: <T,>(id: string) =>
    apiRequest.get<T>(`/factor/jobs/${id}/result`),
  getFactorJobEvents: (id: string, afterIdx = 0) =>
    apiRequest.get<{ events: MiningEvent[]; next_idx: number }>(
      `/factor/jobs/${id}/events`,
      { after_idx: afterIdx },
    ),
  getFactorDefinition: (name: string) =>
    apiRequest.get<FactorDefinition>(`/factor/factors/${encodeURIComponent(name)}/definition`),
  instruments: (candle_type = 'spot') =>
    apiRequest.get<{ symbols: InstrumentInfo[] }>('/factor/instruments', { candle_type }),
  catalog: () => apiRequest.get<{ factors: FactorCatalogItem[] }>('/factor/catalog'),
  updateLifecycle: (name: string, status: LifecycleStatus) =>
    apiRequest.post(`/factor/catalog/${encodeURIComponent(name)}/lifecycle`, { status }),
  updateCategory: (name: string, category: string) =>
    apiRequest.post<{ name: string; category: string }>(
      `/factor/catalog/${encodeURIComponent(name)}/category`,
      { category },
    ),
  saveSnapshot: (p: FactorAnalyzeParams) => apiRequest.post<{ id: number }>('/factor/snapshots', p),
  listSnapshots: (name: string) =>
    apiRequest.get<{ snapshots: FactorSnapshotSummary[] }>('/factor/snapshots', { factor_name: name }),
  deleteSnapshot: (id: number) => apiRequest.delete(`/factor/snapshots/${id}`),
  getSnapshot: (id: number) =>
    apiRequest.get<FactorSnapshotDetail>(`/factor/snapshots/${id}`),
};
