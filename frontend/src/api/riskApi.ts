import { apiRequest } from './index';

export interface RiskMetrics {
  total_checks: number;
  rejected_orders: number;
  rejection_rate: number;
}

export interface RiskCheckResult {
  passed: boolean;
  reason: string | null;
}

export const riskApi = {
  checkOrder: (data: { order: Record<string, unknown>; portfolio: Record<string, unknown> }) =>
    apiRequest.post<RiskCheckResult>('/v2/risk/check', data),
  getMetrics: () =>
    apiRequest.get<RiskMetrics>('/v2/risk/metrics'),
  resetDaily: () =>
    apiRequest.post('/v2/risk/reset'),
};
