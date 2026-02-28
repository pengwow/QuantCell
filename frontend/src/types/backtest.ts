/**
 * 回测模块类型定义
 * 集中管理回测相关的所有类型接口
 */

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
  default: any;
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
    params?: Record<string, any>;
  };
  metrics: BacktestMetric[];
  equity_curve: EquityData[];
  trades: Trade[];
  status: string;
  created_at: string;
}

// 回放数据类型
export interface ReplayData {
  klines: any[];
  trades: any[];
  equity_curve: any[];
  strategy_name: string;
  backtest_config: any;
  symbol: string;
  interval: string;
}

// 合并结果摘要类型
export interface MergeSummary {
  total_currencies: number;
  successful_currencies: number;
  failed_currencies: number;
  total_trades: number;
  average_trades_per_currency: number;
  total_initial_cash: number;
  total_equity: number;
  total_return: number;
  average_return: number;
  average_max_drawdown: number;
  average_sharpe_ratio: number;
  average_sortino_ratio: number;
  average_calmar_ratio: number;
  average_win_rate: number;
  average_profit_factor: number;
}

// 货币对信息类型
export interface SymbolInfo {
  symbol: string;
  status: string;
  message: string;
}

// 回测货币对列表数据类型
export interface BacktestSymbols {
  symbols: SymbolInfo[];
  total: number;
}

// 进度状态类型
export type StepStatus = 'wait' | 'process' | 'finish' | 'error';

// 进度数据接口
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
