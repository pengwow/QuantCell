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

// UnifiedModelRow: 与后端 services/model_registry.list_unified_models 行结构逐字段对齐
export interface UnifiedModelRow {
  file_name: string;
  path: string | null; // 文件缺失条目回显的来源路径,可能为 null
  size_mb: number | null; // 文件缺失时为 null → 前端「文件缺失」态
  created: number | null; // 秒级 unix;无任何时间来源时为 null
  algorithm: string; // registry metadata 优先,否则文件名推断;无值为 "-"
  registered: boolean;
  model_id: string | null; // 未注册为 null
  version: string;
  stage: string; // staging | production | archived;未注册为 ""
  metrics: Record<string, number>;
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
  unifiedModels: () => apiRequest.get<UnifiedModelRow[]>('/models/unified'),
};
