/**
 * SettingsContext - 设置页面全局状态管理
 * 用于在设置页面的各个子组件间共享配置数据
 */
import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { App } from 'antd';
import { configApi, systemApi } from '../../api';
import type {
  GeneralSettings,
  NotificationSettings,
  ApiSettings,
  SystemInfo,
  SystemMetrics,
} from './types';

// 默认通用设置
const defaultGeneralSettings: GeneralSettings = {
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
  generalSettings: GeneralSettings;
  notificationSettings: NotificationSettings;
  apiSettings: ApiSettings;
  systemInfo: SystemInfo;
  systemMetrics: SystemMetrics;
  loading: boolean;
  saving: boolean;

  // 设置状态的方法
  setGeneralSettings: React.Dispatch<React.SetStateAction<GeneralSettings>>;
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
  const { message } = App.useApp();
  const [generalSettings, setGeneralSettings] = useState<GeneralSettings>(defaultGeneralSettings);
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings>(defaultNotificationSettings);
  const [apiSettings, setApiSettings] = useState<ApiSettings>(defaultApiSettings);
  const [systemInfo, _setSystemInfo] = useState<SystemInfo>(defaultSystemInfo);
  const [systemMetrics, setSystemMetrics] = useState<SystemMetrics>(defaultSystemMetrics);
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);

  // 应用主题
  const applyTheme = useCallback((theme: 'light' | 'dark' | 'auto') => {
    const root = document.documentElement;
    let effectiveTheme: 'light' | 'dark';

    if (theme === 'auto') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      effectiveTheme = prefersDark ? 'dark' : 'light';
    } else {
      effectiveTheme = theme;
    }

    // 设置 data-theme 属性（用于 CSS 变量选择）
    root.setAttribute('data-theme', effectiveTheme);

    // 同时设置/移除 dark class（用于 App.tsx 中的主题监听和 Tailwind 暗色模式）
    if (effectiveTheme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }

    // 同步到 localStorage（用于 useBrowserTheme hook）
    localStorage.setItem('quantcell-ui-theme', effectiveTheme);
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

      // 处理后端返回的配置格式（按 name 分组的格式）
      // 格式: { "appearance": { "theme": "light", ... }, "notification": { ... } }
      const groupedConfig = response?.data || response;

      // 将分组配置扁平化，方便提取
        const flattenConfig: Record<string, any> = {};
        if (groupedConfig && typeof groupedConfig === 'object') {
          Object.entries(groupedConfig).forEach(([, groupValues]) => {
            if (groupValues && typeof groupValues === 'object') {
              Object.entries(groupValues as Record<string, any>).forEach(([key, value]) => {
                flattenConfig[key] = value;
              });
            }
          });
        }

      // 从扁平配置中提取通用设置
      const loadedGeneralSettings: Partial<GeneralSettings> = {
        theme: flattenConfig['theme'],
        language: flattenConfig['language'],
        defaultPerPage: flattenConfig['defaultPerPage'] ? parseInt(flattenConfig['defaultPerPage'], 10) : undefined,
        showTips: flattenConfig['showTips'] === 'true' || flattenConfig['showTips'] === true,
        timezone: flattenConfig['timezone'],
      };

      // 过滤掉 undefined 值
      const filteredGeneralSettings = Object.fromEntries(
        Object.entries(loadedGeneralSettings).filter(([, v]) => v !== undefined)
      ) as Partial<GeneralSettings>;

      if (Object.keys(filteredGeneralSettings).length > 0) {
        setGeneralSettings(prev => ({ ...prev, ...filteredGeneralSettings }));
        applyTheme(filteredGeneralSettings.theme || 'light');
      }

      // 从扁平配置中提取通知设置
      const loadedNotificationSettings: Partial<NotificationSettings> = {
        enableEmail: flattenConfig['enableEmail'] === 'true' || flattenConfig['enableEmail'] === true,
        enableWebhook: flattenConfig['enableWebhook'] === 'true' || flattenConfig['enableWebhook'] === true,
        webhookUrl: flattenConfig['webhookUrl'],
        notifyOnAlert: flattenConfig['notifyOnAlert'] === 'true' || flattenConfig['notifyOnAlert'] === true,
        notifyOnTaskComplete: flattenConfig['notifyOnTaskComplete'] === 'true' || flattenConfig['notifyOnTaskComplete'] === true,
        notifyOnSystemUpdate: flattenConfig['notifyOnSystemUpdate'] === 'true' || flattenConfig['notifyOnSystemUpdate'] === true,
      };

      const filteredNotificationSettings = Object.fromEntries(
        Object.entries(loadedNotificationSettings).filter(([, v]) => v !== undefined)
      ) as Partial<NotificationSettings>;

      if (Object.keys(filteredNotificationSettings).length > 0) {
        setNotificationSettings(prev => ({ ...prev, ...filteredNotificationSettings }));
      }

      // 从扁平配置中提取 API 设置
      const loadedApiSettings: Partial<ApiSettings> = {
        apiKey: flattenConfig['apiKey'],
      };

      const filteredApiSettings = Object.fromEntries(
        Object.entries(loadedApiSettings).filter(([, v]) => v !== undefined)
      ) as Partial<ApiSettings>;

      if (Object.keys(filteredApiSettings).length > 0) {
        setApiSettings(prev => ({ ...prev, ...filteredApiSettings }));
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

      // 将嵌套配置转换为后端期望的配置项对象列表格式
      // 每个配置项需要包含 key, value, name 字段
      // name 字段用于分组，相同的 name 会被归为一组
      const configList = [
        // 通用设置 - 使用 'general' 作为 name 分组
        { key: 'theme', value: generalSettings.theme, name: 'general', description: '系统主题设置' },
        { key: 'language', value: generalSettings.language, name: 'general', description: '系统语言设置' },
        { key: 'defaultPerPage', value: String(generalSettings.defaultPerPage), name: 'general', description: '列表页默认显示数量' },
        { key: 'timezone', value: generalSettings.timezone, name: 'general', description: '系统默认时区' },
        { key: 'showTips', value: String(generalSettings.showTips), name: 'general', description: '是否显示提示' },
      ];

      await configApi.updateConfig(configList);

      // 重新加载系统配置
      console.log('[SettingsContext] 保存成功，重新加载系统配置');
      const updatedConfig = await configApi.getConfig();
      console.log('[SettingsContext] 重新加载的配置:', updatedConfig);

      // 更新全局配置
      if (typeof window !== 'undefined') {
        (window as any).APP_CONFIG = {
          ...(window as any).APP_CONFIG,
          generalSettings,
          notificationSettings,
          apiSettings,
        };
        console.log('[SettingsContext] window.APP_CONFIG 已更新:', (window as any).APP_CONFIG);
      }

      message.success('设置保存成功');
    } catch (error) {
      console.error('保存配置失败:', error);
      message.error('保存配置失败');
    } finally {
      setSaving(false);
    }
  }, [generalSettings, notificationSettings, apiSettings]);

  // 重置配置
  const resetConfig = useCallback(() => {
    setGeneralSettings(defaultGeneralSettings);
    setNotificationSettings(defaultNotificationSettings);
    setApiSettings(defaultApiSettings);
    setSystemMetrics(defaultSystemMetrics);
    applyTheme(defaultGeneralSettings.theme);
    message.success('设置已重置为默认值');
  }, [applyTheme]);

  // 组件挂载时加载配置
  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  const value: SettingsContextType = {
    generalSettings,
    notificationSettings,
    apiSettings,
    systemInfo,
    systemMetrics,
    loading,
    saving,
    setGeneralSettings,
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
