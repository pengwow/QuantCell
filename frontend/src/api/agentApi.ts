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
 * 创建WebSocket连接（用于实时日志流）
 */
export const createLogWebSocket = (agentId: number): WebSocket => {
  const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/workers/${agentId}/monitoring/logs/stream`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    const token = localStorage.getItem('token');
    if (token) {
      ws.send(JSON.stringify({ type: 'auth', token }));
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

export default agentApi;
