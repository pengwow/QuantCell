import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios';

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
    // 可以在这里添加认证信息
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
    return apiRequest.delete(`/strategy/delete/${id}`);
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
};

export default api;
