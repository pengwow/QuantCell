import { apiRequest } from './index';

// 与后端 api/v2/rl_routes.py 的 TrainRequest 对齐：symbol 必填，其余有默认值
export interface RLTrainRequest {
  algorithm?: string;
  symbol: string;
  interval?: string;
  candle_type?: string;
  start?: string | null;
  end?: string | null;
  total_timesteps?: number;
  reward_type?: string;
  walk_forward?: boolean;
  wf_splits?: number;
}

export interface RLTrainResult {
  model_id: string;
  status: string;
  metrics: Record<string, number>;
  walk_forward?: unknown;
}

// 后端 model_registry list_models 仅返回 [{ name }]
export interface RLModelInfo {
  name: string;
}

export const rlApi = {
  train: (data: RLTrainRequest) =>
    apiRequest.post<RLTrainResult>('/v2/rl/train', data),
  listModels: () =>
    apiRequest.get<RLModelInfo[]>('/v2/rl/models'),
};
