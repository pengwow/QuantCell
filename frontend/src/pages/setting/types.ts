/**
 * 设置页面类型定义
 */

// 通用设置类型定义
export interface GeneralSettings {
  theme: 'light' | 'dark' | 'auto';
  language: 'zh-CN' | 'en-US';
  showTips: boolean;
  timezone: string; // 时区配置
  defaultPerPage?: number; // 默认分页大小
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
