import { apiRequest } from './index';

export interface ModelInfo {
  id: string;
  name: string;
  version: string;
  stage: string; // production | development | archived(Rust 术语)
  metrics: Record<string, number>;
}

export interface ModelFeatureSpec {
  name: string;
  source_display: string;
  normalizer: string | null;
  clip_range: number[] | null;
}

export interface ModelDetail {
  name: string;
  version: string;
  stage: string;
  metadata: Record<string, unknown>;
  metrics: Record<string, number>;
  artifact_size_bytes: number;
  artifact_hash: string;
  storage_uri: string;
  // 模型卡扩展字段:service 从 metadata 聚合,旧数据为占位值("-" / 空数组)
  algorithm: string;
  trained_at: string;
  spec_version: string;
  window_size: number | string;
  features: ModelFeatureSpec[];
  observation_stats_present: boolean;
  walk_forward: Record<string, unknown>;
}

export const modelApi = {
  listModels: () => apiRequest.get<ModelInfo[]>('/models/list'),
  registerModel: (data: { name: string; model_path: string; metadata?: object; metrics?: object }) =>
    apiRequest.post('/models/register', data),
  promoteModel: (modelId: string) =>
    apiRequest.post(`/models/${modelId}/promote`),
  unpromoteModel: (modelId: string) =>
    apiRequest.post(`/models/${modelId}/unpromote`),
  getModelDetail: (name: string) =>
    apiRequest.get<ModelDetail>(`/models/${encodeURIComponent(name)}/detail`),
};
