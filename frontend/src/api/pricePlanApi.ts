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
