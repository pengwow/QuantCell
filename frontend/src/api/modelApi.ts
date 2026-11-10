import { apiRequest } from './index';

export interface ModelInfo {
  id: string;
  name: string;
  version: string;
  stage: string; // production | development | archived(Rust 术语)
  metrics: Record<string, number>;
}

export const modelApi = {
  listModels: () => apiRequest.get<ModelInfo[]>('/models/list'),
  registerModel: (data: { name: string; model_path: string; metadata?: object; metrics?: object }) =>
    apiRequest.post('/models/register', data),
  promoteModel: (modelId: string) =>
    apiRequest.post(`/models/${modelId}/promote`),
};
