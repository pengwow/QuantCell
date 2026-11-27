/**
 * 价格计划 API client —— 单独成文件避免塞进 index.ts 已有 strategyApi；
 * 复用全局 apiRequest（api/index.ts，baseURL 已含 /api/v1，响应已解包，
 * 用法与 workerApi.ts 的 getWorker 一致）
 */
import { apiRequest } from './index';
import type { PricePlanPreviewResponse, WorkerPlanResponse } from '../types/pricePlan';

export interface PricePlanPreviewPayload {
  strategy_name: string;
  params?: Record<string, unknown>;
  ref_price?: number;
}

/** POST /api/v1/strategies/preview —— 422 detail={code,message} 由调用方处理 */
export const previewPricePlan = (payload: PricePlanPreviewPayload): Promise<PricePlanPreviewResponse> =>
  apiRequest.post('/strategies/preview', payload);

/** GET /api/v1/workers/{id}/plan —— 固化计划 + 运行态增量 */
export const getWorkerPlan = (workerId: number): Promise<WorkerPlanResponse> =>
  apiRequest.get(`/workers/${workerId}/plan`);

// 实时最新价（GET /marketdata/price）：价格计划参考价自动预览的取价通道。
// 注意：apiRequest.get 的第二参就是查询参数本体，不要再包 { params }（见
// docs/testing/pages/strategy-worker.md 历史雷区）。
export interface LatestPriceResponse {
  symbol: string;
  price: number;
  ts: string;
}

export const fetchLatestPrice = (query: {
  symbol: string;
  market_type: string;
  exchange: string;
}): Promise<LatestPriceResponse> => apiRequest.get('/marketdata/price', query);
