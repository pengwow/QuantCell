/**
 * 设置页面类型定义
 */

// 用户设置类型定义
export interface UserSettings {
  username: string;
  displayName: string;
  email: string;
  theme: 'light' | 'dark' | 'auto';
  language: 'zh-CN' | 'en-US';
  showTips: boolean;
}

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

// 系统配置类型定义
export interface SystemConfig {
  qlib_data_dir: string;
  max_workers: string;
  data_download_dir: string;
  current_market_type: string;
  crypto_trading_mode: string;
  default_exchange: string;
  default_interval: string;
  default_commission: number;
  default_initial_cash: number;
  proxy_enabled: boolean;
  proxy_url: string;
  proxy_username: string;
  proxy_password: string;
  // 实时模式配置
  realtime_enabled: boolean;
  data_mode: 'realtime' | 'cache';
  frontend_update_interval: number;
  frontend_data_cache_size: number;
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
