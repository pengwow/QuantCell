/**
 * 回测模块类型定义
 * 集中管理回测相关的所有类型接口
 */

// 回放数据中的 K 线原始字段（后端字段名与前端类型存在差异，按 index signature 兜底）
export interface ReplayKline {
  time?: string | number;
  timestamp?: number | string;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
  [key: string]: unknown;
}

// 回放数据中的交易原始字段
export interface ReplayRawTrade {
  trade_id?: string;
  timestamp?: number;
  formatted_time?: string;
  side?: string;
  direction?: string;
  price?: number;
  quantity?: number;
  volume?: number;
  commission?: string | number;
  status?: string;
  instrument_id?: string;
  [key: string]: unknown;
}

// 交易数据接口
export interface Trade {
  EntryTime: string;
  ExitTime: string;
  Direction: string;
  EntryPrice: number;
  ExitPrice: number;
  Size: number;
  PnL: number;
  ReturnPct: number;
}

// 权益数据接口
export interface EquityData {
  datetime: string;
  Equity: number;
}

// 回测指标接口
export interface BacktestMetric {
  name: string;
  key: string;
  value: number | string;
}

// 回测配置接口
export interface BacktestConfig {
  symbols: string[];
  start_time: string;
  end_time: string;
  interval: string;
  initial_cash: number;
  commission: number;
}

// 策略参数接口
export interface StrategyParam {
  name: string;
  type: string;
  default: unknown;
  description: string;
  required: boolean;
}

// 策略接口
export interface Strategy {
  name: string;
  file_name: string;
  file_path: string;
  description: string;
  version: string;
  tags?: string[];
  params: StrategyParam[];
  created_at: string;
  updated_at: string;
}

// 回测任务接口
export interface BacktestTask {
  id: string;
  strategy_name: string;
  created_at: string;
  status: string;
  total_return?: number;
  max_drawdown?: number;
}

// 回测详情数据接口
export interface BacktestDetailData {
  id: string;
  strategy_name: string;
  backtest_config: BacktestConfig;
  strategy_config?: {
    params?: Record<string, unknown>;
  };
  metrics: BacktestMetric[];
  equity_curve: EquityData[];
  trades: Trade[];
  status: string;
  created_at: string;
}

// 回放交易数据（后端回测引擎字段）
export interface ReplayTrade {
  trade_id: string;
  timestamp?: number;
  formatted_time?: string;
  side?: string;
  direction?: string;
  price?: number;
  quantity?: number;
  volume?: number;
  commission?: string | number;
  status?: string;
  instrument_id?: string;
  [key: string]: unknown;
}

// 回放数据类型（字段与后端 /replay 接口返回保持宽松兼容）
export interface ReplayData {
  klines: ReplayKline[];
  trades: ReplayTrade[];
  equity_curve: Array<{
    date?: string;
    datetime?: string;
    equity?: number;
    [key: string]: unknown;
  }>;
  strategy_name: string;
  backtest_config: Partial<BacktestConfig> & {
    symbol?: string;
    interval?: string;
  };
  symbol: string;
  interval: string;
}

// 货币对信息类型
export interface SymbolInfo {
  symbol: string;
  status: string;
  message: string;
}

// 回测货币对列表数据类型
// 后端返回数据结构: { symbols: ["ETH/USDT", "BTC/USDT"], total: 2 }
export interface BacktestSymbols {
  symbols: string[];
  total: number;
}

// 进度状态类型
export type StepStatus = 'wait' | 'process' | 'finish' | 'error';

// 阶段状态类型
export type StageStatus = 'pending' | 'running' | 'completed' | 'failed';

// 当前阶段类型
export type CurrentStage = 'data_prep' | 'execution' | 'analysis' | 'completed';

// 数据准备步骤类型
export type DataPrepStep = 'checking' | 'downloading' | 'loading';

// 下载进度信息
export interface DownloadProgressInfo {
  symbol: string;
  progress: number;
}

// 数据准备阶段进度
export interface DataPrepProgress {
  status: StageStatus;
  progress: number;
  current_step: DataPrepStep;
  checked_symbols: number;
  total_symbols: number;
  downloading?: DownloadProgressInfo;
  message?: string;
}

// 执行阶段进度
export interface ExecutionProgress {
  status: StageStatus;
  progress: number;
  current_symbol: string;
  completed_symbols: number;
  total_symbols: number;
  message?: string;
}

// 结果统计阶段进度
export interface AnalysisProgress {
  status: StageStatus;
  progress: number;
  message?: string;
}

// 错误信息
export interface ErrorInfo {
  stage: string;
  message: string;
}

// 后端返回的进度数据接口
export interface BacktestProgressData {
  task_id: string;
  status: StageStatus;
  current_stage: CurrentStage;
  overall_progress: number;
  data_prep: DataPrepProgress;
  execution: ExecutionProgress;
  analysis: AnalysisProgress;
  error?: ErrorInfo;
  created_at: string;
  updated_at: string;
}

// 进度数据接口（兼容旧版本）
export interface ProgressData {
  overall: number;
  dataPrep?: {
    percent: number;
    downloading?: boolean;
    downloadProgress?: number;
  };
  execution?: {
    percent: number;
    current: number;
    total: number;
    currentSymbol?: string;
  };
}

// 步骤状态接口
export interface StepStatusState {
  dataPrep: StepStatus;
  execution: StepStatus;
  analysis: StepStatus;
}
