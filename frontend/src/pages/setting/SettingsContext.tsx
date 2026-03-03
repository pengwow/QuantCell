/**
 * SettingsContext - 设置页面全局状态管理
 * 用于在设置页面的各个子组件间共享配置数据
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { message } from 'antd';
import { configApi, systemApi } from '../../api';
import type {
  UserSettings,
  NotificationSettings,
  ApiSettings,
  SystemInfo,
  SystemMetrics,
} from './types';

// 默认用户设置
const defaultUserSettings: UserSettings = {
  username: '',
  displayName: '',
  email: '',
  theme: 'light',
  language: 'zh-CN',
  showTips: true,
  timezone: 'Asia/Shanghai',
  defaultPerPage: 10,
};

// 默认通知设置
const defaultNotificationSettings: NotificationSettings = {
  enableEmail: false,
  enableWebhook: false,
  webhookUrl: '',
  notifyOnAlert: false,
  notifyOnTaskComplete: false,
  notifyOnSystemUpdate: false,
};

// 默认 API 设置
const defaultApiSettings: ApiSettings = {
  apiKey: '',
  permissions: [
    { id: 'read', name: '读取', description: '允许读取数据', enabled: true },
    { id: 'write', name: '写入', description: '允许写入数据', enabled: false },
    { id: 'execute', name: '执行', description: '允许执行操作', enabled: false },
  ],
};

// 默认系统信息
const defaultSystemInfo: SystemInfo = {
  version: {
    system_version: '1.0.0',
    python_version: '3.10.0',
    build_date: '2025-01-01',
  },
  running_status: {
    uptime: '0天0小时0分钟',
    status: '运行中',
    status_color: 'green',
    last_check: '2025-01-01 00:00:00',
  },
  resource_usage: {
    cpu_usage: 0,
    memory_usage: '0 MB',
    disk_space: '0 GB',
  },
};

// 默认系统指标
const defaultSystemMetrics: SystemMetrics = {
  connectionStatus: 'connected',
  cpuUsage: 0,
  memoryUsed: '0 GB',
  memoryTotal: '0 GB',
  diskUsed: '0 GB',
  diskTotal: '0 GB',
  lastUpdated: new Date().toISOString(),
};

// Context 类型定义
interface SettingsContextType {
  // 状态
  userSettings: UserSettings;
  notificationSettings: NotificationSettings;
  apiSettings: ApiSettings;
  systemInfo: SystemInfo;
  systemMetrics: SystemMetrics;
  loading: boolean;
  saving: boolean;

  // 设置状态的方法
  setUserSettings: React.Dispatch<React.SetStateAction<UserSettings>>;
  setNotificationSettings: React.Dispatch<React.SetStateAction<NotificationSettings>>;
  setApiSettings: React.Dispatch<React.SetStateAction<ApiSettings>>;
  setSystemMetrics: React.Dispatch<React.SetStateAction<SystemMetrics>>;

  // 操作方法
  loadConfig: () => Promise<void>;
  saveConfig: () => Promise<void>;
  resetConfig: () => void;
  applyTheme: (theme: 'light' | 'dark' | 'auto') => void;
  refreshSystemMetrics: () => Promise<void>;
}

// 创建 Context
const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

// Provider 组件
interface SettingsProviderProps {
  children: ReactNode;
}

export const SettingsProvider = ({ children }: SettingsProviderProps) => {
  const [userSettings, setUserSettings] = useState<UserSettings>(defaultUserSettings);
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings>(defaultNotificationSettings);
  const [apiSettings, setApiSettings] = useState<ApiSettings>(defaultApiSettings);
  const [systemInfo, setSystemInfo] = useState<SystemInfo>(defaultSystemInfo);
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics>(defaultSystemMetrics);
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  // 应用主题
  const applyTheme = useCallback((theme: 'light' | 'dark' | 'auto') => {
    const root = document.documentElement;
    if (theme === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    } else {
      root.setAttribute('data-theme', theme);
    }
  }, []);

  // 刷新系统指标
  const refreshSystemMetrics = useCallback(async () => {
    try {
      const metrics = await systemApi.getSystemMetrics();
      setSystemMetrics(metrics);
    } catch (error) {
      console.error('获取系统指标失败:', error);
    }
  }, []);

  // 加载配置
  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const response = await configApi.getConfig();

      // 处理后端返回的配置格式（可能是扁平的键值对）
      const config = response?.data || response;

      // 如果是扁平格式，转换为嵌套格式
      const flattenConfig: Record<string, any> = {};
      if (config && typeof config === 'object') {
        Object.entries(config).forEach(([key, value]) => {
          flattenConfig[key] = value;
        });
      }

      // 从扁平配置中提取用户设置
      const loadedUserSettings: Partial<UserSettings> = {
        theme: flattenConfig['user.theme'] || flattenConfig['theme'],
        language: flattenConfig['user.language'] || flattenConfig['language'],
        defaultPerPage: flattenConfig['user.defaultPerPage'] || flattenConfig['defaultPerPage'],
        showTips: flattenConfig['user.showTips'] || flattenConfig['showTips'],
        timezone: flattenConfig['user.timezone'] || flattenConfig['timezone'],
      };

      // 过滤掉 undefined 值
      const filteredUserSettings = Object.fromEntries(
        Object.entries(loadedUserSettings).filter(([, v]) => v !== undefined)
      ) as Partial<UserSettings>;

      if (Object.keys(filteredUserSettings).length > 0) {
        setUserSettings(prev => ({ ...prev, ...filteredUserSettings }));
        applyTheme(filteredUserSettings.theme || 'light');
      }

      // 从扁平配置中提取通知设置
      const loadedNotificationSettings: Partial<NotificationSettings> = {
        enableEmail: flattenConfig['notification.enableEmail'],
        enableWebhook: flattenConfig['notification.enableWebhook'],
        webhookUrl: flattenConfig['notification.webhookUrl'],
        notifyOnAlert: flattenConfig['notification.notifyOnAlert'],
        notifyOnTaskComplete: flattenConfig['notification.notifyOnTaskComplete'],
        notifyOnSystemUpdate: flattenConfig['notification.notifyOnSystemUpdate'],
      };

      const filteredNotificationSettings = Object.fromEntries(
        Object.entries(loadedNotificationSettings).filter(([, v]) => v !== undefined)
      ) as Partial<NotificationSettings>;

      if (Object.keys(filteredNotificationSettings).length > 0) {
        setNotificationSettings(prev => ({ ...prev, ...filteredNotificationSettings }));
      }

      // 从扁平配置中提取 API 设置
      const loadedApiSettings: Partial<ApiSettings> = {
        apiKey: flattenConfig['api.apiKey'],
      };

      const filteredApiSettings = Object.fromEntries(
        Object.entries(loadedApiSettings).filter(([, v]) => v !== undefined)
      ) as Partial<ApiSettings>;

      if (Object.keys(filteredApiSettings).length > 0) {
        setApiSettings(prev => ({ ...prev, ...filteredApiSettings }));
      }

      // 更新系统信息（如果后端返回）
      if (config.systemInfo) {
        setSystemInfo(prev => ({ ...prev, ...config.systemInfo }));
      }

      // 获取系统指标
      await refreshSystemMetrics();
    } catch (error) {
      console.error('加载配置失败:', error);
      message.error('加载配置失败');
    } finally {
      setLoading(false);
    }
  }, [applyTheme, refreshSystemMetrics]);

  // 保存配置
  const saveConfig = useCallback(async () => {
    try {
      setSaving(true);

      // 将嵌套配置转换为后端期望的配置项对象列表格式，只包含前端实际使用的配置
      const configList = [
        // 用户设置 (AppearanceSettingsPage, BasicSettingsPage)
        { key: 'theme', value: userSettings.theme, name: '主题', description: '系统主题设置' },
        { key: 'language', value: userSettings.language, name: '语言', description: '系统语言设置' },
        { key: 'defaultPerPage', value: String(userSettings.defaultPerPage), name: '默认分页', description: '列表页默认显示数量' },
        { key: 'timezone', value: userSettings.timezone, name: '时区', description: '系统默认时区' }
      ];

      await configApi.updateConfig(configList);

      // 更新全局配置
      if (typeof window !== 'undefined') {
        (window as any).APP_CONFIG = {
          ...(window as any).APP_CONFIG,
          userSettings,
          notificationSettings,
          apiSettings,
        };
      }

      message.success('设置保存成功');
    } catch (error) {
      console.error('保存配置失败:', error);
      message.error('保存配置失败');
    } finally {
      setSaving(false);
    }
  }, [userSettings, notificationSettings, apiSettings]);

  // 重置配置
  const resetConfig = useCallback(() => {
    setUserSettings(defaultUserSettings);
    setNotificationSettings(defaultNotificationSettings);
    setApiSettings(defaultApiSettings);
    setSystemMetrics(defaultSystemMetrics);
    applyTheme(defaultUserSettings.theme);
    message.success('设置已重置为默认值');
  }, [applyTheme]);

  // 组件挂载时加载配置
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const value: SettingsContextType = {
    userSettings,
    notificationSettings,
    apiSettings,
    systemInfo,
    systemMetrics,
    loading,
    saving,
    setUserSettings,
    setNotificationSettings,
    setApiSettings,
    setSystemMetrics,
    loadConfig,
    saveConfig,
    resetConfig,
    applyTheme,
    refreshSystemMetrics,
  };

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
};

// 自定义 Hook
export const useSettings = (): SettingsContextType => {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
