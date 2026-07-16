/**
 * 数据管理相关类型定义
 * 从旧版本迁移过来
 */

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
 * 归档数据种类（共 7 种）
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

/** 3 个 K 线类（需要 interval 参数） */
export const KLINE_ARCHIVE_KINDS: ArchiveKind[] = [
  'markPriceKlines',
  'indexPriceKlines',
  'premiumIndexKlines',
];

/** 3 个市场 */
export const ARCHIVE_MARKETS: MarketType[] = ['spot', 'um', 'cm'];

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
