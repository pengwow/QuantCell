import { apiRequest } from './index';

// 与后端 api/rl_routes.py 的 TrainRequest 对齐：symbol 必填，其余有默认值
export interface RLTrainRequest {
  algorithm?: string;
  symbol: string;
  interval?: string;
  candle_type?: string;
  start?: string | null;
  end?: string | null;
  total_timesteps?: number;
  reward_type?: string;
  walk_forward?: boolean;
  wf_splits?: number;
}

export interface RLTrainResult {
  model_id: string;
  status: string;
  metrics: Record<string, number>;
  walk_forward?: unknown;
}

// 与后端 RLService.list_saved_models() 对齐：data/models 下真实 .zip 文件
export interface RLModelInfo {
  name: string;
  path: string;
  size_mb: number;
  created: number;
}

// 与后端 api/rl_routes.py 的 RLBacktestRequest 对齐：model_id 为 data/models 下 .zip 文件 stem；
// 引擎固定统一内核（与实盘同一条主回路），不再提供 engine / reward_type 选项
export interface RLBacktestRequest {
  model_id: string;
  symbol: string;
  interval?: string;
  candle_type?: string;
  initial_capital?: number;
  // 非空时跑集成员聚合回测，model_id 仅作兜底
  ensemble_id?: string;
}

// 后端 run_backtest_task 返回的任务化摘要：结果按策略回测同一契约落盘，
// 凭 task_id 打开详情抽屉 / 详情页（backtestApi.getBacktestDetail）
export interface RLBacktestResult {
  task_id: number | string;
  strategy_name: string;
  engine: string; // 固定 "kernel"
  symbol: string;
  interval: string;
  data_bars: number;
  total_pnl: number;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate: number;
  num_trades: number;
}

export const rlApi = {
  train: (data: RLTrainRequest) =>
    apiRequest.post<RLTrainResult>('/rl/train', data),
  listModels: () =>
    apiRequest.get<RLModelInfo[]>('/rl/models'),
  deleteModel: (name: string) =>
    apiRequest.delete(`/rl/models/${encodeURIComponent(name)}`),
  // 同步回测（kernel 秒级）也可能跑几分钟：timeout:0 关闭 axios 默认超时（与 backtestApi.runBacktest 同策略）
  backtest: (data: RLBacktestRequest) =>
    apiRequest.post<RLBacktestResult>('/rl/backtest', data, { timeout: 0 }),
};