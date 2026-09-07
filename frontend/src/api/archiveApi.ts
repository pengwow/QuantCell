/**
 * Binance 归档数据 REST API 客户端
 * 对应后端 6 个端点（backend/collector/api/archive.py）：
 *   1. POST   /api/data/archive/download
 *   2. GET    /api/data/archive/tasks/{task_id}
 *   3. GET    /api/data/archive/symbols
 *   4. GET    /api/data/archive/data
 *   5. GET    /api/data/archive/meta/{kind}/{market}/{symbol}
 *   6. DELETE /api/data/archive/data
 *
 * 复用项目已有的 apiRequest（带 token、401 拦截、code 适配）
 */
import { apiRequest } from './index';
import type {
  ArchiveKind,
  ArchiveMeta,
  ArchiveRow,
  ArchiveTaskRequest,
  MarketType,
  TaskProgressInfo,
  TaskStatus,
} from '@/types/data';

/**
 * 创建归档下载任务成功后返回的响应
 */
export interface ArchiveDownloadResponse {
  success: boolean;
  task_id: string;
  status: string;
  message: string;
}

/**
 * 分页查询数据的响应
 * - total: 总行数（不限于本次返回的 limit）
 * - rows:  本次返回的行
 * - truncated: 是否被后端 limit 截断
 */
export interface ArchiveQueryResponse {
  total: number;
  rows: ArchiveRow[];
  truncated: boolean;
}

/**
 * 列表 symbol 响应
 */
export interface ArchiveSymbolsResponse {
  symbols: string[];
  total: number;
}

/**
 * 元数据响应（meta 可能为 null：_meta.json 不存在时）
 */
export interface ArchiveMetaResponse {
  meta: ArchiveMeta | null;
}

/**
 * 删除数据响应
 */
export interface ArchiveDeleteResponse {
  success: boolean;
  deleted: string | null;
  message: string;
}

/**
 * 归档任务详情（与后端 task_manager 返回的 task dict 对齐）
 */
export interface ArchiveTaskDetail {
  task_id: string;
  status: TaskStatus;
  progress: TaskProgressInfo;
  log?: string[];
  error_message?: string;
  created_at?: string;
  updated_at?: string;
}

export const archiveApi = {
  /**
   * 1) 创建归档下载任务
   * K 线类缺 interval 时后端会返回 400，由 axios 拦截器转为 ApiError
   */
  downloadTask: (req: ArchiveTaskRequest): Promise<ArchiveDownloadResponse> => {
    return apiRequest.post('/data/archive/download', req);
  },

  /**
   * 2) 查询归档任务进度
   * 返回 task_manager 中的完整 task dict（含 status/progress/log 等）
   */
  getTask: (taskId: string): Promise<ArchiveTaskDetail> => {
    return apiRequest.get(`/data/archive/tasks/${taskId}`);
  },

  /**
   * 3) 列出某 (kind, market) 下已采集的 symbols
   */
  listSymbols: (
    kind: ArchiveKind,
    market: MarketType,
  ): Promise<ArchiveSymbolsResponse> => {
    return apiRequest.get('/data/archive/symbols', { kind, market });
  },

  /**
   * 4) 分页查询某 symbol 的数据
   * @param startTime 起始时间（毫秒）
   * @param endTime   结束时间（毫秒）
   * @param limit     分页行数上限（默认 1000）
   * @param offset    分页偏移（默认 0）
   */
  queryData: (
    kind: ArchiveKind,
    market: MarketType,
    symbol: string,
    startTime: number,
    endTime: number,
    limit = 1000,
    offset = 0,
  ): Promise<ArchiveQueryResponse> => {
    return apiRequest.get('/data/archive/data', {
      kind,
      market,
      symbol,
      start_time: startTime,
      end_time: endTime,
      limit,
      offset,
    });
  },

  /**
   * 5) 读取 _meta.json；不存在时返回 null
   */
  getMeta: (
    kind: ArchiveKind,
    market: MarketType,
    symbol: string,
  ): Promise<ArchiveMetaResponse> => {
    return apiRequest.get(`/data/archive/meta/${kind}/${market}/${symbol}`);
  },

  /**
   * 6) 删除某 (kind, market, symbol) 目录下的全部数据
   * 注意：后端不要求确认，前端调用前需自行 Popconfirm
   */
  deleteData: (
    kind: ArchiveKind,
    market: MarketType,
    symbol: string,
  ): Promise<ArchiveDeleteResponse> => {
    return apiRequest.delete('/data/archive/data', { kind, market, symbol });
  },
};
