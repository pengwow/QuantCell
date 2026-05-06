/**
 * Worker类型定义
 *
 * 与后端Worker模块API规范保持一致
 */

// Worker状态常量
export const WorkerStatus = {
  STOPPED: 'stopped',
  RUNNING: 'running',
  PAUSED: 'paused',
  ERROR: 'error',
  STARTING: 'starting',
  STOPPING: 'stopping'
} as const;

// Worker状态类型
export type WorkerStatus = typeof WorkerStatus[keyof typeof WorkerStatus];

// Worker状态文本映射
export const WorkerStatusText: Record<WorkerStatus, string> = {
  [WorkerStatus.STOPPED]: '已停止',
  [WorkerStatus.RUNNING]: '运行中',
  [WorkerStatus.PAUSED]: '已暂停',
  [WorkerStatus.ERROR]: '错误',
  [WorkerStatus.STARTING]: '启动中',
  [WorkerStatus.STOPPING]: '停止中'
};

// Worker状态标签颜色映射
export const WorkerStatusColor: Record<WorkerStatus, string> = {
  [WorkerStatus.STOPPED]: 'gray',
  [WorkerStatus.RUNNING]: 'green',
  [WorkerStatus.PAUSED]: 'orange',
  [WorkerStatus.ERROR]: 'red',
  [WorkerStatus.STARTING]: 'blue',
  [WorkerStatus.STOPPING]: 'cyan'
};

// 交易标的配置
export interface SymbolsConfig {
  type: 'symbols' | 'pool';  // symbols-直接货币对, pool-自选组
  symbols: string[];  // 货币对列表
  pool_id?: number;  // 自选组ID
  pool_name?: string;  // 自选组名称
}

// 交易配置
export interface TradingConfig {
  exchange: string;
  symbols_config: SymbolsConfig;
  timeframe: string;
  market_type: string;
  trading_mode: string;
}

// 策略信息
export interface StrategyInfo {
  id: number;
  name: string;
  description?: string;
  strategy_type: string;  // default/legacy
  version: string;
}

// Worker基础信息
export interface Worker {
  id: number;
  name: string;
  description?: string;
  status: WorkerStatus;
  strategy_id: number;
  strategy_info?: StrategyInfo;
  // 交易配置（新格式）
  trading_config?: TradingConfig;
  // 兼容旧版本字段
  exchange: string;
  symbols: string[];
  timeframe: string;
  market_type: string;
  trading_mode: string;
  cpu_limit: number;
  memory_limit: number;
  pid?: number;
  config?: Record<string, any>;
  created_at: string;
  updated_at: string;
  started_at?: string;
  stopped_at?: string;
  total_profit?: number;
}

// Worker列表响应
export interface WorkerListResponse {
  items: Worker[];
  total: number;
  page: number;
  page_size: number;
}

// 创建Worker请求
export interface CreateWorkerRequest {
  name: string;
  description?: string;
  strategy_id: number;
  // 交易配置（新格式）
  trading_config?: TradingConfig;
  // 兼容旧版本字段
  exchange?: string;
  symbols?: string[];
  timeframe?: string;
  market_type?: string;
  trading_mode?: string;
  cpu_limit?: number;
  memory_limit?: number;
  env_vars?: Record<string, string>;
  config?: Record<string, any>;
}

// 更新Worker请求
export interface UpdateWorkerRequest {
  name?: string;
  description?: string;
  // 交易配置（新格式）
  trading_config?: TradingConfig;
  // 兼容旧版本字段
  exchange?: string;
  symbols?: string[];
  timeframe?: string;
  trading_mode?: string;
  cpu_limit?: number;
  memory_limit?: number;
  config?: Record<string, any>;
}

// 更新Worker配置请求
export interface UpdateWorkerConfigRequest {
  config: Record<string, any>;
}

// 克隆Worker请求
export interface CloneWorkerRequest {
  new_name: string;
  copy_config?: boolean;
  copy_parameters?: boolean;
}

// 批量操作请求
export interface BatchOperationRequest {
  worker_ids: number[];
  operation: 'start' | 'stop' | 'restart';
}

// 批量操作响应
export interface BatchOperationResponse {
  success: number[];
  failed: Record<number, string>;
  total: number;
}

// Worker状态响应
export interface WorkerStatusResponse {
  worker_id: number;
  status: WorkerStatus;
  pid?: number;
  uptime?: number;
  last_heartbeat?: string;
  is_healthy: boolean;
}

// 健康检查响应
export interface HealthCheckResponse {
  worker_id: number;
  status: string;
  is_healthy: boolean;
  last_heartbeat?: string;
  uptime?: number;
  checks: Record<string, boolean>;
}

// Worker指标
export interface WorkerMetrics {
  worker_id: number;
  cpu_usage: number;
  memory_usage: number;
  memory_used_mb: number;
  network_in: number;
  network_out: number;
  active_tasks: number;
  timestamp: string;
}

// Worker日志
export interface WorkerLog {
  id: number;
  worker_id: number;
  level: string;
  message: string;
  source?: string;
  timestamp: string;
}

// Worker绩效
export interface WorkerPerformance {
  worker_id: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_profit: number;
  total_loss: number;
  net_profit: number;
  max_drawdown: number;
  sharpe_ratio: number;
  date: string;
}

// 交易记录
export interface WorkerTrade {
  id: number;
  worker_id: number;
  trade_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  order_type: string;
  quantity: number;
  price: number;
  amount: number;
  fee: number;
  fee_currency: string;
  realized_pnl?: number;
  realized_pnl_pct?: number;
  entry_time?: string;
  exit_time?: string;
  created_at: string;
}

// 策略部署请求
export interface StrategyDeployRequest {
  strategy_id: number;
  parameters?: Record<string, any>;
  auto_start?: boolean;
}

// 策略参数
export interface StrategyParameter {
  param_name: string;
  param_value: any;
  param_type: string;
  description?: string;
  min_value?: number;
  max_value?: number;
  editable: boolean;
}

// 更新策略参数请求
export interface UpdateStrategyParametersRequest {
  parameters: Record<string, any>;
}

// 持仓信息
export interface PositionInfo {
  symbol: string;
  side: 'long' | 'short';
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  timestamp: string;
}

// 订单信息
export interface OrderInfo {
  order_id: string;
  symbol: string;
  side: 'buy' | 'sell';
  order_type: string;
  quantity: number;
  price?: number;
  status: string;
  filled_quantity: number;
  created_at: string;
}

// API响应包装
export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data?: T;
}

// 分页参数
export interface PaginationParams {
  page?: number;
  page_size?: number;
}

// 筛选参数
export interface WorkerFilterParams extends PaginationParams {
  status?: WorkerStatus;
  strategy_id?: number;
}

// 日志查询参数
export interface LogQueryParams extends PaginationParams {
  level?: string;
  start_time?: string;
  end_time?: string;
}

// 交易记录查询参数
export interface TradeQueryParams extends PaginationParams {
  symbol?: string;
  start_time?: string;
  end_time?: string;
}

// 指标历史查询参数
export interface MetricsHistoryParams {
  start_time?: string;
  end_time?: string;
  interval?: string;
}

// 交易信号
export interface TradingSignal {
  symbol: string;
  action: 'buy' | 'sell';
  quantity?: number;
  price?: number;
  order_type?: string;
  params?: Record<string, any>;
}

// ============================================
// WebSocket 消息类型
// ============================================

// WebSocket 日志消息
export interface WebSocketLogMessage {
  type: 'log';
  data: WorkerLog;
}

// WebSocket 状态更新消息
export interface WebSocketStatusMessage {
  type: 'status';
  data: {
    worker_id: number;
    status: WorkerStatus;
    timestamp: string;
  };
}

// WebSocket 指标更新消息
export interface WebSocketMetricsMessage {
  type: 'metrics';
  data: WorkerMetrics;
}

// WebSocket 错误消息
export interface WebSocketErrorMessage {
  type: 'error';
  data: {
    message: string;
    code?: string;
    timestamp: string;
  };
}

// WebSocket 消息联合类型
export type WebSocketMessage =
  | WebSocketLogMessage
  | WebSocketStatusMessage
  | WebSocketMetricsMessage
  | WebSocketErrorMessage;

// ============================================
// Store 状态类型
// ============================================

// Worker Store 状态
export interface WorkerStoreState {
  // 数据
  workers: Worker[];
  selectedWorker: Worker | null;
  performance: WorkerPerformance | null;
  trades: WorkerTrade[];
  logs: WorkerLog[];
  returnRateData: ReturnRateDataPoint[];

  // 分页
  total: number;
  page: number;
  pageSize: number;

  // 加载状态
  loading: boolean;
  loadingDetail: boolean;
  loadingPerformance: boolean;
  loadingTrades: boolean;
  loadingLogs: boolean;

  // 错误状态
  error: string | null;
  detailError: string | null;
  performanceError: string | null;
  tradesError: string | null;
  logsError: string | null;

  // WebSocket
  logStream: WorkerLogStreamType | null;
  isLogStreamConnected: boolean;
}

// Worker Store 操作
export interface WorkerStoreActions {
  // 数据获取
  fetchWorkers: (params?: WorkerFilterParams) => Promise<void>;
  fetchWorkerDetail: (workerId: number) => Promise<void>;
  fetchPerformance: (workerId: number, days?: number) => Promise<void>;
  fetchTrades: (workerId: number, params?: TradeQueryParams) => Promise<void>;
  fetchLogs: (workerId: number, params?: LogQueryParams) => Promise<void>;

  // CRUD 操作
  createWorker: (data: CreateWorkerRequest) => Promise<Worker>;
  updateWorker: (workerId: number, data: UpdateWorkerRequest) => Promise<Worker>;
  deleteWorker: (workerId: number) => Promise<void>;

  // 生命周期控制
  startWorker: (workerId: number) => Promise<void>;
  stopWorker: (workerId: number) => Promise<void>;
  pauseWorker: (workerId: number) => Promise<void>;
  resumeWorker: (workerId: number) => Promise<void>;

  // WebSocket
  connectLogStream: (workerId: number) => void;
  disconnectLogStream: () => void;

  // 状态管理
  setSelectedWorker: (worker: Worker | null) => void;
  clearErrors: () => void;
}

// WorkerLogStream 类型占位（避免循环依赖）
// 实际类型在 workerApi.ts 中定义，这里使用 any 作为占位
type WorkerLogStreamType = any;

// ==================== UI展示扩展类型 ====================

// 收益率曲线数据点
export interface ReturnRateDataPoint {
  timestamp: string;
  value: number;
}

// 策略绩效指标（前端展示用）
export interface WorkerPerformanceMetrics {
  winRate: number;           // 胜率 (%)
  profitLossRatio: number;   // 盈亏比
  maxDrawdown: number;       // 最大回撤 (%)
  sharpeRatio: number;       // 夏普比率
  totalTrades: number;       // 总交易数
  winningTrades: number;     // 盈利交易数
  losingTrades: number;      // 亏损交易数
  totalProfit: number;       // 总收益 ($)
  totalLoss: number;         // 总亏损 ($)
}

// 策略交易记录（前端展示用）
export interface WorkerTradeRecord {
  id: string;
  timestamp: string;
  symbol: string;
  action: 'buy' | 'sell';
  price: number;
  quantity: number;
  amount: number;
  status: 'filled' | 'pending' | 'cancelled';
}

// 扩展 Worker 类型，添加 UI 展示字段
export interface WorkerWithPerformance extends Worker {
  totalReturn: number;                    // 总收益率 (%)
  currentReturn: number;                  // 今日收益率 (%)
  startTime?: string;                     // 启动时间
  lastTradeTime?: string;                 // 最后交易时间
  performance: WorkerPerformanceMetrics;   // 绩效指标
  tradeRecords: WorkerTradeRecord[];       // 交易记录
  returnRateData: ReturnRateDataPoint[];  // 收益率曲线数据
}

// 策略状态文本映射（用于 UI 展示）
export const WorkerStatusDisplayText: Record<WorkerStatus, string> = {
  [WorkerStatus.STOPPED]: '已停止',
  [WorkerStatus.RUNNING]: '运行中',
  [WorkerStatus.PAUSED]: '已暂停',
  [WorkerStatus.ERROR]: '错误',
  [WorkerStatus.STARTING]: '启动中',
  [WorkerStatus.STOPPING]: '停止中'
};

// 策略状态颜色映射（Ant Design Tag 颜色）
export const WorkerStatusTagColor: Record<WorkerStatus, string> = {
  [WorkerStatus.STOPPED]: 'default',
  [WorkerStatus.RUNNING]: 'success',
  [WorkerStatus.PAUSED]: 'warning',
  [WorkerStatus.ERROR]: 'error',
  [WorkerStatus.STARTING]: 'processing',
  [WorkerStatus.STOPPING]: 'cyan'
};
