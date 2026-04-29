/**
 * 设置页面类型定义
 */

// 用户配置类型定义
export interface UserSettings {
  username?: string;
  password?: string;
}

// 通用设置类型定义
export interface GeneralSettings {
  theme: 'light' | 'dark' | 'auto';
  language: 'zh-CN' | 'en-US';
  showTips: boolean;
  timezone: string; // 时区配置
  defaultPerPage?: number; // 默认分页大小
  user?: UserSettings; // 用户配置
}

// 保持向后兼容的别名
export type AppearanceSettings = GeneralSettings;

// 通知设置类型定义
export interface NotificationSettings {
  enableEmail: boolean;
  enableWebhook: boolean;
  webhookUrl: string;
  notifyOnAlert: boolean;
  notifyOnTaskComplete: boolean;
  notifyOnSystemUpdate: boolean;
}

// API权限类型定义
export interface ApiPermission {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

// API设置类型定义
export interface ApiSettings {
  apiKey: string;
  permissions: ApiPermission[];
}

// 版本信息类型定义
export interface VersionInfo {
  system_version: string;
  python_version: string;
  build_date: string;
}

// 运行状态类型定义
export interface RunningStatus {
  uptime: string;
  status: string;
  status_color: string;
  last_check: string;
}

// 资源使用类型定义
export interface ResourceUsage {
  cpu_usage: number;
  memory_usage: string;
  disk_space: string;
}

// 系统信息类型定义
export interface SystemInfo {
  version: VersionInfo;
  running_status: RunningStatus;
  resource_usage: ResourceUsage;
  apiVersion?: string;
}

// 配置项类型定义
export interface ConfigItem {
  key: string;
  value: any;
  description: string;
  plugin?: string;
  name?: string;
  type?: string;
  placeholder?: string;
  options?: Array<{ label: string; value: string }>;
}

// 插件配置类型定义
export interface PluginConfig {
  name: string;
  configs: ConfigItem[];
  menuName: string;
}

// 菜单项类型定义
export interface MenuItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
}

// 日志级别枚举
export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error',
  FATAL = 'fatal',
}

// 日志记录类型定义
export interface LogRecord {
  id: string;
  timestamp: string;
  level: LogLevel;
  message: string;
  data?: any;
  source?: string;
}

// 系统指标类型定义（用于系统状态）
export interface SystemMetrics {
  connectionStatus: 'connected' | 'disconnected' | 'error';
  cpuUsage: number;
  memoryUsed: string;
  memoryTotal: string;
  diskUsed: string;
  diskTotal: string;
  lastUpdated: string;
}

// 日志查询参数
export interface LogQueryParams {
  page?: number;
  pageSize?: number;
  level?: LogLevel;
  startTime?: string;
  endTime?: string;
  source?: string;
}

// 日志查询响应
export interface LogQueryResponse {
  records: LogRecord[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}

// ============ 日志文件管理相关类型 ============

/** 日志文件信息 */
export interface LogFileInfo {
  name: string;
  path: string;
  type: 'directory' | 'file';
  size: number;                // 字节数
  size_formatted: string;       // 格式化后的字符串
  modified_time: string;        // ISO格式
  created_time?: string;
  line_count?: number;          // 日志行数（仅文件）
  log_type?: string;             // application/system/api等
  date?: string;                // 文件名中的日期
}

/** 目录树节点 */
export interface LogDirectoryNode {
  name: string;
  path: string;
  type: 'root' | 'directory';
  children: LogDirectoryNode[];
  files: LogFileInfo[];
  total_size: number;
  file_count: number;
}

/** 磁盘使用情况 */
export interface LogDiskUsage {
  total_space: number;          // 字节
  used_space: number;
  free_space: number;
  usage_percent: number;
  log_types: {
    [type: string]: {
      count: number;
      total_size: number;
    };
  };
  logs_total_size?: number;      // 日志总大小
}

/** 自动清理配置 */
export interface LogAutoCleanupConfig {
  enabled: boolean;
  retention_days: number;
  max_size_gb: number;             // 0表示不限制
  cleanup_schedule: 'daily' | 'weekly';
  last_cleanup_time: string | null;
  next_cleanup_time: string | null;
  space_used: number;             // MB
}

/** 清理操作结果 */
export interface CleanupResult {
  success: boolean;
  deleted_files: string[];
  deleted_count: number;
  freed_space: number;            // 字节
  errors: Array<{
    file: string;
    error: string;
  }>;
}
