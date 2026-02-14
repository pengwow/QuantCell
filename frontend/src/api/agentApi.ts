/**
 * Agent API调用模块
 * 
 * 与后端Worker模块API规范保持一致
 * 实现完整的错误处理和数据验证
 */

import type {
  Agent,
  AgentListResponse,
  CreateAgentRequest,
  UpdateAgentRequest,
  UpdateAgentConfigRequest,
  CloneAgentRequest,
  BatchOperationRequest,
  BatchOperationResponse,
  AgentStatusResponse,
  HealthCheckResponse,
  AgentMetrics,
  AgentLog,
  AgentPerformance,
  AgentTrade,
  StrategyDeployRequest,
  StrategyParameter,
  UpdateStrategyParametersRequest,
  PositionInfo,
  OrderInfo,
  ApiResponse,
  AgentFilterParams,
  LogQueryParams,
  TradeQueryParams,
  MetricsHistoryParams,
  TradingSignal
} from '../types/agent';

// API基础URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

// 请求超时时间（毫秒）
const REQUEST_TIMEOUT = 30000;

// 错误码映射
const ErrorCodeMap: Record<number, string> = {
  400: '请求参数错误',
  401: '未授权，请重新登录',
  403: '权限不足',
  404: '资源不存在',
  409: '资源冲突',
  422: '请求格式错误',
  429: '请求过于频繁',
  500: '服务器内部错误',
  502: '网关错误',
  503: '服务不可用',
  504: '网关超时'
};

// 自定义API错误类
export class ApiError extends Error {
  code: number;
  data?: any;

  constructor(message: string, code: number, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.data = data;
  }
}

// 网络错误类
export class NetworkError extends Error {
  constructor(message: string = '网络连接失败') {
    super(message);
    this.name = 'NetworkError';
  }
}

// 超时错误类
export class TimeoutError extends Error {
  constructor(message: string = '请求超时') {
    super(message);
    this.name = 'TimeoutError';
  }
}

// 获取认证Token
const getAuthToken = (): string | null => {
  return localStorage.getItem('token');
};

// 构建请求头
const buildHeaders = (): HeadersInit => {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  
  const token = getAuthToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  return headers;
};

// 带超时的fetch封装
const fetchWithTimeout = async (
  url: string,
  options: RequestInit,
  timeout: number = REQUEST_TIMEOUT
): Promise<Response> => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new TimeoutError();
      }
      throw new NetworkError(error.message);
    }
    throw error;
  }
};

// 处理API响应
const handleResponse = async <T>(response: Response): Promise<T> => {
  // 检查HTTP状态码
  if (!response.ok) {
    const errorMessage = ErrorCodeMap[response.status] || `HTTP错误: ${response.status}`;
    throw new ApiError(errorMessage, response.status);
  }
  
  // 解析响应数据
  const data: ApiResponse<T> = await response.json();
  
  // 检查业务状态码
  if (data.code !== 0) {
    throw new ApiError(data.message || '请求失败', data.code, data.data);
  }
  
  return data.data as T;
};

// 基础请求函数
const request = async <T>(
  method: string,
  endpoint: string,
  body?: any,
  params?: Record<string, any>
): Promise<T> => {
  // 构建URL
  let url = `${API_BASE_URL}${endpoint}`;
  if (params) {
    const queryParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        queryParams.append(key, String(value));
      }
    });
    const queryString = queryParams.toString();
    if (queryString) {
      url += `?${queryString}`;
    }
  }
  
  // 构建请求选项
  const options: RequestInit = {
    method,
    headers: buildHeaders()
  };
  
  if (body) {
    options.body = JSON.stringify(body);
  }
  
  // 发送请求
  const response = await fetchWithTimeout(url, options);
  return handleResponse<T>(response);
};

// ==================== 基础管理API ====================

/**
 * 创建Agent
 */
export const createAgent = async (data: CreateAgentRequest): Promise<Agent> => {
  return request<Agent>('POST', '/workers', data);
};

/**
 * 获取Agent列表
 */
export const listAgents = async (params?: AgentFilterParams): Promise<AgentListResponse> => {
  return request<AgentListResponse>('GET', '/workers', undefined, params);
};

/**
 * 获取Agent详情
 */
export const getAgent = async (agentId: number): Promise<Agent> => {
  return request<Agent>('GET', `/workers/${agentId}`);
};

/**
 * 更新Agent
 */
export const updateAgent = async (agentId: number, data: UpdateAgentRequest): Promise<Agent> => {
  return request<Agent>('PUT', `/workers/${agentId}`, data);
};

/**
 * 更新Agent配置
 */
export const updateAgentConfig = async (agentId: number, data: UpdateAgentConfigRequest): Promise<Agent> => {
  return request<Agent>('PATCH', `/workers/${agentId}/config`, data);
};

/**
 * 删除Agent
 */
export const deleteAgent = async (agentId: number): Promise<void> => {
  return request<void>('DELETE', `/workers/${agentId}`);
};

/**
 * 克隆Agent
 */
export const cloneAgent = async (agentId: number, data: CloneAgentRequest): Promise<Agent> => {
  return request<Agent>('POST', `/workers/${agentId}/clone`, data);
};

/**
 * 批量操作Agent
 */
export const batchOperation = async (data: BatchOperationRequest): Promise<BatchOperationResponse> => {
  return request<BatchOperationResponse>('POST', '/workers/batch', data);
};

// ==================== 生命周期管理API ====================

/**
 * 启动Agent
 */
export const startAgent = async (agentId: number): Promise<{ task_id: string; status: string }> => {
  return request<{ task_id: string; status: string }>('POST', `/workers/${agentId}/lifecycle/start`);
};

/**
 * 停止Agent
 */
export const stopAgent = async (agentId: number): Promise<void> => {
  return request<void>('POST', `/workers/${agentId}/lifecycle/stop`);
};

/**
 * 重启Agent
 */
export const restartAgent = async (agentId: number): Promise<{ task_id: string; status: string }> => {
  return request<{ task_id: string; status: string }>('POST', `/workers/${agentId}/lifecycle/restart`);
};

/**
 * 暂停Agent
 */
export const pauseAgent = async (agentId: number): Promise<void> => {
  return request<void>('POST', `/workers/${agentId}/lifecycle/pause`);
};

/**
 * 恢复Agent
 */
export const resumeAgent = async (agentId: number): Promise<void> => {
  return request<void>('POST', `/workers/${agentId}/lifecycle/resume`);
};

/**
 * 获取Agent状态
 */
export const getAgentStatus = async (agentId: number): Promise<AgentStatusResponse> => {
  return request<AgentStatusResponse>('GET', `/workers/${agentId}/lifecycle/status`);
};

/**
 * 健康检查
 */
export const healthCheck = async (agentId: number): Promise<HealthCheckResponse> => {
  return request<HealthCheckResponse>('GET', `/workers/${agentId}/lifecycle/health`);
};

// ==================== 监控数据API ====================

/**
 * 获取Agent实时指标
 */
export const getAgentMetrics = async (agentId: number): Promise<AgentMetrics> => {
  return request<AgentMetrics>('GET', `/workers/${agentId}/monitoring/metrics`);
};

/**
 * 获取Agent历史指标
 */
export const getMetricsHistory = async (
  agentId: number,
  params?: MetricsHistoryParams
): Promise<AgentMetrics[]> => {
  return request<AgentMetrics[]>('GET', `/workers/${agentId}/monitoring/metrics/history`, undefined, params);
};

/**
 * 获取Agent日志
 */
export const getAgentLogs = async (
  agentId: number,
  params?: LogQueryParams
): Promise<AgentLog[]> => {
  return request<AgentLog[]>('GET', `/workers/${agentId}/monitoring/logs`, undefined, params);
};

/**
 * 获取Agent绩效统计
 */
export const getAgentPerformance = async (
  agentId: number,
  days: number = 30
): Promise<AgentPerformance[]> => {
  return request<AgentPerformance[]>('GET', `/workers/${agentId}/monitoring/performance`, undefined, { days });
};

/**
 * 获取Agent交易记录
 */
export const getAgentTrades = async (
  agentId: number,
  params?: TradeQueryParams
): Promise<{ items: AgentTrade[]; total: number; page: number; page_size: number }> => {
  return request('GET', `/workers/${agentId}/monitoring/trades`, undefined, params);
};

// ==================== 策略代理API ====================

/**
 * 部署策略
 */
export const deployStrategy = async (
  agentId: number,
  data: StrategyDeployRequest
): Promise<{ deployed: boolean; strategy_id: number; worker_id: number }> => {
  return request('POST', `/workers/${agentId}/strategy/deploy`, data);
};

/**
 * 卸载策略
 */
export const undeployStrategy = async (agentId: number): Promise<{ undeployed: boolean; worker_id: number }> => {
  return request('POST', `/workers/${agentId}/strategy/undeploy`);
};

/**
 * 获取策略参数
 */
export const getStrategyParameters = async (agentId: number): Promise<StrategyParameter[]> => {
  return request<StrategyParameter[]>('GET', `/workers/${agentId}/strategy/parameters`);
};

/**
 * 更新策略参数
 */
export const updateStrategyParameters = async (
  agentId: number,
  data: UpdateStrategyParametersRequest
): Promise<void> => {
  return request<void>('PUT', `/workers/${agentId}/strategy/parameters`, data);
};

/**
 * 获取持仓信息
 */
export const getPositions = async (agentId: number): Promise<PositionInfo[]> => {
  return request<PositionInfo[]>('GET', `/workers/${agentId}/strategy/positions`);
};

/**
 * 获取订单信息
 */
export const getOrders = async (agentId: number, status?: string): Promise<OrderInfo[]> => {
  return request<OrderInfo[]>('GET', `/workers/${agentId}/strategy/orders`, undefined, status ? { status } : undefined);
};

/**
 * 发送交易信号
 */
export const sendTradingSignal = async (
  agentId: number,
  signal: TradingSignal
): Promise<{ sent: boolean; signal_id: string; worker_id: number }> => {
  return request('POST', `/workers/${agentId}/strategy/signal`, signal);
};

// ==================== WebSocket连接（用于实时日志） ====================

/**
 * 创建WebSocket连接（用于实时日志流）
 */
export const createLogWebSocket = (agentId: number): WebSocket => {
  const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/workers/${agentId}/monitoring/logs/stream`;
  const ws = new WebSocket(wsUrl);
  
  // 连接建立时发送认证信息
  ws.onopen = () => {
    const token = getAuthToken();
    if (token) {
      ws.send(JSON.stringify({ type: 'auth', token }));
    }
  };
  
  return ws;
};

// 导出所有API函数
export const agentApi = {
  // 基础管理
  createAgent,
  listAgents,
  getAgent,
  updateAgent,
  updateAgentConfig,
  deleteAgent,
  cloneAgent,
  batchOperation,
  
  // 生命周期
  startAgent,
  stopAgent,
  restartAgent,
  pauseAgent,
  resumeAgent,
  getAgentStatus,
  healthCheck,
  
  // 监控数据
  getAgentMetrics,
  getMetricsHistory,
  getAgentLogs,
  getAgentPerformance,
  getAgentTrades,
  
  // 策略代理
  deployStrategy,
  undeployStrategy,
  getStrategyParameters,
  updateStrategyParameters,
  getPositions,
  getOrders,
  sendTradingSignal,
  
  // WebSocket
  createLogWebSocket
};

export default agentApi;
