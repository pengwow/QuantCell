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
};
