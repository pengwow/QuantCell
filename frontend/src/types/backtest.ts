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

// 逐笔成交（引擎 fill_detail 关联后的展示契约）
export interface TradeFill {
  fill_id: number;
  side: 'buy' | 'sell';
  offset: 'open' | 'close';
  price: number;
  quantity: number;
  timestamp: number;
  formatted_time: string;
  status: 'filled';
}

// 交易数据接口（round-trip 成交契约，与后端 _format_round_trip_trades 输出一一对应）
// 注意：2026-07-25 起引擎只产出该格式；旧结果无成交明细，由详情页空态提示
// 2026-10-20 契约调整：side → entry_side，新增 exit_side / direction 语义（多空）/ fills
export interface Trade {
  trade_id: string;
  symbol: string;
  timestamp: number;        // 开仓时间（秒级）
  formatted_time: string;   // 开仓展示时间
  entry_time: string;       // 开仓 ISO UTC
  exit_time: string | null;       // 平仓 ISO UTC（未配对行无平仓 → null）
  exit_timestamp: number | null;  // 平仓时间（秒级）
  entry_price: number;
  exit_price: number;
  size: number;
  pnl: number;
  return_pct: number;
  direction: 'long' | 'short' | null;   // 持仓方向；null = 未配对（Worker 分组视图）
  entry_side: 'buy' | 'sell';    // 开仓方向
  exit_side: 'buy' | 'sell';     // 平仓方向
  status: 'closed' | 'unpaired';        // 回测恒为 closed
  entry_fill_ids: number[];      // 构成该持仓的开仓 fill id
  exit_fill_ids: number[];       // 平仓 fill id 列表（FLAT_TO_FLAT 下可能多条）
  fills: TradeFill[];            // 逐笔成交明细
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
  capital_mode?: 'per_symbol' | 'shared';   // 资金使用方式：各品种独立资金池 / 组合共享资金池
}

// 策略参数接口
export interface StrategyParam {
  name: string;
  type: string;
  default: unknown;
  description: string;
  required: boolean;
  options?: string[]; // 下拉选项（type=select 时使用）
}

// 策略因子接口
export interface StrategyFactor {
  name: string;
  type?: string;
  description?: string;
  default?: unknown;
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
  factors?: StrategyFactor[];
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
  /** /backtest/list 行附带字段（RL 回测历史页展示参数用；老页面未引用） */
  symbols?: string;
  timeframes?: string;
  engine_type?: string;
  updated_at?: string;
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
  /** 逐笔成交明细（fill 粒度）：round-trip 稀疏时（如 RL 目标仓位策略）详情页兜底展示 */
  fills_detail?: BacktestFill[];
  status: string;
  created_at: string;
}

/** 逐笔成交展示行（后端 rl_service fill_rows 契约） */
export interface BacktestFill {
  fill_id: number;
  /** 秒级 Unix 时间戳 */
  timestamp: number;
  formatted_time: string;
  /** Taker 方向：buy / sell */
  side: 'buy' | 'sell';
  price: number;
  quantity: number;
}

/** cascade 决策轻列表行（回测 / Worker 决策报告共用；后端 decisions 字段契约） */
export interface CascadeDecisionRecord {
  _seq?: number;          // 录制 JSONL 原始行号，详情弹窗定位键；旧任务无此字段不显示详情按钮
  fingerprint?: string;
  action: string;         // buy / sell / hold
  confidence: number;     // 0.0 ~ 1.0
  probabilities?: Record<string, number>;
  source: string;         // sdm_direct / fallback
  fallback_reason?: string;
  sdm_usage?: unknown;
  sub_signals?: Record<string, unknown>;
  _ts?: string;           // ISO 8601 录制时间
  _s1_model?: string;
  _s2_model?: string;
  _decider?: string;      // 录制侧标注的实际决策者（S1:xxx / S2:xxx / 规则 / 回放）
}

/** 决策录制行完整结构（与 backend/strategy/decision_recording.py 的 JSONL 契约对应） */
export interface DecisionDetailRecord {
  fingerprint: string;
  decision: Record<string, unknown>;
  state: Record<string, unknown>;
  questions: Record<string, unknown>;
  ts: string;
  _decider?: string;
  meta?: Record<string, unknown>;
  s1_raw?: string;
  s2_raw?: string;
  s2_thinking?: string;
}

// 回放交易数据：契约同 Trade，保留 index signature 兜底后端附加字段
export type ReplayTrade = Trade & { [key: string]: unknown };

// ---- 回测因子（与后端结果 JSON 的 factors 字段对应）----
// 列式时序：timestamps（毫秒 epoch）/ formatted_times 为公共轴，每个因子名对应一列值。
// attribution 回放页用不到，保持 unknown（详情页有自己的完整定义）。
export interface FactorTimeSeries {
  timestamps: number[];
  formatted_times: string[];
  // 每因子一列值（后端 NaN 序列化为 null，故数值列元素允许 null）
  [factorName: string]: Array<number | null> | Array<string | null> | null;
}

export interface BacktestFactors {
  names: string[];
  thresholds: Record<string, { buy?: number; sell?: number }>;
  time_series: FactorTimeSeries;
  trade_factors: Array<Record<string, number | string | null>>;
  attribution: Record<string, unknown>;
}

// 因子快照面板单行
export interface FactorSnapshotRow {
  name: string;
  value: number | null;   // null 表示该 bar 无值（NaN）
  buy?: number;
  sell?: number;
  signal: 'long' | 'short' | 'neutral' | 'none';  // none: 无阈值或无值，只显示数值
}

// 生效保证金规格：引擎回显实际生效值（含档位来源）；旧任务回退配置时没有 bracket_source。
// 详情页与回放页（单品种/组合）共用，交易表「保证金占用」列的杠杆来源
export interface EffectiveMarginSpec {
  symbol: string;
  leverage: number;
  margin_mode?: 'isolated' | 'cross';
  bracket_source?: 'db' | 'snapshot' | 'default';
}

// 详情/回放三处共用的「保证金占用」列杠杆表构造：
// 仅启用保证金（margin_applied=true）时返回 symbol -> leverage 映射，否则 undefined（表格不渲染该列）
export const buildLeverageMap = (
  marginApplied: boolean | undefined,
  specs: EffectiveMarginSpec[] | undefined
): Record<string, number> | undefined =>
  marginApplied && specs?.length
    ? Object.fromEntries(specs.map((item) => [item.symbol, item.leverage]))
    : undefined;

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
  factors?: BacktestFactors | null;
  // 生效保证金回显：与 /detail 同源；仅启用保证金时回放交易表显示「保证金占用」列
  margin_applied?: boolean;
  margin_specs_effective?: EffectiveMarginSpec[];
}

// 货币对信息类型
export interface SymbolInfo {
  symbol: string;
  status: string;
  message: string;
}

// ---- 全局视角（组合）回放 ----
// 账户稀疏点：[t(ms), equity, balance, margin, cum_pnl, drawdown, day_pnl]
export type PortfolioAccountPoint = [number, number, number, number, number, number, number];

// 成交流重建的单笔持仓事件（成交后净持仓状态）
export interface PortfolioPositionEvent {
  t: number;          // 归属网格点（ms）
  ts: number;         // 成交时间（秒）
  symbol: string;
  side: string;       // BUY / SELL
  qty: number;        // 成交后净持仓（正多 / 负空 / 0 平仓）
  traded_qty: number; // 本次成交数量（带方向）
  avg_cost: number;   // 成交后持仓均价
  price: number;      // 成交价
  pnl: number;        // 平仓/减仓实现盈亏
}

export interface PortfolioReplayData {
  symbols: string[];
  interval: string;
  init_cash: number;
  start_ms: number;       // 统一网格起点（ms）
  end_ms: number;         // 统一网格终点（ms）
  grid_count: number;     // 网格点数（等距，不回传全量）
  grid_step_ms: number;   // 网格步长（ms）
  account: PortfolioAccountPoint[];
  position_events: PortfolioPositionEvent[];
  // 持仓期收盘价点（仅净持仓非零网格）：{ symbol: [[t(ms), close], ...] }
  holding_prices: Record<string, Array<[number, number]>>;
  trades: ReplayTrade[];
  capital_mode?: 'per_symbol' | 'shared';   // 本次回测的资金使用方式，供口径说明按模式渲染
  // 生效保证金回显：与单品种 /replay 口径一致；仅启用保证金时显示「保证金占用」列
  margin_applied?: boolean;
  margin_specs_effective?: EffectiveMarginSpec[];
}

// 回测货币对列表数据类型
// 后端返回数据结构: { symbols: ["ETH/USDT", "BTC/USDT"], total: 2 }
export interface BacktestSymbols {
  symbols: string[];
  total: number;
}

// 进度状态类型
export type StepStatus = 'wait' | 'process' | 'finish' | 'error';

// 阶段状态类型（stopped = 用户终止后的终态，与后端 StageStatus.STOPPED 对齐）
export type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'stopped';

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
