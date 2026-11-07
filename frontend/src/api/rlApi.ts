import { apiRequest } from './index';

// 与后端 api/rl_routes.py 的 TrainRequest 对齐：symbol 必填，其余有默认值
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

// 与后端 RLService.list_saved_models() 对齐：data/models 下真实 .zip 文件
export interface RLModelInfo {
  name: string;
  path: string;
  size_mb: number;
  created: number;
}

export const rlApi = {
  train: (data: RLTrainRequest) =>
    apiRequest.post<RLTrainResult>('/rl/train', data),
  listModels: () =>
    apiRequest.get<RLModelInfo[]>('/rl/models'),
  deleteModel: (name: string) =>
    apiRequest.delete(`/rl/models/${encodeURIComponent(name)}`),
};