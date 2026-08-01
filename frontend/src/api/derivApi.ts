/**
 * Binance 衍生数据（fundingRate / openInterest）REST API 客户端
 * 对应后端 4 个端点（backend/collector/api/deriv.py）：
 *   1. GET    /api/data/deriv/symbols
 *   2. GET    /api/data/deriv/data
 *   3. GET    /api/data/deriv/meta/{kind}/{market}/{symbol}
 *   4. DELETE /api/data/deriv/data
 *
 * 下载入口走统一的 downloadCryptoData（data_type=fundingRate|openInterest）。
 */
import { apiRequest } from './index';
import type {
  DerivKind,
  MarketType,
  ArchiveMeta,
  ArchiveRow,
} from '@/types/data';

/** 分页查询响应 */
export interface DerivQueryResponse {
  total: number;
  rows: ArchiveRow[];
  truncated: boolean;
}

export interface DerivSymbolsResponse {
  symbols: string[];
  total: number;
}

export interface DerivMetaResponse {
  meta: ArchiveMeta | null;
}

export interface DerivDeleteResponse {
  success: boolean;
  deleted: string | null;
  message: string;
}

export const derivApi = {
  /** 1) 列出 (kind, market) 下已采集的 symbols */
  listSymbols: (
    kind: DerivKind,
    market: MarketType,
  ): Promise<DerivSymbolsResponse> => {
    return apiRequest.get('/data/deriv/symbols', { kind, market });
  },

  /** 2) 分页查询某 symbol 的数据（毫秒时间范围） */
  queryData: (
    kind: DerivKind,
    market: MarketType,
    symbol: string,
    startTime: number,
    endTime: number,
    limit = 1000,
    offset = 0,
  ): Promise<DerivQueryResponse> => {
    return apiRequest.get('/data/deriv/data', {
      kind,
      market,
      symbol,
      start_time: startTime,
      end_time: endTime,
      limit,
      offset,
    });
  },

  /** 3) 读取元数据（从 parquet 推断）；不存在时 meta=null */
  getMeta: (
    kind: DerivKind,
    market: MarketType,
    symbol: string,
  ): Promise<DerivMetaResponse> => {
    return apiRequest.get(`/data/deriv/meta/${kind}/${market}/${symbol}`);
  },

  /** 4) 删除某 (kind, market, symbol) 目录下的全部数据
   *  调用前前端自行 Popconfirm。
   */
  deleteData: (
    kind: DerivKind,
    market: MarketType,
    symbol: string,
  ): Promise<DerivDeleteResponse> => {
    return apiRequest.delete('/data/deriv/data', { kind, market, symbol });
  },
};
