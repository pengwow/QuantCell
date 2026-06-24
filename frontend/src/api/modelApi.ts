import { apiRequest } from './index';

export interface ModelInfo {
  id: string;
  name: string;
  version: string;
  status: string;
  metrics: Record<string, number>;
}

export const modelApi = {
  listModels: () => apiRequest.get<ModelInfo[]>('/v2/models/list'),
  registerModel: (data: { name: string; model_path: string; metadata?: object; metrics?: object }) =>
    apiRequest.post('/v2/models/register', data),
  promoteModel: (modelId: string) =>
    apiRequest.post(`/v2/models/${modelId}/promote`),
};
