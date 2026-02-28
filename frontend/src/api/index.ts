import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios';
import { getAccessToken, updateAccessToken } from '../utils/tokenManager';
import type { LogQueryParams, LogQueryResponse, SystemMetrics } from '../pages/setting/types';

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
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * 请求拦截器
 */
api.interceptors.request.use(
  (config) => {
    const token = getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    console.error('请求错误:', error);
    return Promise.reject(error);
  }
);

/**
 * 响应拦截器
 */
api.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const refreshedToken = response.headers['x-refreshed-token'];
    if (refreshedToken) {
      updateAccessToken(refreshedToken);
    }

    const { code, message, data } = response.data;
    if (code === 0) {
      return data;
    } else {
      console.error('API 错误:', message);
      return Promise.reject(new ApiError(code, message));
    }
  },
  (error) => {
    console.error('网络错误:', error);
    return Promise.reject(error);
  }
);

/**
 * API 请求方法封装
 */
export const apiRequest = {
  get: <T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.get(url, { params, ...config }) as Promise<T>;
  },

  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.post(url, data, config) as Promise<T>;
  },

  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.put(url, data, config) as Promise<T>;
  },

  patch: <T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.patch(url, data, config) as Promise<T>;
  },

  delete: <T = any>(url: string, params?: any, config?: AxiosRequestConfig): Promise<T> => {
    return api.delete(url, { params, ...config }) as Promise<T>;
  },
};

/**
 * 策略相关 API
 */
export const strategyApi = {
  getStrategies: () => {
    return apiRequest.get('/strategy/list');
  },

  createStrategy: (data: any) => {
    return apiRequest.post('/strategy/create', data);
  },

  updateStrategy: (id: string, data: any) => {
    return apiRequest.put(`/strategy/update/${id}`, data);
  },

  deleteStrategy: (id: string) => {
    return apiRequest.delete(`/strategy/${id}`);
  },

  toggleStrategyStatus: (id: string, status: 'active' | 'inactive') => {
    return apiRequest.put(`/strategy/toggle/${id}`, { status });
  },

  getExecutionStats: () => {
    return apiRequest.get('/strategy/stats');
  },

  uploadStrategyFile: (data: any) => {
    return apiRequest.post('/strategy/upload', data);
  },

  getStrategyDetail: (strategy_name: string) => {
    return apiRequest.post('/strategy/detail', { strategy_name });
  },
};

/**
 * 数据管理相关 API
 */
export const dataApi = {
  getCryptoData: () => {
    return apiRequest.get('/data/crypto');
  },

  getStockData: () => {
    return apiRequest.get('/data/stock');
  },

  startImport: (data: any) => {
    return apiRequest.post('/data/import', data);
  },

  startQualityCheck: (data: any) => {
    return apiRequest.post('/data/quality/check', data);
  },

  generateVisualization: (data: any) => {
    return apiRequest.post('/data/visualization/generate', data);
  },

  getTasks: (params: any) => {
    return apiRequest.get('/data/tasks', params);
  },

  getTaskStatus: (taskId: string) => {
    return apiRequest.get(`/data/task/${taskId}`);
  },

  downloadCryptoData: (data: any) => {
    return apiRequest.post('/data/download/crypto', data);
  },

  getServiceStatus: () => {
    return apiRequest.get('/data/status');
  },

  getKlines: (params: any) => {
    return apiRequest.get('/data/klines', params);
  },

  getCryptoSymbols: (params?: any) => {
    return apiRequest.get('/data/crypto/symbols', params);
  },

  getCollectionSymbols: (params?: any) => {
    return apiRequest.get('/data-pools/collection/symbols', params);
  },

  getProducts: (params?: any) => {
    return apiRequest.get('/data/products', params);
  },

  checkKlineQuality: (params: any) => {
    return apiRequest.get('/data/quality/kline', params);
  },

  getKlineDuplicates: (params: any) => {
    return apiRequest.get('/data/quality/kline/duplicates', params);
  },

  resolveKlineDuplicates: (params: any) => {
    return apiRequest.post('/data/quality/kline/duplicates/resolve', undefined, { params });
  },

  getQualityOptions: (params: any) => {
    return apiRequest.get('/data/quality/options', params);
  },
};

/**
 * 配置相关 API
 */
export const configApi = {
  getConfig: () => {
    return apiRequest.get('/config/');
  },

  updateConfig: (data: any) => {
    return apiRequest.post('/config/batch', data);
  },

  updatePluginConfig: (pluginName: string, data: any) => {
    const pluginConfigData = data.map((item: any) => ({
      ...item,
      plugin: pluginName
    }));
    return apiRequest.post('/config/batch', pluginConfigData);
  },

  getPluginConfig: (pluginName: string) => {
    return apiRequest.get(`/config/plugin/${pluginName}`);
  }
};

/**
 * 数据池相关 API
 */
export const dataPoolApi = {
  getDataPools: (type: string) => {
    return apiRequest.get('/data-pools/', { type });
  },

  createDataPool: (data: any) => {
    return apiRequest.post('/data-pools/', data);
  },

  updateDataPool: (id: string, data: any) => {
    return apiRequest.put(`/data-pools/${id}`, data);
  },

  deleteDataPool: (id: string, type: string) => {
    return apiRequest.delete(`/data-pools/${id}`, { params: { type } });
  },

  getDataPoolDetail: (id: string, type: string) => {
    return apiRequest.get(`/data-pools/${id}`, { params: { type } });
  },

  getPoolAssets: (poolId: string) => {
    return apiRequest.get(`/data-pools/${poolId}/assets`);
  },

  addPoolAssets: (poolId: string, data: any) => {
    return apiRequest.post(`/data-pools/${poolId}/assets`, data);
  },
};

/**
 * 定时任务相关 API
 */
export const scheduledTaskApi = {
  getTasks: () => {
    return apiRequest.get('/scheduled-tasks');
  },

  getTask: (taskId: string) => {
    return apiRequest.get(`/scheduled-tasks/${taskId}`);
  },

  createTask: (data: any) => {
    return apiRequest.post('/scheduled-tasks', data);
  },

  updateTask: (taskId: string, data: any) => {
    return apiRequest.put(`/scheduled-tasks/${taskId}`, data);
  },

  deleteTask: (taskId: string) => {
    return apiRequest.delete(`/scheduled-tasks/${taskId}`);
  },

  runTask: (taskId: string) => {
    return apiRequest.post(`/scheduled-tasks/${taskId}/run`);
  },

  pauseTask: (taskId: string) => {
    return apiRequest.post(`/scheduled-tasks/${taskId}/pause`);
  },

  resumeTask: (taskId: string) => {
    return apiRequest.post(`/scheduled-tasks/${taskId}/resume`);
  },
};

/**
 * 回测相关 API
 */
export const backtestApi = {
  getBacktestList: () => {
    return apiRequest.get('/backtest/list');
  },

  getStrategies: () => {
    return apiRequest.get('/strategy/list');
  },

  runBacktest: (data: any, signal?: AbortSignal) => {
    return apiRequest.post('/backtest/run', data, { timeout: 0, signal });
  },

  stopBacktest: (taskId: string) => {
    return apiRequest.post('/backtest/stop', { task_id: taskId });
  },

  analyzeBacktest: (backtestId: string) => {
    return apiRequest.post('/backtest/analyze', { backtest_id: backtestId });
  },

  getBacktestDetail: (backtestId: string) => {
    return apiRequest.get(`/backtest/${backtestId}`);
  },

  deleteBacktest: (backtestId: string) => {
    return apiRequest.delete(`/backtest/delete/${backtestId}`);
  },

  uploadStrategy: (data: any) => {
    return apiRequest.post('/backtest/strategy', data);
  },

  createStrategyConfig: (data: any) => {
    return apiRequest.post('/backtest/strategy/config', data);
  },

  getReplayData: (backtestId: string, symbol?: string) => {
    return apiRequest.get(`/backtest/${backtestId}/replay`, { symbol });
  },

  getBacktestSymbols: (backtestId: string) => {
    return apiRequest.get(`/backtest/${backtestId}/symbols`);
  },
};

/**
 * 技术指标相关 API
 */
export const indicatorApi = {
  getIndicators: () => {
    return apiRequest.get('/indicators');
  },

  getIndicator: (id: number) => {
    return apiRequest.get(`/indicators/${id}`);
  },

  createIndicator: (data: any) => {
    return apiRequest.post('/indicators', data);
  },

  updateIndicator: (id: number, data: any) => {
    return apiRequest.put(`/indicators/${id}`, data);
  },

  deleteIndicator: (id: number) => {
    return apiRequest.delete(`/indicators/${id}`);
  },

  verifyCode: (code: string) => {
    return apiRequest.post('/indicators/verify', { code });
  },

  aiGenerate: (prompt: string, existingCode?: string) => {
    return apiRequest.post('/indicators/ai-generate', { prompt, existing_code: existingCode });
  },

  getIndicatorParams: (id: number) => {
    return apiRequest.get(`/indicators/${id}/params`);
  },
};

/**
 * 系统相关 API
 */
export const systemApi = {
  /**
   * 获取系统日志
   * @param params 查询参数
   */
  getLogs: (params?: LogQueryParams): Promise<LogQueryResponse> => {
    return apiRequest.get('/system/logs', params);
  },

  /**
   * 获取系统指标（连接状态、CPU、内存、磁盘等）
   */
  getSystemMetrics: (): Promise<SystemMetrics> => {
    return apiRequest.get('/system/metrics');
  },
};

export default api;
