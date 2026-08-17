/**
 * 数据管理相关类型定义
 * 从旧版本迁移过来
 */

/**
 * 任务状态类型定义
 */
export type TaskStatus = 'running' | 'completed' | 'failed' | 'pending' | 'canceled';

/**
 * 任务进度信息
 */
export interface TaskProgressInfo {
  percentage: number;
  total: number;
  completed: number;
  failed: number;
  current: string;
  message?: string;
}

/**
 * 任务类型定义（与后端 Task 模型对齐）
 */
export interface Task {
  task_id: string;
  status: TaskStatus;
  task_type: string;
  params: Record<string, any>;
  progress: TaskProgressInfo;
  start_time?: string;
  end_time?: string;
  error_message?: string;
  created_at: string;
  updated_at?: string;
  /** @deprecated 使用 progress.percentage */
  completed_at?: string;
  log?: string[];
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

/**
 * 品种选项类型定义
 */
export interface SymbolOption {
  value: string;
  label: string;
  type: 'data_pool' | 'direct_symbol';
  symbols?: string[];
}

/**
 * K线数据类型定义
 */
export interface KlineData {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * 数据质量报告类型定义
 */
export interface QualityReport {
  symbol: string;
  interval: string;
  total_records: number;
  missing_records: number;
  duplicate_records: number;
  completeness: number;
  start_time: string;
  end_time: string;
}

// ==================== Binance 归档采集类型 ====================

/**
 * 归档数据种类（7 种）
 * - aggTrades/trades/bookDepth/bookTicker 为非 K 线类，无需 interval
 * - markPriceKlines/indexPriceKlines/premiumIndexKlines 为 K 线类，必须传 interval
 */
export type ArchiveKind =
  | 'aggTrades'
  | 'trades'
  | 'bookDepth'
  | 'bookTicker'
  | 'markPriceKlines'
  | 'indexPriceKlines'
  | 'premiumIndexKlines';

/**
 * 衍生数据种类（2 种）——仅期货 market（um / cm）
 */
export type DerivKind = 'fundingRate' | 'openInterest';

/**
 * K线类数据（传统 K 线数据接口获取）
 */
export type KlineKind = 'kline';

/**
 * 统一数据种类：涵盖全部 10 种
 */
export type DataKind = ArchiveKind | DerivKind | KlineKind;

/**
 * 市场类型（spot=现货 / um=USDT 永续 / cm=币本位永续）
 */
export type MarketType = 'spot' | 'um' | 'cm';

/** 全部 7 种归档种类，按 UI 展示顺序 */
export const ARCHIVE_KINDS: ArchiveKind[] = [
  'aggTrades',
  'trades',
  'bookDepth',
  'bookTicker',
  'markPriceKlines',
  'indexPriceKlines',
  'premiumIndexKlines',
];

/** 2 种衍生数据种类 */
export const DERIV_KINDS: DerivKind[] = ['fundingRate', 'openInterest'];

/** 仅期货（非 spot）market 可用的数据种类 */
export const FUTURES_ONLY_KINDS: DataKind[] = [
  'markPriceKlines',
  'indexPriceKlines',
  'premiumIndexKlines',
  'fundingRate',
  'openInterest',
];

/** 需要 interval 参数的数据种类 */
export const INTERVAL_REQUIRED_KINDS: DataKind[] = [
  'kline',
  'markPriceKlines',
  'indexPriceKlines',
  'premiumIndexKlines',
];

/** 数据种类的中文名称映射 */
export const DATA_KIND_LABEL: Record<DataKind, string> = {
  kline: 'K线数据',
  aggTrades: '归集交易',
  trades: '逐笔交易',
  bookDepth: '深度快照',
  bookTicker: '最优挂单',
  markPriceKlines: '标记价格K线',
  indexPriceKlines: '指数价格K线',
  premiumIndexKlines: '溢价指数K线',
  fundingRate: '资金费率',
  openInterest: '持仓量',
};

/** 数据种类的分组（用于 UI 分组展示） */
export const DATA_KIND_GROUPS: Array<{
  key: 'kline' | 'archive' | 'deriv';
  label: string;
  kinds: DataKind[];
}> = [
  { key: 'kline', label: 'K线数据', kinds: ['kline'] },
  { key: 'archive', label: '行情数据', kinds: ['aggTrades', 'trades', 'bookDepth', 'bookTicker', 'markPriceKlines', 'indexPriceKlines', 'premiumIndexKlines'] },
  { key: 'deriv', label: '衍生品指标', kinds: ['fundingRate', 'openInterest'] },
];

/** 3 个 K 线类（需要 interval 参数） */
export const KLINE_ARCHIVE_KINDS: ArchiveKind[] = [
  'markPriceKlines',
  'indexPriceKlines',
  'premiumIndexKlines',
];

/** 3 个市场 */
export const ARCHIVE_MARKETS: MarketType[] = ['spot', 'um', 'cm'];

/** market 中文名称 */
export const MARKET_LABEL: Record<MarketType, string> = {
  spot: '现货',
  um: 'USDT永续',
  cm: '币本位永续',
};

/** K 线类支持的 interval 列表 */
export const ARCHIVE_INTERVALS: string[] = [
  '1m',
  '3m',
  '5m',
  '15m',
  '30m',
  '1h',
  '2h',
  '1d',
];

/**
 * 创建归档下载任务的请求体（与后端 DownloadRequest 对齐）
 */
export interface ArchiveTaskRequest {
  symbols: string[];
  kind: ArchiveKind;
  market: MarketType;
  start_date: string; // YYYY-MM-DD
  end_date: string; // YYYY-MM-DD
  mode: 'inc' | 'full';
  /** K 线类必填；非 K 线类传 undefined */
  interval?: string;
}

/**
 * 归档数据行（duck typing：aggTrades/trades/bookDepth 等字段不固定）
 * 统一用宽松的 string|number|boolean|null 表示，避免每个 kind 写一套
 */
export interface ArchiveRow {
  [key: string]: string | number | boolean | null;
}

/**
 * _meta.json 内容（collector 写入的元信息）
 */
export interface ArchiveMeta {
  symbol: string;
  kind: string;
  market: string;
  earliest_date: string;
  latest_date: string;
  total_rows: number;
  file_count: number;
  corrupt_dates: string[];
  updated_at: string;
}
