/**
 * 策略执行历史记录类型
 */
export interface ExecutionHistory {
  timestamp: string;
  status: 'success' | 'failed';
}

/**
 * 交易记录类型定义
 */
export interface TradeRecord {
  id: string;
  timestamp: string;
  symbol: string;
  action: 'buy' | 'sell';
  price: number;
  quantity: number;
  amount: number;
  status: 'filled' | 'pending' | 'canceled';
}

/**
 * 收益率数据点类型
 */
export interface ReturnRatePoint {
  timestamp: string;
  value: number;
}

/**
 * 策略性能指标类型
 */
export interface StrategyPerformance {
  winRate: number;
  profitLossRatio: number;
  maxDrawdown: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  totalProfit: number;
  totalLoss: number;
  averageProfit: number;
  averageLoss: number;
  sharpeRatio: number;
  sortinoRatio: number;
  calmarRatio: number;
}

/**
 * 策略类型定义
 */
export interface Strategy {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'inactive' | 'paused';
  statusText: string;
  createdAt: string;
  updatedAt: string;
  createdBy: string;
  executionFrequency: string;
  ruleCount: number;
  executionHistory: ExecutionHistory[];
  // 量化交易相关字段
  currentReturn: number;
  totalReturn: number;
  startTime: string;
  lastTradeTime: string;
  tradeRecords: TradeRecord[];
  returnRateData: ReturnRatePoint[];
  performance: StrategyPerformance;
}

/**
 * 菜单项类型定义
 */
export interface MenuItem {
  id: string;
  title: string;
  icon: string;
}

/**
 * 加密货币数据类型定义
 */
export interface CryptoCurrency {
  id: string;
  name: string;
  symbol: string;
  currentPrice: number;
  priceChange24h: number;
  marketCap: number;
  tradingVolume: number;
}

/**
 * 股票数据类型定义
 */
export interface Stock {
  symbol: string;
  companyName: string;
  currentPrice: number;
  priceChange: number;
  priceChangePercent: number;
  openPrice: number;
  highPrice: number;
  lowPrice: number;
}

/**
 * 导入表单数据类型定义
 */
export interface ImportForm {
  dataType: string;
  exchange: string;
  startDate: string;
  endDate: string;
  interval: string;
  symbols: string;
}

/**
 * 数据质量检查表单数据类型定义
 */
export interface QualityForm {
  dataType: string;
  symbol: string;
  startDate: string;
  endDate: string;
}

/**
 * 数据质量检查结果类型定义
 */
export interface QualityResult {
  totalRows: number;
  missingValues: number;
  outliers: number;
  completeness: number;
  details: string;
}

/**
 * 数据可视化表单数据类型定义
 */
export interface VizForm {
  dataType: string;
  symbol: string;
  startDate: string;
  endDate: string;
  chartType: string;
  indicator: string;
}

/**
 * 数据采集表单数据类型定义
 */
export interface CollectionForm {
  symbols: string[];
  interval: string[];
  start: string;
  end: string;
  exchange: string;
  max_workers: number;
  candle_type: string;
}

/**
 * 任务状态类型定义
 */
export type TaskStatus = 'running' | 'completed' | 'failed' | 'pending' | 'canceled';

/**
 * 任务类型定义
 */
export interface Task {
  task_id: string;
  status: TaskStatus;
  task_type: string;
  params: any;
  created_at: string;
  completed_at?: string;
  progress?: {
    percentage: number;
    message?: string;
  };
  log?: string[];
}

/**
 * 数据池类型定义
 */
export interface DataPool {
  id: string;
  name: string;
  description: string;
  assetCount: number;
  createdAt: string;
}

/**
 * 资产类型定义
 */
export interface Asset {
  id: string;
  name: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
}

/**
 * 定时任务类型定义
 */
export interface ScheduledTask {
  id: number;
  name: string;
  description: string | null;
  task_type: string;
  status: string;
  cron_expression: string | null;
  interval: string | null;
  start_time: string | null;
  end_time: string | null;
  frequency_type: string;
  symbols: string[] | null;
  exchange: string | null;
  candle_type: string;
  save_dir: string | null;
  max_workers: number;
  incremental_enabled: boolean;
  last_collected_date: string | null;
  notification_enabled: boolean;
  notification_type: string | null;
  notification_email: string | null;
  notification_webhook: string | null;
  last_run_time: string | null;
  next_run_time: string | null;
  last_result: string | null;
  error_message: string | null;
  run_count: number;
  success_count: number;
  fail_count: number;
  created_at: string;
  updated_at: string;
  created_by: string;
}
