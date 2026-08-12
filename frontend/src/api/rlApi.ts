import { apiRequest } from './index';

export interface RLTrainRequest {
  algorithm: string;
  data_source: string;
  total_timesteps: number;
  reward_type: string;
  walk_forward: boolean;
  hpo: boolean;
}

export interface RLTrainResult {
  model_id: string;
  status: string;
  metrics: Record<string, number>;
}

export const rlApi = {
  train: (data: RLTrainRequest) =>
    apiRequest.post<RLTrainResult>('/v2/rl/train', data),
  listModels: () =>
    apiRequest.get<any[]>('/v2/rl/models'),
};
