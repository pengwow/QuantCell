import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios';
import { getAccessToken, updateAccessToken } from '../utils/tokenManager';

/**
 * API 响应类型
 */
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

/**
 * API 错误类型
 */
export class ApiError extends Error {
  code: number;
  
  constructor(code: number, message: string) {
    super(message);
    this.code = code;
    this.name = 'ApiError';
  }
}

/**
 * 配置 Axios 实例
 */
export const api: AxiosInstance = axios.create({
  baseURL: '/api', // 基础 URL，会被 Vite 代理转发到后端
  timeout: 30000, // 请求超时时间
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 请求拦截器
 */
api.interceptors.request.use(
  (config) => {
    // 添加认证令牌
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    // 处理请求错误
    console.error('请求错误:', error);
    return Promise.reject(error);
  }
);

/**
 * 响应拦截器
 */
api.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    // 检查是否有刷新的令牌
    const refreshedToken = response.headers['x-refreshed-token'];
    if (refreshedToken) {
      // 更新访问令牌
      updateAccessToken(refreshedToken);
    }
    
    const { code, message, data } = response.data;
    if (code === 0) {
      return data;
    } else {
      // 处理业务错误
      console.error('API 错误:', message);
      return Promise.reject(new ApiError(code, message));
    }
  },
  (error) => {
    // 处理网络错误
    console.error('网络错误:', error);
    return Promise.reject(error);
  }
);

/**
 * API 请求方法封装
 */
export const apiRequest = {
  /**
   * GET 请求
   * @param url 请求 URL
   * @param params 请求参数
   * @param config 请求配置
   * @returns 响应数据
   */
  get: <T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.get(url, { params, ...config }) as Promise<T>;
  },

  /**
   * POST 请求
   * @param url 请求 URL
   * @param data 请求数据
   * @param config 请求配置
   * @returns 响应数据
   */
  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.post(url, data, config) as Promise<T>;
  },

  /**
   * PUT 请求
   * @param url 请求 URL
   * @param data 请求数据
   * @param config 请求配置
   * @returns 响应数据
   */
  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.put(url, data, config) as Promise<T>;
  },

  /**
   * DELETE 请求
   * @param url 请求 URL
   * @param params 请求参数
   * @param config 请求配置
   * @returns 响应数据
   */
  delete: <T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.delete(url, { params, ...config }) as Promise<T>;
  },
};

/**
 * 策略相关 API
 */
export const strategyApi = {
  /**
   * 获取策略列表
   * @returns 策略列表数据
   */
  getStrategies: () => {
    return apiRequest.get('/strategy/list');
  },

  /**
   * 创建策略
   * @param data 策略数据
   * @returns 创建的策略数据
   */
  createStrategy: (data: any) => {
    return apiRequest.post('/strategy/create', data);
  },

  /**
   * 更新策略
   * @param id 策略 ID
   * @param data 策略数据
   * @returns 更新后的策略数据
   */
  updateStrategy: (id: string, data: any) => {
    return apiRequest.put(`/strategy/update/${id}`, data);
  },

  /**
   * 删除策略
   * @param id 策略 ID
   * @returns 删除结果
   */
  deleteStrategy: (id: string) => {
    return apiRequest.delete(`/strategy/${id}`);
  },

  /**
   * 切换策略状态
   * @param id 策略 ID
   * @param status 策略状态
   * @returns 切换结果
   */
  toggleStrategyStatus: (id: string, status: 'active' | 'inactive') => {
    return apiRequest.put(`/strategy/toggle/${id}`, { status });
  },

  /**
   * 获取策略执行统计
   * @returns 执行统计数据
   */
  getExecutionStats: () => {
    return apiRequest.get('/strategy/stats');
  },

  /**
 * 上传策略文件
 * @param data 策略数据，包括策略名称和文件内容
 * @returns 上传结果
 */
uploadStrategyFile: (data: any) => {
  return apiRequest.post('/strategy/upload', data);
},

/**
 * 获取策略详情
 * @param strategy_name 策略名称
 * @returns 策略详情数据
 */
getStrategyDetail: (strategy_name: string) => {
  return apiRequest.post('/strategy/detail', { strategy_name });
},
};

/**
 * 数据管理相关 API
 */
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
    return apiRequest.get('/data/quality/kline', { params });
  },
};

/**
 * 配置相关 API
 */
export const configApi = {
  /**
   * 获取配置
   * @returns 配置数据
   */
  getConfig: () => {
    return apiRequest.get('/config/');
  },

  /**
   * 更新配置
   * @param data 配置数据
   * @returns 更新结果
   */
  updateConfig: (data: any) => {
    return apiRequest.post('/config/batch', data);
  },

  /**
   * 更新插件配置
   * @param pluginName 插件名称
   * @param data 配置数据
   * @returns 更新结果
   */
  updatePluginConfig: (pluginName: string, data: any) => {
    // 为每个配置项添加 plugin 字段
    const pluginConfigData = data.map((item: any) => ({
      ...item,
      plugin: pluginName
    }));
    return apiRequest.post('/config/batch', pluginConfigData);
  },

  /**
   * 获取插件配置
   * @param pluginName 插件名称
   * @returns 插件配置数据
   */
  getPluginConfig: (pluginName: string) => {
    return apiRequest.get(`/config/plugin/${pluginName}`);
  }
};

/**
 * 数据池相关 API
 */
export const dataPoolApi = {
  /**
   * 获取数据池列表
   * @param type 数据池类型
   * @returns 数据池列表数据
   */
  getDataPools: (type: string) => {
    return apiRequest.get('/data-pools/', { params: { type } });
  },

  /**
   * 创建数据池
   * @param data 数据池数据
   * @returns 创建的数据池数据
   */
  createDataPool: (data: any) => {
    return apiRequest.post('/data-pools/', data);
  },

  /**
   * 更新数据池
   * @param id 数据池 ID
   * @param data 数据池数据
   * @returns 更新后的数据池数据
   */
  updateDataPool: (id: string, data: any) => {
    return apiRequest.put(`/data-pools/${id}`, data);
  },

  /**
   * 删除数据池
   * @param id 数据池 ID
   * @param type 数据池类型
   * @returns 删除结果
   */
  deleteDataPool: (id: string, type: string) => {
    return apiRequest.delete(`/data-pools/${id}`, { params: { type } });
  },

  /**
   * 获取数据池详情
   * @param id 数据池 ID
   * @param type 数据池类型
   * @returns 数据池详情数据
   */
  getDataPoolDetail: (id: string, type: string) => {
    return apiRequest.get(`/data-pools/${id}`, { params: { type } });
  },

  /**
   * 获取数据池包含的资产
   * @param poolId 数据池 ID
   * @returns 资产列表
   */
  getPoolAssets: (poolId: string) => {
    return apiRequest.get(`/data-pools/${poolId}/assets`);
  },

  /**
   * 向数据池添加资产
   * @param poolId 数据池 ID
   * @param data 资产添加请求，包含assets列表和asset_type字段
   * @returns 添加结果
   */
  addPoolAssets: (poolId: string, data: any) => {
    return apiRequest.post(`/data-pools/${poolId}/assets`, data);
  },
};

/**
 * 定时任务相关 API
 */
export const scheduledTaskApi = {
  /**
   * 获取定时任务列表
   * @returns 定时任务列表数据
   */
  getTasks: () => {
    return apiRequest.get('/scheduled-tasks');
  },

  /**
   * 获取定时任务详情
   * @param taskId 任务ID
   * @returns 定时任务详情数据
   */
  getTask: (taskId: string) => {
    return apiRequest.get(`/scheduled-tasks/${taskId}`);
  },

  /**
   * 创建定时任务
   * @param data 任务数据
   * @returns 创建的任务数据
   */
  createTask: (data: any) => {
    return apiRequest.post('/scheduled-tasks', data);
  },

  /**
   * 更新定时任务
   * @param taskId 任务ID
   * @param data 任务数据
   * @returns 更新后的任务数据
   */
  updateTask: (taskId: string, data: any) => {
    return apiRequest.put(`/scheduled-tasks/${taskId}`, data);
  },

  /**
   * 删除定时任务
   * @param taskId 任务ID
   * @returns 删除结果
   */
  deleteTask: (taskId: string) => {
    return apiRequest.delete(`/scheduled-tasks/${taskId}`);
  },

  /**
   * 运行定时任务
   * @param taskId 任务ID
   * @returns 运行结果
   */
  runTask: (taskId: string) => {
    return apiRequest.post(`/scheduled-tasks/${taskId}/run`);
  },

  /**
   * 暂停定时任务
   * @param taskId 任务ID
   * @returns 暂停结果
   */
  pauseTask: (taskId: string) => {
    return apiRequest.post(`/scheduled-tasks/${taskId}/pause`);
  },

  /**
   * 恢复定时任务
   * @param taskId 任务ID
   * @returns 恢复结果
   */
  resumeTask: (taskId: string) => {
    return apiRequest.post(`/scheduled-tasks/${taskId}/resume`);
  },
};

/**
 * 回测相关 API
 */
export const backtestApi = {
  /**
   * 获取回测结果列表
   * @returns 回测结果列表数据
   */
  getBacktestList: () => {
    return apiRequest.get('/backtest/list');
  },

  /**
   * 获取策略列表
   * @returns 策略列表数据
   */
  getStrategies: () => {
    return apiRequest.get('/strategy/list');
  },

  /**
   * 执行回测
   * @param data 回测数据，包括策略配置和回测配置
   * @returns 回测结果数据
   */
  runBacktest: (data: any) => {
    return apiRequest.post('/backtest/run', data);
  },

  /**
   * 分析回测结果
   * @param backtestId 回测ID
   * @returns 回测分析结果
   */
  analyzeBacktest: (backtestId: string) => {
    return apiRequest.post('/backtest/analyze', { backtest_id: backtestId });
  },

  /**
   * 获取回测结果详情
   * @param backtestId 回测ID
   * @returns 回测结果详情
   */
  getBacktestDetail: (backtestId: string) => {
    return apiRequest.get(`/backtest/${backtestId}`);
  },

  /**
   * 删除回测结果
   * @param backtestId 回测ID
   * @returns 删除结果
   */
  deleteBacktest: (backtestId: string) => {
    return apiRequest.delete(`/backtest/delete/${backtestId}`);
  },

  /**
   * 上传策略文件
   * @param data 策略文件数据，包括策略名称和文件内容
   * @returns 上传结果
   */
  uploadStrategy: (data: any) => {
    return apiRequest.post('/backtest/strategy', data);
  },

  /**
   * 创建策略配置
   * @param data 策略配置数据，包括策略名称和参数
   * @returns 创建的策略配置
   */
  createStrategyConfig: (data: any) => {
    return apiRequest.post('/backtest/strategy/config', data);
  },

  /**
   * 获取回测回放数据
   * @param backtestId 回测ID
   * @returns 回放数据
   */
  getReplayData: (backtestId: string) => {
    return apiRequest.get(`/backtest/${backtestId}/replay`);
  },
};

export default api;
