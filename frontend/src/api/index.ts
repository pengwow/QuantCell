import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios';
import { getAccessToken, updateAccessToken } from '../utils/tokenManager';
import type { LogQueryParams, LogQueryResponse, SystemMetrics } from '../pages/setting/types';

// ============================================
// 策略生成相关类型定义
// ============================================

/**
 * 策略生成请求
 */
export interface StrategyGenerateRequest {
  requirement: string;
  model_id?: string;
  model_name?: string;
  temperature?: number;
  template_vars?: Record<string, any>;
}

/**
 * 策略生成响应
 */
export interface StrategyGenerateResponse {
  code: string;
  explanation: string;
  model_used: string;
  tokens_used: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

/**
 * 思维链步骤状态
 */
export interface ThinkingChainStep {
  title: string;
  description: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
}

/**
 * 思维链事件数据
 */
export interface ThinkingChainEventData {
  current_step: number;
  total_steps: number;
  step_title: string;
  step_description?: string;
  step_key?: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  progress: number;
  message?: string;
}

/**
 * 流式策略生成响应
 * 优化后：仅保留思维链进度和最终结果，移除content事件
 */
export interface StrategyGenerateStreamResponse {
  type: 'thinking_chain' | 'done' | 'error';
  code?: string;
  raw_content?: string;
  data?: ThinkingChainEventData;
  metadata?: {
    request_id?: string;
    model?: string;
    elapsed_time?: number;
    chunk_count?: number;
    tokens_used?: {
      prompt_tokens: number;
      completion_tokens: number;
      total_tokens: number;
    };
    generation_time?: number;
  };
  error?: string;
  error_code?: string;
}

/**
 * 代码验证请求
 */
export interface CodeValidationRequest {
  code: string;
  language?: string;
}

/**
 * 代码验证响应
 */
export interface CodeValidationResponse {
  valid: boolean;
  errors: Array<{
    type: string;
    line: number;
    column: number;
    message: string;
  }>;
  warnings: Array<{
    type: string;
    line: number;
    message: string;
  }>;
}

/**
 * 策略模板
 */
export interface StrategyTemplate {
  id: string;
  name: string;
  category: string;
  description: string;
  parameters: Array<{
    name: string;
    type: string;
    default: any;
    description: string;
  }>;
  tags?: string[];
}

/**
 * 策略模板分类
 */
export interface StrategyTemplateCategory {
  id: string;
  name: string;
  description: string;
}

/**
 * 策略历史记录
 */
export interface StrategyHistoryItem {
  id: string;
  title: string;
  requirement: string;
  code: string;
  explanation: string;
  model_id: string;
  temperature: number;
  tokens_used: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  generation_time: number;
  is_valid: boolean;
  tags: string[];
  created_at: string;
  updated_at: string;
}

/**
 * 性能统计
 */
export interface PerformanceStats {
  total_requests: number;
  success_rate: number;
  avg_generation_time: number;
  avg_tokens_used: number;
  by_model: Record<string, {
    requests: number;
    success_rate: number;
    avg_time: number;
  }>;
  by_date: Record<string, {
    requests: number;
    success_rate: number;
  }>;
}

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

    // 处理401未授权错误
    if (error.response?.status === 401) {
      // 清除token并跳转到登录页
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
      return Promise.reject(new ApiError(401, '登录已过期，请重新登录'));
    }

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

  parseStrategy: (strategy_name: string, file_content: string) => {
    return apiRequest.post('/strategy/parse', { strategy_name, file_content });
  },

  /**
   * AI生成策略
   * @param data 生成请求数据
   */
  generateStrategy: (data: any) => {
    return apiRequest.post('/strategy/generate', data);
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
    return apiRequest.get<LogQueryResponse>('/system/logs', params);
  },

  /**
   * 获取系统指标（连接状态、CPU、内存、磁盘等）
   */
  getSystemMetrics: (): Promise<SystemMetrics> => {
    return apiRequest.get<SystemMetrics>('/system/metrics');
  },
};

/**
 * 通知设置相关 API
 */
export const notificationApi = {
  /**
   * 获取通知渠道配置
   */
  getChannels: () => {
    return apiRequest.get('/notifications/channels');
  },

  /**
   * 保存通知渠道配置
   * @param channels 通知渠道配置列表
   */
  saveChannels: (channels: any[]) => {
    return apiRequest.post('/notifications/channels', channels);
  },

  /**
   * 测试通知渠道
   * @param channelId 渠道ID
   * @param config 渠道配置
   */
  testChannel: (channelId: string, config: any) => {
    return apiRequest.post('/notifications/test', { channel_id: channelId, config });
  },
};

/**
 * AI模型配置相关 API
 */
export const aiModelApi = {
  /**
   * 获取AI模型配置列表
   */
  getModels: () => {
    return apiRequest.get('/ai-models/');
  },

  /**
   * 创建AI模型配置
   * @param data 模型配置数据
   */
  createModel: (data: any) => {
    return apiRequest.post('/ai-models/', data);
  },

  /**
   * 更新AI模型配置
   * @param id 模型ID
   * @param data 模型配置数据
   */
  updateModel: (id: string, data: any) => {
    return apiRequest.put(`/ai-models/${id}`, data);
  },

  /**
   * 删除AI模型配置
   * @param id 模型ID
   */
  deleteModel: (id: string) => {
    return apiRequest.delete(`/ai-models/${id}`);
  },

  /**
   * 检查模型可用性
   * @param data 检查请求数据
   */
  checkAvailability: (data: any) => {
    return apiRequest.post('/ai-models/check', data);
  },

  /**
   * 获取支持的厂商列表
   */
  getProviders: () => {
    return apiRequest.get('/ai-models/providers');
  },

  /**
   * 获取默认提供商的模型列表
   * 返回默认提供商中 is_enabled 为 true 的模型列表
   */
  getDefaultProviderModels: () => {
    return apiRequest.get('/ai-models/default-provider/models');
  },

  // ============================================
  // 策略生成相关 API
  // ============================================

  /**
   * 流式生成策略（SSE）
   * @param data 生成请求数据
   * @returns EventSource 实例
   */
  generateStrategy: (_data: StrategyGenerateRequest): EventSource => {
    const token = getAccessToken();
    const url = `/api/ai-models/strategy/generate?token=${token}`;

    // 使用 POST 方法创建 EventSource，需要通过 fetch 实现
    const eventSource = new EventSource(url);

    // 发送请求数据（需要在连接建立后发送）
    // 注意：标准 EventSource 不支持 POST，这里使用查询参数传递简单数据
    // 复杂数据建议使用 generateStrategyStream 方法
    return eventSource;
  },

  /**
   * 使用 fetch + ReadableStream 实现流式生成策略（优化版）
   * 仅保留思维链进度和最终结果，移除content事件流式传输
   * @param data 生成请求数据
   * @param onThinkingChain 思维链状态更新回调
   * @param onDone 生成完成回调
   * @param onError 错误回调
   * @returns 取消函数
   */
  generateStrategyStream: (
    data: StrategyGenerateRequest,
    onThinkingChain?: (data: ThinkingChainEventData) => void,
    onDone?: (result: { code?: string; raw_content?: string; metadata?: any }) => void,
    onError?: (error: Error) => void
  ): (() => void) => {
    const token = getAccessToken();
    const controller = new AbortController();

    // 使用 Promise 包装 fetch 调用
    const fetchPromise = fetch('/api/ai-models/strategy/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(data),
      signal: controller.signal,
    });

    // 立即开始处理 fetch
    fetchPromise
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('Response body is null');
        }

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const jsonData = JSON.parse(line.slice(6)) as StrategyGenerateStreamResponse;
                
                // 处理思维链事件
                if (jsonData.type === 'thinking_chain' && jsonData.data && onThinkingChain) {
                  onThinkingChain(jsonData.data);
                }
                
                // 处理完成事件
                if (jsonData.type === 'done' && onDone) {
                  onDone({
                    code: jsonData.code,
                    raw_content: jsonData.raw_content,
                    metadata: jsonData.metadata,
                  });
                }
                
                // 处理错误事件
                if (jsonData.type === 'error' && onError) {
                  onError(new Error(jsonData.error || '生成失败'));
                }
              } catch (e) {
                console.error('解析SSE数据失败:', e);
              }
            }
          }
        }
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          onError?.(error);
        }
      });

    // 返回取消函数
    return () => controller.abort();
  },

  /**
   * 同步生成策略
   * @param data 生成请求数据
   * @returns 生成结果
   */
  generateStrategySync: (data: StrategyGenerateRequest): Promise<StrategyGenerateResponse> => {
    return apiRequest.post('/ai-models/strategy/generate-sync', data);
  },

  /**
   * 预加载思维链配置
   * 用于前端页面打开时快速获取激活的思维链配置
   * @param chainType 思维链类型
   * @returns 思维链配置
   */
  preloadThinkingChain: (chainType: 'strategy_generation' | 'indicator_generation' = 'strategy_generation'): Promise<{
    id: string;
    chain_type: string;
    name: string;
    description?: string;
    steps: Array<{ title: string; description?: string }>;
    is_active: boolean;
  } | null> => {
    return apiRequest.get(`/ai-models/strategy/thinking-chains/preload`, { chain_type: chainType });
  },

  /**
   * 验证代码
   * @param data 验证请求数据
   * @returns 验证结果
   */
  validateCode: (data: CodeValidationRequest): Promise<CodeValidationResponse> => {
    return apiRequest.post('/ai-models/strategy/validate-code', data);
  },

  /**
   * 获取策略模板列表
   * @param category 分类ID（可选）
   * @returns 模板列表
   */
  getTemplates: (category?: string): Promise<StrategyTemplate[]> => {
    return apiRequest.get('/ai-models/strategy/templates', { category });
  },

  /**
   * 获取策略模板分类
   * @returns 分类列表
   */
  getTemplateCategories: (): Promise<StrategyTemplateCategory[]> => {
    return apiRequest.get('/ai-models/strategy/templates/categories');
  },

  /**
   * 获取单个策略模板
   * @param id 模板ID
   * @returns 模板详情
   */
  getTemplateById: (id: string): Promise<StrategyTemplate> => {
    return apiRequest.get(`/ai-models/strategy/templates/${id}`);
  },

  /**
   * 基于模板生成策略
   * @param templateId 模板ID
   * @param params 模板参数
   * @returns 生成结果
   */
  generateFromTemplate: (
    templateId: string,
    params: Record<string, any>
  ): Promise<StrategyGenerateResponse> => {
    return apiRequest.post('/ai-models/strategy/generate-from-template', {
      template_id: templateId,
      parameters: params,
    });
  },

  /**
   * 获取策略生成历史记录
   * @param page 页码
   * @param pageSize 每页数量
   * @returns 历史记录列表
   */
  getHistory: (page?: number, pageSize?: number): Promise<{
    items: StrategyHistoryItem[];
    total: number;
    page: number;
    page_size: number;
  }> => {
    return apiRequest.get('/ai-models/strategy/history', { page, page_size: pageSize });
  },

  /**
   * 获取单个历史记录
   * @param id 历史记录ID
   * @returns 历史记录详情
   */
  getHistoryById: (id: string): Promise<StrategyHistoryItem> => {
    return apiRequest.get(`/ai-models/strategy/history/${id}`);
  },

  /**
   * 删除历史记录
   * @param id 历史记录ID
   */
  deleteHistory: (id: string): Promise<void> => {
    return apiRequest.delete(`/ai-models/strategy/history/${id}`);
  },

  /**
   * 基于历史记录重新生成
   * @param id 历史记录ID
   * @param newRequirement 新的需求描述（可选）
   * @returns 生成结果
   */
  regenerateFromHistory: (
    id: string,
    newRequirement?: string
  ): Promise<StrategyGenerateResponse> => {
    return apiRequest.post(`/ai-models/strategy/history/${id}/regenerate`, {
      new_requirement: newRequirement,
    });
  },

  /**
   * 获取性能统计
   * @returns 性能统计数据
   */
  getPerformanceStats: (): Promise<PerformanceStats> => {
    return apiRequest.get('/ai-models/strategy/stats');
  },
};

/**
 * 交易所配置相关 API
 * 使用系统配置表存储，name="exchange"，key=交易所英文名称
 */
export const exchangeConfigApi = {
  /**
   * 获取交易所配置列表
   */
  getConfigs: () => {
    return apiRequest.get('/exchange-configs/');
  },

  /**
   * 创建交易所配置
   * @param data 交易所配置数据
   */
  createConfig: (data: any) => {
    return apiRequest.post('/exchange-configs/', data);
  },

  /**
   * 更新交易所配置
   * @param key 交易所英文名称（如 "binance", "okx"）
   * @param data 交易所配置数据
   */
  updateConfig: (key: string, data: any) => {
    return apiRequest.put(`/exchange-configs/${key}`, data);
  },

  /**
   * 删除交易所配置
   * @param key 交易所英文名称（如 "binance", "okx"）
   */
  deleteConfig: (key: string) => {
    return apiRequest.delete(`/exchange-configs/${key}`);
  },

  /**
   * 获取支持的交易所列表
   */
  getExchanges: () => {
    return apiRequest.get('/exchange-configs/exchanges');
  },
};

/**
 * 交易所连接测试相关 API
 */
export const exchangeApi = {
  /**
   * 测试交易所连接
   * @param data 连接测试参数
   */
  testConnection: (data: {
    exchange_name: string;
    api_key?: string;
    secret_key?: string;
    api_passphrase?: string;
    proxy_url?: string;
    trading_mode?: string;
    testnet?: boolean;
  }) => {
    return apiRequest.post<{
      success: boolean;
      status: string;
      message: string;
      response_time_ms?: number;
      details?: any;
    }>('/exchanges/test-connection', data);
  },

  /**
   * 获取支持的交易所列表
   */
  getSupportedExchanges: () => {
    return apiRequest.get<{ exchanges: string[] }>('/exchanges/supported');
  },
};

export default api;
