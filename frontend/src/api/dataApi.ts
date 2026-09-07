/**
 * 数据管理相关 API
 * 从旧版本迁移过来
 */
import { apiRequest } from './index';
import type { Task, KlineData } from '../types/data';

// 数据池（自选组）记录
export interface DataPoolRecord {
  id: string | number;
  name: string;
  description?: string;
  color?: string;
  is_default?: boolean;
  symbols?: string[];
  created_at?: string;
  updated_at?: string;
}

// 货币对条目
export interface CryptoSymbol {
  id?: string | number;
  symbol: string;
  base?: string;
  quote?: string;
}

// 任务子任务详情条目（任务详情列表元素）
export interface TaskDetailItem {
  task_key?: string;
  symbol?: string;
  interval?: string;
  percentage?: number;
  [key: string]: unknown;
}

// K线质量检查结果（对应后端 /data/quality/kline 的返回结构）
export interface KlineQualityReport {
  total_records?: number;
  summary?: { status?: string; score?: number };
  details?: {
    integrity?: {
      status?: string;
      total_records?: number;
      missing_columns?: string[];
      missing_values?: Record<string, number>;
    };
    continuity?: {
      status?: string;
      expected_records?: number;
      actual_records?: number;
      missing_records?: number;
      coverage_ratio?: number;
      missing_time_ranges?: Array<{ start?: string; end?: string; count?: number }>;
    };
    uniqueness?: {
      status?: string;
      duplicate_records?: number;
      duplicate_periods?: string[];
      duplicate_details?: Array<{
        key?: string;
        count?: number;
        records?: Array<{ row_number?: number; open?: number; high?: number; low?: number; close?: number; volume?: number }>;
      }>;
    };
    validity?: {
      status?: string;
      total_invalid_records?: number;
      negative_prices?: unknown[];
      negative_volumes?: unknown[];
      invalid_high_low?: unknown[];
      invalid_price_logic?: unknown[];
      abnormal_price_changes?: Array<{ timestamp?: number; change_pct?: number }>;
      abnormal_volumes?: Array<{ timestamp?: number; volume?: number; avg_30d_volume?: number }>;
      price_gaps?: Array<{ timestamp?: number; gap_pct?: number }>;
    };
    consistency?: {
      status?: string;
      time_format_issues?: string[];
      duplicate_codes?: string[];
      code_name_mismatches?: string[];
      inconsistent_adj_factors?: string[];
    };
    logic?: {
      status?: string;
      trading_time_issues?: string[];
      suspension_issues?: string[];
      price_limit_issues?: string[];
    };
    coverage?: {
      status?: string;
      data_start_date?: string;
      data_end_date?: string;
      expected_start_date?: string;
      expected_end_date?: string;
      missing_historical_data?: boolean;
      historical_gap_days?: number;
      missing_future_data?: boolean;
      future_gap_days?: number;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export const dataApi = {
  /**
   * 获取加密货币数据
   * @returns 加密货币数据
   */
  getCryptoData: () => {
    return apiRequest.get('/data/crypto');
  },

  /**
   * 获取股票数据
   * @returns 股票数据
   */
  getStockData: () => {
    return apiRequest.get('/data/stock');
  },

  /**
   * 开始导入数据
   * @param data 导入数据
   * @returns 导入结果
   */
  startImport: (data: Record<string, unknown>) => {
    return apiRequest.post('/data/import', data);
  },

  /**
   * 开始数据质量检查
   * @param data 检查数据
   * @returns 检查结果
   */
  startQualityCheck: (data: Record<string, unknown>) => {
    return apiRequest.post('/data/quality/check', data);
  },

  /**
   * 生成数据可视化图表
   * @param data 图表数据
   * @returns 图表 URL
   */
  generateVisualization: (data: Record<string, unknown>) => {
    return apiRequest.post('/data/visualization/generate', data);
  },

  /**
   * 获取数据采集任务列表
   * @param params 查询参数
   * @returns 任务列表
   */
  getTasks: (params: Record<string, unknown>): Promise<{
    tasks?: Task[];
    total?: number;
    page?: number;
    page_size?: number;
  }> => {
    return apiRequest.get('/data/tasks', params);
  },

  /**
   * 获取任务状态
   * @param taskId 任务 ID
   * @returns 任务状态
   */
  getTaskStatus: (taskId: string) => {
    return apiRequest.get(`/data/task/${taskId}`);
  },

  /**
   * 下载加密货币数据
   * @param data 下载参数
   * @returns 下载结果
   */
  downloadCryptoData: (data: Record<string, unknown>): Promise<{
    task_id?: string;
    status?: string;
    message?: string;
  }> => {
    return apiRequest.post('/data/download/crypto', data);
  },

  /**
   * 获取数据服务状态
   * @returns 服务状态
   */
  getServiceStatus: () => {
    return apiRequest.get('/data/status');
  },

  /**
   * 获取K线数据
   * @param params 查询参数，包括symbol、interval、limit等
   * @returns K线数据
   */
  getKlines: (params: Record<string, unknown>): Promise<
    KlineData[] | {
      data?: KlineData[];
      klines?: KlineData[];
      total?: number;
      symbol?: string;
      interval?: string;
    }
  > => {
    return apiRequest.get('/data/klines', params);
  },

  /**
   * 获取加密货币符号列表
   * @param params 查询参数，包括type、exchange、filter、limit、offset等
   * @returns 加密货币符号列表
   */
  getCryptoSymbols: (params?: Record<string, unknown>): Promise<{
    symbols?: CryptoSymbol[];
    data?: { symbols?: CryptoSymbol[]; items?: CryptoSymbol[] };
    total?: number;
    offset?: number;
    limit?: number;
    exchange?: string;
  }> => {
    return apiRequest.get('/data/crypto/symbols', params);
  },

  /**
   * 获取数据采集页面的品种选项数据
   * @param params 查询参数，包括type和exchange
   * @returns 包含资产池和直接货币对数据的响应
   */
  getCollectionSymbols: (params?: Record<string, unknown>): Promise<{
    data_pools?: DataPoolRecord[];
    direct_symbols?: string[];
  }> => {
    return apiRequest.get('/data-pools/collection/symbols', params);
  },

  /**
   * 获取商品列表
   * @param params 查询参数，包括market_type、crypto_type、exchange、filter、limit、offset等
   * @returns 商品列表数据
   */
  getProducts: (params?: Record<string, unknown>): Promise<{ products: CryptoSymbol[] }> => {
    return apiRequest.get('/data/products', params);
  },

  /**
   * 检查K线数据质量
   * @param params 查询参数，包括symbol、interval、start、end等
   * @returns K线数据质量报告
   */
  checkKlineQuality: (params: Record<string, unknown>): Promise<KlineQualityReport> => {
    return apiRequest.get('/data/quality/kline', params);
  },

  /**
   * 获取K线重复记录详情
   * @param params 查询参数，包括symbol、interval、start、end等
   * @returns K线重复记录详情
   */
  getKlineDuplicates: (params: Record<string, unknown>) => {
    return apiRequest.get('/data/quality/kline/duplicates', params);
  },

  /**
   * 处理K线重复记录
   * @param params 查询参数，包括symbol、interval、strategy、group_key等
   * @returns 重复记录处理结果
   */
  resolveKlineDuplicates: (params: Record<string, unknown>) => {
    return apiRequest.post('/data/quality/kline/duplicates/resolve', undefined, { params });
  },

  /**
   * 获取数据质量检查的下拉选项数据
   * @param params 查询参数，包括symbol、market_type、crypto_type等
   * @returns 包含货币对和时间周期列表的数据
   */
  getQualityOptions: (params: Record<string, unknown>) => {
    return apiRequest.get('/data/quality/options', params);
  },

  // ==================== 数据池（自选组）API ====================

  /**
   * 获取所有数据池（自选组）
   * @param params 查询参数，包括type类型过滤
   * @returns 数据池列表
   */
  getDataPools: (params?: { type?: string }): Promise<
    DataPoolRecord[] | { data?: DataPoolRecord[]; pools?: DataPoolRecord[]; items?: DataPoolRecord[] }
  > => {
    return apiRequest.get('/data-pools/', params);
  },

  /**
   * 创建数据池（自选组）
   * @param data 数据池信息，包括name、type、description、color、tags
   * @returns 创建结果
   */
  createDataPool: (data: {
    name: string;
    type: string;
    description?: string;
    color?: string;
    tags?: string[];
  }): Promise<{ pool_id?: string | number }> => {
    return apiRequest.post('/data-pools/', data);
  },

  /**
   * 更新数据池（自选组）
   * @param poolId 数据池ID
   * @param data 更新信息
   * @returns 更新结果
   */
  updateDataPool: (
    poolId: number,
    data: {
      name?: string;
      type?: string;
      description?: string;
      color?: string;
      tags?: string[];
    }
  ): Promise<{ code?: number; message?: string }> => {
    return apiRequest.put(`/data-pools/${poolId}`, data);
  },

  /**
   * 删除数据池（自选组）
   * @param poolId 数据池ID
   * @returns 删除结果
   */
  deleteDataPool: (poolId: number) => {
    return apiRequest.delete(`/data-pools/${poolId}`);
  },

  /**
   * 获取数据池资产列表
   * @param poolId 数据池ID
   * @returns 资产列表
   */
  getDataPoolAssets: (poolId: number): Promise<string[] | { assets?: string[] }> => {
    return apiRequest.get(`/data-pools/${poolId}/assets`);
  },

  /**
   * 批量添加资产到数据池
   * @param poolId 数据池ID
   * @param data 资产列表和类型
   * @returns 添加结果
   */
  addDataPoolAssets: (
    poolId: number,
    data: {
      assets: string[];
      asset_type: string;
    }
  ) => {
    return apiRequest.post(`/data-pools/${poolId}/assets`, data);
  },

  // ==================== 市场数据 API ====================

  /**
   * 获取市场数据（24小时行情）
   * @param data 请求体，包含symbols数组、exchange、force_refresh
   * @returns 市场数据列表
   */
  getMarketData: (data: {
    symbols: string[];
    exchange?: string;
    force_refresh?: boolean;
  }): Promise<Array<Record<string, unknown>> | { data?: Array<Record<string, unknown>> }> => {
    return apiRequest.post('/data/crypto/market-data', data);
  },

  /**
   * 同步货币对列表
   * @param exchange 交易所名称
   * @returns 同步结果
   */
  syncSymbols: (exchange?: string) => {
    return apiRequest.post('/data/crypto/sync-symbols', null, { params: { exchange } });
  },

  /**
   * 获取任务的子任务详情列表
   * @param taskId 任务ID
   * @returns 子任务详情列表
   */
  getTaskDetails: (taskId: string): Promise<{ details?: TaskDetailItem[] }> => {
    return apiRequest.get(`/data/tasks/${taskId}/details`);
  },

  /**
   * 清理K线数据
   * @param params 清理参数，包括symbol、interval、start、end、clean_type等
   * @returns 清理结果
   */
  cleanKlineData: (params: {
    symbol: string;
    interval?: string;
    start?: string;
    end?: string;
    clean_type?: 'all' | 'duplicates' | 'invalid';
    market_type?: string;
    crypto_type?: string;
  }): Promise<{
    deleted_count?: number;
    symbol?: string;
    interval?: string;
    clean_type?: string;
    total_before?: number;
  }> => {
    return apiRequest.post<{ deleted_count?: number }>('/data/clean', undefined, { params });
  },
};
