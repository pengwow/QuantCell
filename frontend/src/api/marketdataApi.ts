/**
 * marketdata 行情数据 API
 *
 * 有意不 re-export 进 api/index.ts：本模块 import api/index 的 apiRequest，
 * 若 index 再反向导出本模块会形成循环（dataApi 注释里已踩过 TDZ 坑）。
 * 消费方直接 `import { marketdataApi } from '@/api/marketdataApi'`。
 */
import { apiRequest } from './index';

/** 深度档位 [price, quantity] */
export type DepthLevel = [number, number];

export interface DepthSnapshot {
  symbol: string;
  bids: DepthLevel[];
  asks: DepthLevel[];
  /** 快照生成时间（毫秒） */
  timestamp: number;
}

export interface OiHistoryRow {
  timestamp: number;
  openInterest: number;
}

export interface FundingHistoryRow {
  timestamp: number;
  fundingRate: number;
}

export const marketdataApi = {
  /** 深度快照（limit 与推流深度档数共用一个配置） */
  getDepthSnapshot: (symbol: string, limit = 20): Promise<DepthSnapshot> =>
    apiRequest.get<DepthSnapshot>('/marketdata/depth', { symbol, limit }),

  /** 持仓量历史（K线粒度，时间戳毫秒） */
  getOiHistory: (symbol: string, interval: string, limit = 200): Promise<OiHistoryRow[]> =>
    apiRequest.get<OiHistoryRow[]>('/marketdata/oi/history', { symbol, interval, limit }),

  /** 资金费率历史（结算时点序列，时间戳毫秒） */
  getFundingHistory: (symbol: string, limit = 200): Promise<FundingHistoryRow[]> =>
    apiRequest.get<FundingHistoryRow[]>('/marketdata/funding/history', { symbol, limit }),
};
