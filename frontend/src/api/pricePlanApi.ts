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

/** GET /api/v1/workers/{id}/plan —— 固化计划 + 运行态增量（多标的固化后按 symbol 取对应快照） */
export const getWorkerPlan = (workerId: number, symbol?: string): Promise<WorkerPlanResponse> =>
  apiRequest.get(`/workers/${workerId}/plan`, symbol ? { symbol } : undefined);

/**
 * GET /api/v1/marketdata/klines —— 真实K线（ts 毫秒升序，价格计划预览用）。
 * 注意：apiRequest.get 的第二参就是查询本体，不要再包 { params }（历史雷区）。
 */
export interface KlineBar {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/** 后端 interval 白名单（与 backend/marketdata/service.py 的 _KLINES_INTERVALS 一致） */
export const KLINE_INTERVALS = ['1m', '5m', '15m', '1h', '4h', '1d'] as const;
export type KlineInterval = (typeof KLINE_INTERVALS)[number];

export const fetchKlines = (query: {
  symbol: string;
  market_type: string;
  exchange: string;
  interval: KlineInterval;
  limit?: number;
}): Promise<KlineBar[]> => apiRequest.get('/marketdata/klines', query);

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
