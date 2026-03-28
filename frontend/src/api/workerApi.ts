/**
 * Worker API Client
 *
 * 提供与后端 Worker API 的完整集成
 * 包括 CRUD 操作、生命周期控制、监控数据、WebSocket 日志等
 */

import { apiRequest } from './index';
import type {
  Worker,
  WorkerListResponse,
  CreateWorkerRequest,
  UpdateWorkerRequest,
  UpdateWorkerConfigRequest,
  CloneWorkerRequest,
  BatchOperationRequest,
  BatchOperationResponse,
  WorkerStatusResponse,
  HealthCheckResponse,
  WorkerMetrics,
  WorkerLog,
  WorkerPerformance,
  WorkerTrade,
  StrategyDeployRequest,
  StrategyParameter,
  UpdateStrategyParametersRequest,
  PositionInfo,
  OrderInfo,
  TradingSignal,
  WorkerFilterParams,
  LogQueryParams,
  TradeQueryParams,
  MetricsHistoryParams,
} from '../types/worker';

// ============================================
// Worker CRUD API
// ============================================

/**
 * 获取 Worker 列表
 * @param params 筛选和分页参数
 */
export const getWorkers = (params?: WorkerFilterParams): Promise<WorkerListResponse> => {
  return apiRequest.get('/workers', params);
};

/**
 * 获取单个 Worker 详情
 * @param workerId Worker ID
 */
export const getWorker = (workerId: number): Promise<Worker> => {
  return apiRequest.get(`/workers/${workerId}`);
};

/**
 * 创建 Worker
 * @param data 创建请求数据
 */
export const createWorker = (data: CreateWorkerRequest): Promise<Worker> => {
  return apiRequest.post('/workers', data);
};

/**
 * 更新 Worker
 * @param workerId Worker ID
 * @param data 更新请求数据
 */
export const updateWorker = (workerId: number, data: UpdateWorkerRequest): Promise<Worker> => {
  return apiRequest.put(`/workers/${workerId}`, data);
};

/**
 * 部分更新 Worker 配置
 * @param workerId Worker ID
 * @param data 配置更新数据
 */
export const updateWorkerConfig = (workerId: number, data: UpdateWorkerConfigRequest): Promise<Worker> => {
  return apiRequest.patch(`/workers/${workerId}/config`, data);
};

/**
 * 删除 Worker
 * @param workerId Worker ID
 */
export const deleteWorker = (workerId: number): Promise<void> => {
  return apiRequest.delete(`/workers/${workerId}`);
};

/**
 * 克隆 Worker
 * @param workerId Worker ID
 * @param data 克隆请求数据
 */
export const cloneWorker = (workerId: number, data: CloneWorkerRequest): Promise<Worker> => {
  return apiRequest.post(`/workers/${workerId}/clone`, data);
};

/**
 * 批量操作 Worker
 * @param data 批量操作请求数据
 */
export const batchOperation = (data: BatchOperationRequest): Promise<BatchOperationResponse> => {
  return apiRequest.post('/workers/batch', data);
};

// ============================================
// Worker Lifecycle API
// ============================================

/**
 * 启动 Worker
 * @param workerId Worker ID
 */
export const startWorker = (workerId: number): Promise<{ task_id: string; status: string }> => {
  return apiRequest.post(`/workers/${workerId}/lifecycle/start`);
};

/**
 * 停止 Worker
 * @param workerId Worker ID
 */
export const stopWorker = (workerId: number): Promise<void> => {
  return apiRequest.post(`/workers/${workerId}/lifecycle/stop`);
};

/**
 * 重启 Worker
 * @param workerId Worker ID
 */
export const restartWorker = (workerId: number): Promise<{ task_id: string; status: string }> => {
  return apiRequest.post(`/workers/${workerId}/lifecycle/restart`);
};

/**
 * 暂停 Worker
 * @param workerId Worker ID
 */
export const pauseWorker = (workerId: number): Promise<void> => {
  return apiRequest.post(`/workers/${workerId}/lifecycle/pause`);
};

/**
 * 恢复 Worker
 * @param workerId Worker ID
 */
export const resumeWorker = (workerId: number): Promise<void> => {
  return apiRequest.post(`/workers/${workerId}/lifecycle/resume`);
};

/**
 * 获取 Worker 实时状态
 * @param workerId Worker ID
 */
export const getWorkerStatus = (workerId: number): Promise<WorkerStatusResponse> => {
  return apiRequest.get(`/workers/${workerId}/lifecycle/status`);
};

/**
 * Worker 健康检查
 * @param workerId Worker ID
 */
export const healthCheck = (workerId: number): Promise<HealthCheckResponse> => {
  return apiRequest.get(`/workers/${workerId}/lifecycle/health`);
};

// ============================================
// Worker Monitoring API
// ============================================

/**
 * 获取 Worker 实时性能指标
 * @param workerId Worker ID
 */
export const getWorkerMetrics = (workerId: number): Promise<WorkerMetrics> => {
  return apiRequest.get(`/workers/${workerId}/monitoring/metrics`);
};

/**
 * 获取 Worker 历史性能指标
 * @param workerId Worker ID
 * @param params 查询参数
 */
export const getMetricsHistory = (
  workerId: number,
  params?: MetricsHistoryParams
): Promise<WorkerMetrics[]> => {
  return apiRequest.get(`/workers/${workerId}/monitoring/metrics/history`, params);
};

/**
 * 获取 Worker 日志
 * @param workerId Worker ID
 * @param params 查询参数
 */
export const getWorkerLogs = (workerId: number, params?: LogQueryParams): Promise<WorkerLog[]> => {
  return apiRequest.get(`/workers/${workerId}/monitoring/logs`, params);
};

/**
 * 获取 Worker 绩效统计
 * @param workerId Worker ID
 * @param days 查询天数
 */
export const getWorkerPerformance = (workerId: number, days?: number): Promise<WorkerPerformance[]> => {
  return apiRequest.get(`/workers/${workerId}/monitoring/performance`, { days });
};

/**
 * 获取 Worker 交易记录
 * @param workerId Worker ID
 * @param params 查询参数
 */
export const getWorkerTrades = (
  workerId: number,
  params?: TradeQueryParams
): Promise<{ items: WorkerTrade[]; total: number; page: number; page_size: number }> => {
  return apiRequest.get(`/workers/${workerId}/monitoring/trades`, params);
};

// ============================================
// WebSocket Log Streaming
// ============================================

/**
 * WebSocket 日志流连接
 */
export class WorkerLogStream {
  private websocket: WebSocket | null = null;
  private workerId: number;
  private onMessageCallback: ((log: WorkerLog) => void) | null = null;
  private onErrorCallback: ((error: Event) => void) | null = null;
  private onCloseCallback: (() => void) | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 3000;

  constructor(workerId: number) {
    this.workerId = workerId;
  }

  /**
   * 连接 WebSocket
   */
  connect(): void {
    const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/api/workers/${this.workerId}/monitoring/logs/stream`;

    this.websocket = new WebSocket(wsUrl);

    this.websocket.onopen = () => {
      console.log(`Worker ${this.workerId} log stream connected`);
      this.reconnectAttempts = 0;
    };

    this.websocket.onmessage = (event) => {
      try {
        const log: WorkerLog = JSON.parse(event.data);
        this.onMessageCallback?.(log);
      } catch (error) {
        console.error('Failed to parse log message:', error);
      }
    };

    this.websocket.onerror = (error) => {
      console.error(`Worker ${this.workerId} log stream error:`, error);
      this.onErrorCallback?.(error);
    };

    this.websocket.onclose = () => {
      console.log(`Worker ${this.workerId} log stream closed`);
      this.onCloseCallback?.();

      // 自动重连
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => {
          console.log(`Reconnecting... attempt ${this.reconnectAttempts}`);
          this.connect();
        }, this.reconnectDelay);
      }
    };
  }

  /**
   * 断开 WebSocket 连接
   */
  disconnect(): void {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
  }

  /**
   * 设置消息接收回调
   */
  onMessage(callback: (log: WorkerLog) => void): void {
    this.onMessageCallback = callback;
  }

  /**
   * 设置错误回调
   */
  onError(callback: (error: Event) => void): void {
    this.onErrorCallback = callback;
  }

  /**
   * 设置连接关闭回调
   */
  onClose(callback: () => void): void {
    this.onCloseCallback = callback;
  }

  /**
   * 检查连接状态
   */
  isConnected(): boolean {
    return this.websocket?.readyState === WebSocket.OPEN;
  }
}

// ============================================
// Strategy Management API
// ============================================

/**
 * 部署策略到 Worker
 * @param workerId Worker ID
 * @param data 部署请求数据
 */
export const deployStrategy = (
  workerId: number,
  data: StrategyDeployRequest
): Promise<{ success: boolean; message: string }> => {
  return apiRequest.post(`/workers/${workerId}/strategy/deploy`, data);
};

/**
 * 卸载 Worker 上的策略
 * @param workerId Worker ID
 */
export const undeployStrategy = (workerId: number): Promise<{ success: boolean; message: string }> => {
  return apiRequest.post(`/workers/${workerId}/strategy/undeploy`);
};

/**
 * 获取策略参数
 * @param workerId Worker ID
 */
export const getStrategyParameters = (workerId: number): Promise<StrategyParameter[]> => {
  return apiRequest.get(`/workers/${workerId}/strategy/parameters`);
};

/**
 * 更新策略参数
 * @param workerId Worker ID
 * @param data 参数更新数据
 */
export const updateStrategyParameters = (
  workerId: number,
  data: UpdateStrategyParametersRequest
): Promise<void> => {
  return apiRequest.put(`/workers/${workerId}/strategy/parameters`, data);
};

/**
 * 获取持仓信息
 * @param workerId Worker ID
 */
export const getPositions = (workerId: number): Promise<PositionInfo[]> => {
  return apiRequest.get(`/workers/${workerId}/strategy/positions`);
};

/**
 * 获取订单信息
 * @param workerId Worker ID
 * @param status 订单状态筛选
 */
export const getOrders = (workerId: number, status?: string): Promise<OrderInfo[]> => {
  return apiRequest.get(`/workers/${workerId}/strategy/orders`, { status });
};

/**
 * 发送交易信号
 * @param workerId Worker ID
 * @param signal 交易信号
 */
export const sendTradingSignal = (
  workerId: number,
  signal: TradingSignal
): Promise<{ success: boolean; message: string }> => {
  return apiRequest.post(`/workers/${workerId}/strategy/signal`, signal);
};

// ============================================
// Worker API 导出
// ============================================

export const workerApi = {
  // CRUD
  getWorkers,
  getWorker,
  createWorker,
  updateWorker,
  updateWorkerConfig,
  deleteWorker,
  cloneWorker,
  batchOperation,

  // Lifecycle
  startWorker,
  stopWorker,
  restartWorker,
  pauseWorker,
  resumeWorker,
  getWorkerStatus,
  healthCheck,

  // Monitoring
  getWorkerMetrics,
  getMetricsHistory,
  getWorkerLogs,
  getWorkerPerformance,
  getWorkerTrades,

  // Strategy
  deployStrategy,
  undeployStrategy,
  getStrategyParameters,
  updateStrategyParameters,
  getPositions,
  getOrders,
  sendTradingSignal,

  // WebSocket
  WorkerLogStream,
};

export default workerApi;
