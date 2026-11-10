import { apiRequest } from './index';

// 与后端 GET /ensemble/list 返回字段对齐(spec §5.3)
export interface EnsembleInfo {
  id: string;
  models: number;
  strategy: string;
  model_paths: string[];
  created_at: number | null; // 秒级 unix
}

export interface EnsemblePredictResult {
  action: string;
  confidence: number;
}

// POST /ensemble/create 响应:创建成功但可能有模型加载失败被跳过
export interface EnsembleCreateResult {
  ensemble_id: string;
  skipped: { path: string; reason: string }[];
}

export const ensembleApi = {
  // 修复:原 /v2/ensemble/* 拼上 baseURL(/api/v1)后全部 404,后端实际路由无 /v2 段
  listEnsembles: () => apiRequest.get<EnsembleInfo[]>('/ensemble/list'),
  createEnsemble: (data: { strategy: string; model_paths: string[] }) =>
    apiRequest.post<EnsembleCreateResult>('/ensemble/create', data),
  deleteEnsemble: (id: string) => apiRequest.delete(`/ensemble/${id}`),
  predict: (ensembleId: string, observation: Record<string, number>) =>
    apiRequest.post<EnsemblePredictResult>(`/ensemble/${ensembleId}/predict`, { observation }),
};
