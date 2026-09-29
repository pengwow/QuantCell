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
  instruments: (candle_type = 'spot') =>
    apiRequest.get<{ symbols: InstrumentInfo[] }>('/factor/instruments', { candle_type }),
};
