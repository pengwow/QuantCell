import { apiRequest } from './index';

export interface EnsembleInfo {
  id: string;
  models: number;
  strategy: string;
}

export interface EnsemblePredictResult {
  action: string;
  confidence: number;
}

export const ensembleApi = {
  listEnsembles: () => apiRequest.get<EnsembleInfo[]>('/v2/ensemble/list'),
  createEnsemble: (data: { strategy: string; model_paths: string[] }) =>
    apiRequest.post<{ ensemble_id: string }>('/v2/ensemble/create', data),
  predict: (ensembleId: string, observation: Record<string, number>) =>
    apiRequest.post<EnsemblePredictResult>(`/v2/ensemble/${ensembleId}/predict`, { observation }),
};
