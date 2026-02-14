/**
 * Agent类型定义
 * 
 * 与后端Worker模块API规范保持一致
 */

// Agent状态常量
export const AgentStatus = {
  STOPPED: 'stopped',
  RUNNING: 'running',
  PAUSED: 'paused',
  ERROR: 'error',
  STARTING: 'starting',
  STOPPING: 'stopping'
} as const;

// Agent状态类型
export type AgentStatus = typeof AgentStatus[keyof typeof AgentStatus];

// Agent状态文本映射
export const AgentStatusText: Record<AgentStatus, string> = {
  [AgentStatus.STOPPED]: '已停止',
  [AgentStatus.RUNNING]: '运行中',
  [AgentStatus.PAUSED]: '已暂停',
  [AgentStatus.ERROR]: '错误',
  [AgentStatus.STARTING]: '启动中',
  [AgentStatus.STOPPING]: '停止中'
};

// Agent状态标签颜色映射
export const AgentStatusColor: Record<AgentStatus, string> = {
  [AgentStatus.STOPPED]: 'gray',
  [AgentStatus.RUNNING]: 'green',
  [AgentStatus.PAUSED]: 'orange',
  [AgentStatus.ERROR]: 'red',
  [AgentStatus.STARTING]: 'blue',
  [AgentStatus.STOPPING]: 'cyan'
};

// Agent基础信息
export interface Agent {
  id: number;
  name: string;
  description?: string;
  status: AgentStatus;
  strategy_id: number;
  exchange: string;
  symbol: string;
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
}

// Agent列表响应
export interface AgentListResponse {
  items: Agent[];
  total: number;
  page: number;
  page_size: number;
}

// 创建Agent请求
export interface CreateAgentRequest {
  name: string;
  description?: string;
  strategy_id: number;
  exchange?: string;
  symbol?: string;
  timeframe?: string;
  market_type?: string;
  trading_mode?: string;
  cpu_limit?: number;
  memory_limit?: number;
  env_vars?: Record<string, string>;
  config?: Record<string, any>;
}

// 更新Agent请求
export interface UpdateAgentRequest {
  name?: string;
  description?: string;
  exchange?: string;
  symbol?: string;
  timeframe?: string;
  trading_mode?: string;
  cpu_limit?: number;
  memory_limit?: number;
  config?: Record<string, any>;
}

// 更新Agent配置请求
export interface UpdateAgentConfigRequest {
  config: Record<string, any>;
}

// 克隆Agent请求
export interface CloneAgentRequest {
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

// Agent状态响应
export interface AgentStatusResponse {
  worker_id: number;
  status: AgentStatus;
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

// Agent指标
export interface AgentMetrics {
  worker_id: number;
  cpu_usage: number;
  memory_usage: number;
  memory_used_mb: number;
  network_in: number;
  network_out: number;
  active_tasks: number;
  timestamp: string;
}

// Agent日志
export interface AgentLog {
  id: number;
  worker_id: number;
  level: string;
  message: string;
  source?: string;
  timestamp: string;
}

// Agent绩效
export interface AgentPerformance {
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
export interface AgentTrade {
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
export interface AgentFilterParams extends PaginationParams {
  status?: AgentStatus;
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

// ==================== UI展示扩展类型 ====================

// 收益率曲线数据点
export interface ReturnRateDataPoint {
  timestamp: string;
  value: number;
}

// 策略绩效指标（前端展示用）
export interface AgentPerformanceMetrics {
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
export interface AgentTradeRecord {
  id: string;
  timestamp: string;
  symbol: string;
  action: 'buy' | 'sell';
  price: number;
  quantity: number;
  amount: number;
  status: 'filled' | 'pending' | 'cancelled';
}

// 扩展 Agent 类型，添加 UI 展示字段
export interface AgentWithPerformance extends Agent {
  totalReturn: number;                    // 总收益率 (%)
  currentReturn: number;                  // 今日收益率 (%)
  startTime?: string;                     // 启动时间
  lastTradeTime?: string;                 // 最后交易时间
  performance: AgentPerformanceMetrics;   // 绩效指标
  tradeRecords: AgentTradeRecord[];       // 交易记录
  returnRateData: ReturnRateDataPoint[];  // 收益率曲线数据
}

// 策略状态文本映射（用于 UI 展示）
export const AgentStatusDisplayText: Record<AgentStatus, string> = {
  [AgentStatus.STOPPED]: '已停止',
  [AgentStatus.RUNNING]: '运行中',
  [AgentStatus.PAUSED]: '已暂停',
  [AgentStatus.ERROR]: '错误',
  [AgentStatus.STARTING]: '启动中',
  [AgentStatus.STOPPING]: '停止中'
};

// 策略状态颜色映射（Ant Design Tag 颜色）
export const AgentStatusTagColor: Record<AgentStatus, string> = {
  [AgentStatus.STOPPED]: 'default',
  [AgentStatus.RUNNING]: 'success',
  [AgentStatus.PAUSED]: 'warning',
  [AgentStatus.ERROR]: 'error',
  [AgentStatus.STARTING]: 'processing',
  [AgentStatus.STOPPING]: 'cyan'
};
