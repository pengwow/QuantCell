/**
 * Agent API调用模块
 *
 * 与后端Worker模块API规范保持一致
 * 实现完整的错误处理和数据验证
 */

import { apiRequest } from './index';

// API基础URL
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

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

// Agent类型定义
export interface Agent {
  id: number;
  name: string;
  description?: string;
  status: 'running' | 'stopped' | 'paused' | 'error';
  config?: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export interface AgentListResponse {
  items: Agent[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  config?: Record<string, any>;
}

export interface UpdateAgentRequest {
  name?: string;
  description?: string;
}

export interface UpdateAgentConfigRequest {
  config: Record<string, any>;
}

export interface CloneAgentRequest {
  name?: string;
  description?: string;
}

export interface BatchOperationRequest {
  ids: number[];
  operation: 'start' | 'stop' | 'restart' | 'delete';
}

export interface BatchOperationResponse {
  success: number;
  failed: number;
  errors?: Array<{ id: number; error: string }>;
}

export interface AgentStatusResponse {
  id: number;
  status: string;
  uptime?: number;
  last_error?: string;
}

export interface HealthCheckResponse {
  healthy: boolean;
  checks: Record<string, boolean>;
}

export interface AgentMetrics {
  cpu_usage: number;
  memory_usage: number;
  network_in: number;
  network_out: number;
  timestamp: string;
}

export interface AgentLog {
  level: 'debug' | 'info' | 'warning' | 'error';
  message: string;
  timestamp: string;
  source?: string;
}

export interface AgentPerformance {
  date: string;
  trades_count: number;
  profit_loss: number;
  win_rate: number;
}

export interface AgentTrade {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  timestamp: string;
  pnl?: number;
}

export interface StrategyDeployRequest {
  strategy_id: number;
  parameters?: Record<string, any>;
}

export interface StrategyParameter {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  default?: any;
  description?: string;
  required?: boolean;
}

export interface UpdateStrategyParametersRequest {
  parameters: Record<string, any>;
}

export interface PositionInfo {
  symbol: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  unrealized_pnl: number;
}

export interface OrderInfo {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  type: 'market' | 'limit' | 'stop';
  quantity: number;
  price?: number;
  status: 'pending' | 'filled' | 'cancelled' | 'rejected';
  timestamp: string;
}

export interface TradingSignal {
  action: 'buy' | 'sell' | 'close';
  symbol: string;
  quantity?: number;
  price?: number;
  metadata?: Record<string, any>;
}

export interface AgentFilterParams {
  status?: string;
  name?: string;
  page?: number;
  page_size?: number;
}

export interface LogQueryParams {
  level?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}

export interface TradeQueryParams {
  symbol?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface MetricsHistoryParams {
  start_time?: string;
  end_time?: string;
  interval?: string;
}

// ==================== 基础管理API ====================

/**
 * 创建Agent
 */
export const createAgent = async (data: CreateAgentRequest): Promise<Agent> => {
  return apiRequest.post<Agent>('/workers', data);
};

/**
 * 获取Agent列表
 */
export const listAgents = async (params?: AgentFilterParams): Promise<AgentListResponse> => {
  return apiRequest.get<AgentListResponse>('/workers', params);
};

/**
 * 获取Agent详情
 */
export const getAgent = async (agentId: number): Promise<Agent> => {
  return apiRequest.get<Agent>(`/workers/${agentId}`);
};

/**
 * 更新Agent
 */
export const updateAgent = async (agentId: number, data: UpdateAgentRequest): Promise<Agent> => {
  return apiRequest.put<Agent>(`/workers/${agentId}`, data);
};

/**
 * 更新Agent配置
 */
export const updateAgentConfig = async (agentId: number, data: UpdateAgentConfigRequest): Promise<Agent> => {
  return apiRequest.patch<Agent>(`/workers/${agentId}/config`, data);
};

/**
 * 删除Agent
 */
export const deleteAgent = async (agentId: number): Promise<void> => {
  return apiRequest.delete<void>(`/workers/${agentId}`);
};

/**
 * 克隆Agent
 */
export const cloneAgent = async (agentId: number, data: CloneAgentRequest): Promise<Agent> => {
  return apiRequest.post<Agent>(`/workers/${agentId}/clone`, data);
};

/**
 * 批量操作Agent
 */
export const batchOperation = async (data: BatchOperationRequest): Promise<BatchOperationResponse> => {
  return apiRequest.post<BatchOperationResponse>('/workers/batch', data);
};

// ==================== 生命周期管理API ====================

/**
 * 启动Agent
 */
export const startAgent = async (agentId: number): Promise<{ task_id: string; status: string }> => {
  return apiRequest.post<{ task_id: string; status: string }>(`/workers/${agentId}/lifecycle/start`);
};

/**
 * 停止Agent
 */
export const stopAgent = async (agentId: number): Promise<void> => {
  return apiRequest.post<void>(`/workers/${agentId}/lifecycle/stop`);
};

/**
 * 重启Agent
 */
export const restartAgent = async (agentId: number): Promise<{ task_id: string; status: string }> => {
  return apiRequest.post<{ task_id: string; status: string }>(`/workers/${agentId}/lifecycle/restart`);
};

/**
 * 暂停Agent
 */
export const pauseAgent = async (agentId: number): Promise<void> => {
  return apiRequest.post<void>(`/workers/${agentId}/lifecycle/pause`);
};

/**
 * 恢复Agent
 */
export const resumeAgent = async (agentId: number): Promise<void> => {
  return apiRequest.post<void>(`/workers/${agentId}/lifecycle/resume`);
};

/**
 * 获取Agent状态
 */
export const getAgentStatus = async (agentId: number): Promise<AgentStatusResponse> => {
  return apiRequest.get<AgentStatusResponse>(`/workers/${agentId}/lifecycle/status`);
};

/**
 * 健康检查
 */
export const healthCheck = async (agentId: number): Promise<HealthCheckResponse> => {
  return apiRequest.get<HealthCheckResponse>(`/workers/${agentId}/lifecycle/health`);
};

// ==================== 监控数据API ====================

/**
 * 获取Agent实时指标
 */
export const getAgentMetrics = async (agentId: number): Promise<AgentMetrics> => {
  return apiRequest.get<AgentMetrics>(`/workers/${agentId}/monitoring/metrics`);
};

/**
 * 获取Agent历史指标
 */
export const getMetricsHistory = async (
  agentId: number,
  params?: MetricsHistoryParams
): Promise<AgentMetrics[]> => {
  return apiRequest.get<AgentMetrics[]>(`/workers/${agentId}/monitoring/metrics/history`, params);
};

/**
 * 获取Agent日志
 */
export const getAgentLogs = async (
  agentId: number,
  params?: LogQueryParams
): Promise<AgentLog[]> => {
  return apiRequest.get<AgentLog[]>(`/workers/${agentId}/monitoring/logs`, params);
};

/**
 * 获取Agent绩效统计
 */
export const getAgentPerformance = async (
  agentId: number,
  days: number = 30
): Promise<AgentPerformance[]> => {
  return apiRequest.get<AgentPerformance[]>(`/workers/${agentId}/monitoring/performance`, { days });
};

/**
 * 获取Agent交易记录
 */
export const getAgentTrades = async (
  agentId: number,
  params?: TradeQueryParams
): Promise<{ items: AgentTrade[]; total: number; page: number; page_size: number }> => {
  return apiRequest.get<{ items: AgentTrade[]; total: number; page: number; page_size: number }>(`/workers/${agentId}/monitoring/trades`, params);
};

// ==================== 策略代理API ====================

/**
 * 部署策略
 */
export const deployStrategy = async (
  agentId: number,
  data: StrategyDeployRequest
): Promise<{ deployed: boolean; strategy_id: number; worker_id: number }> => {
  return apiRequest.post<{ deployed: boolean; strategy_id: number; worker_id: number }>(`/workers/${agentId}/strategy/deploy`, data);
};

/**
 * 卸载策略
 */
export const undeployStrategy = async (agentId: number): Promise<{ undeployed: boolean; worker_id: number }> => {
  return apiRequest.post<{ undeployed: boolean; worker_id: number }>(`/workers/${agentId}/strategy/undeploy`);
};

/**
 * 获取策略参数
 */
export const getStrategyParameters = async (agentId: number): Promise<StrategyParameter[]> => {
  return apiRequest.get<StrategyParameter[]>(`/workers/${agentId}/strategy/parameters`);
};

/**
 * 更新策略参数
 */
export const updateStrategyParameters = async (
  agentId: number,
  data: UpdateStrategyParametersRequest
): Promise<void> => {
  return apiRequest.put<void>(`/workers/${agentId}/strategy/parameters`, data);
};

/**
 * 获取持仓信息
 */
export const getPositions = async (agentId: number): Promise<PositionInfo[]> => {
  return apiRequest.get<PositionInfo[]>(`/workers/${agentId}/strategy/positions`);
};

/**
 * 获取订单信息
 */
export const getOrders = async (agentId: number, status?: string): Promise<OrderInfo[]> => {
  return apiRequest.get<OrderInfo[]>(`/workers/${agentId}/strategy/orders`, status ? { status } : undefined);
};

/**
 * 发送交易信号
 */
export const sendTradingSignal = async (
  agentId: number,
  signal: TradingSignal
): Promise<{ sent: boolean; signal_id: string; worker_id: number }> => {
  return apiRequest.post<{ sent: boolean; signal_id: string; worker_id: number }>(`/workers/${agentId}/strategy/signal`, signal);
};

// ==================== WebSocket连接（用于实时日志） ====================

/**
 * 从tokenManager获取token，确保与axios实例使用相同的token来源
 */
const getWebSocketToken = (): string | undefined => {
  // 优先使用tokenManager获取token
  const { getAccessToken } = require('../utils/tokenManager');
  return getAccessToken();
};

/**
 * 处理WebSocket认证错误
 * 当收到401错误时，统一跳转到登录页面
 */
const handleWebSocketAuthError = (): void => {
  // 保存当前页面状态
  const currentPath = window.location.pathname + window.location.search + window.location.hash;
  sessionStorage.setItem('redirect_after_login', currentPath);

  // 清除认证数据
  const { removeToken } = require('../utils/tokenManager');
  removeToken();
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('quantcell_jwt_token');

  // 跳转到登录页
  window.location.href = '/login';
};

/**
 * 创建WebSocket连接（用于实时日志流）
 * 增强401错误处理，确保认证失败时统一跳转
 */
export const createLogWebSocket = (agentId: number): WebSocket => {
  const token = getWebSocketToken();
  // 如果token存在，添加到URL查询参数中
  const wsUrl = token
    ? `${API_BASE_URL.replace('http', 'ws')}/workers/${agentId}/monitoring/logs/stream?token=${encodeURIComponent(token)}`
    : `${API_BASE_URL.replace('http', 'ws')}/workers/${agentId}/monitoring/logs/stream`;

  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    // 连接已建立，token已通过URL传递
  };

  ws.onerror = (error) => {
    console.error('WebSocket错误:', error);
  };

  ws.onclose = (event) => {
    // 处理认证失败关闭连接的情况
    if (event.code === 1008 || event.code === 1006) {
      // 1008: Policy Violation (认证失败)
      // 1006: Abnormal Closure (可能被服务器拒绝)
      handleWebSocketAuthError();
    }
  };

  return ws;
};

// 导出所有API函数
export const agentApi = {
  createAgent,
  listAgents,
  getAgent,
  updateAgent,
  updateAgentConfig,
  deleteAgent,
  cloneAgent,
  batchOperation,
  startAgent,
  stopAgent,
  restartAgent,
  pauseAgent,
  resumeAgent,
  getAgentStatus,
  healthCheck,
  getAgentMetrics,
  getMetricsHistory,
  getAgentLogs,
  getAgentPerformance,
  getAgentTrades,
  deployStrategy,
  undeployStrategy,
  getStrategyParameters,
  updateStrategyParameters,
  getPositions,
  getOrders,
  sendTradingSignal,
  createLogWebSocket
};

// ==================== 工具参数管理API ====================

/**
 * 工具参数类型定义
 */
export interface ToolParamTemplate {
  name: string;
  type: 'string' | 'integer' | 'float' | 'boolean';
  required: boolean;
  sensitive: boolean;
  default?: any;
  env_key?: string;
  description: string;
  validation?: {
    min?: number;
    max?: number;
  };
}

export interface ToolParamValue {
  value: any;
  configured: boolean;
  source: 'database' | 'environment' | 'default';
  sensitive: boolean;
  type: string;
  description: string;
}

export interface ToolInfo {
  name: string;
  param_count: number;
  configured_count: number;
  has_required_params: boolean;
}

export interface ToolParamsResponse {
  tool_name: string;
  params: Record<string, ToolParamValue>;
}

export interface BatchUpdateResult {
  updated: string[];
  skipped: string[];
  errors: string[];
}

export interface ExportConfigResponse {
  export_time: string;
  version: string;
  tools: Record<string, Record<string, any>>;
}

export interface ImportExportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

/**
 * 获取所有已注册的工具列表
 */
export const getRegisteredTools = async (): Promise<ToolInfo[]> => {
  return apiRequest.get<ToolInfo[]>('/agent/tools/params/tools');
};

/**
 * 获取指定工具的参数配置
 */
export const getToolParams = async (
  toolName: string,
  includeSensitive: boolean = false
): Promise<ToolParamsResponse> => {
  return apiRequest.get<ToolParamsResponse>(`/agent/tools/params/${toolName}`, {
    include_sensitive: includeSensitive
  });
};

/**
 * 设置工具参数
 */
export const setToolParam = async (
  toolName: string,
  paramName: string,
  value: any
): Promise<{ param_name: string; value_masked: string; updated_at: string }> => {
  return apiRequest.put(`/agent/tools/params/${toolName}/${paramName}`, { value });
};

/**
 * 批量更新工具参数
 */
export const batchUpdateToolParams = async (
  toolName: string,
  params: Record<string, any>,
  overwrite: boolean = false
): Promise<BatchUpdateResult> => {
  return apiRequest.post<BatchUpdateResult>(`/agent/tools/params/${toolName}/batch`, {
    params,
    overwrite
  });
};

/**
 * 删除工具参数（恢复默认值或环境变量）
 */
export const deleteToolParam = async (
  toolName: string,
  paramName: string
): Promise<{ message: string }> => {
  return apiRequest.delete(`/agent/tools/params/${toolName}/${paramName}`);
};

/**
 * 导出工具配置
 */
export const exportToolConfig = async (
  toolName?: string
): Promise<ExportConfigResponse> => {
  const params = toolName ? { tool_name: toolName } : {};
  return apiRequest.get<ExportConfigResponse>('/agent/tools/params/export', params);
};

/**
 * 导入工具配置
 */
export const importToolConfig = async (
  config: ExportConfigResponse,
  overwrite: boolean = false
): Promise<ImportExportResult> => {
  return apiRequest.post<ImportExportResult>('/agent/tools/params/import', {
    config,
    overwrite
  });
};

// 工具参数管理API导出
export const toolParamApi = {
  getRegisteredTools,
  getToolParams,
  setToolParam,
  batchUpdateToolParams,
  deleteToolParam,
  exportToolConfig,
  importToolConfig
};

export default agentApi;
