/**
 * 数据管理相关 API
 * 从旧版本迁移过来
 */
import { apiRequest } from './index';

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
  startImport: (data: any) => {
    return apiRequest.post('/data/import', data);
  },

  /**
   * 开始数据质量检查
   * @param data 检查数据
   * @returns 检查结果
   */
  startQualityCheck: (data: any) => {
    return apiRequest.post('/data/quality/check', data);
  },

  /**
   * 生成数据可视化图表
   * @param data 图表数据
   * @returns 图表 URL
   */
  generateVisualization: (data: any) => {
    return apiRequest.post('/data/visualization/generate', data);
  },

  /**
   * 获取数据采集任务列表
   * @param params 查询参数
   * @returns 任务列表
   */
  getTasks: (params: any) => {
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
  downloadCryptoData: (data: any) => {
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
  getKlines: (params: any) => {
    return apiRequest.get('/data/klines', params);
  },

  /**
   * 获取加密货币符号列表
   * @param params 查询参数，包括type、exchange、filter、limit、offset等
   * @returns 加密货币符号列表
   */
  getCryptoSymbols: (params?: any) => {
    return apiRequest.get('/data/crypto/symbols', params);
  },

  /**
   * 获取数据采集页面的品种选项数据
   * @param params 查询参数，包括type和exchange
   * @returns 包含资产池和直接货币对数据的响应
   */
  getCollectionSymbols: (params?: any) => {
    return apiRequest.get('/data-pools/collection/symbols', params);
  },

  /**
   * 获取商品列表
   * @param params 查询参数，包括market_type、crypto_type、exchange、filter、limit、offset等
   * @returns 商品列表数据
   */
  getProducts: (params?: any) => {
    return apiRequest.get('/data/products', params);
  },

  /**
   * 检查K线数据质量
   * @param params 查询参数，包括symbol、interval、start、end等
   * @returns K线数据质量报告
   */
  checkKlineQuality: (params: any) => {
    return apiRequest.get('/data/quality/kline', params);
  },

  /**
   * 获取K线重复记录详情
   * @param params 查询参数，包括symbol、interval、start、end等
   * @returns K线重复记录详情
   */
  getKlineDuplicates: (params: any) => {
    return apiRequest.get('/data/quality/kline/duplicates', params);
  },

  /**
   * 处理K线重复记录
   * @param params 查询参数，包括symbol、interval、strategy、group_key等
   * @returns 重复记录处理结果
   */
  resolveKlineDuplicates: (params: any) => {
    return apiRequest.post('/data/quality/kline/duplicates/resolve', undefined, { params });
  },

  /**
   * 获取数据质量检查的下拉选项数据
   * @param params 查询参数，包括symbol、market_type、crypto_type等
   * @returns 包含货币对和时间周期列表的数据
   */
  getQualityOptions: (params: any) => {
    return apiRequest.get('/data/quality/options', params);
  },

  // ==================== 数据池（自选组）API ====================

  /**
   * 获取所有数据池（自选组）
   * @param params 查询参数，包括type类型过滤
   * @returns 数据池列表
   */
  getDataPools: (params?: { type?: string }) => {
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
  }) => {
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
  ) => {
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
  getDataPoolAssets: (poolId: number) => {
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
  }) => {
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
  getTaskDetails: (taskId: string) => {
    return apiRequest.get(`/data/tasks/${taskId}/details`);
  },
};
