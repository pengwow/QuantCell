/**
 * 设置页面主组件
 * 功能：提供用户界面配置、通知设置、API配置、系统信息等功能
 */
import { useState, useEffect, lazy, Suspense } from 'react';
import { configApi } from '../../api';
import type { AppConfig } from '../../utils/configLoader';
import { useTranslation } from 'react-i18next';
import { applyTheme } from '../../utils/themeManager';
import { pluginManager } from '../../plugins/PluginManager';
import { useResponsive } from '../../hooks/useResponsive';

// 导入类型定义
import type { 
  UserSettings, 
  NotificationSettings, 
  ApiSettings, 
  SystemConfig as SystemConfigType, 
  SystemInfo as SystemInfoType,
  PluginConfig
} from './types';

// 导入独立模块（使用动态导入实现按需加载）
const BasicSettings = lazy(() => import('./BasicSettings'));
const SystemConfig = lazy(() => import('./SystemConfig'));
const Notifications = lazy(() => import('./Notifications'));
const ApiSettings = lazy(() => import('./ApiSettings'));
const SystemInfo = lazy(() => import('./SystemInfo'));
const Plugins = lazy(() => import('./Plugins'));

// 扩展Window接口，添加APP_CONFIG属性
declare global {
  interface Window {
    APP_CONFIG: AppConfig;
  }
}

// 定义请求配置项类型，用于API请求
type ConfigItem = {
  key: string;
  value: any;
  description: string;
  plugin?: string;
  name?: string;
}

import {
  Layout, Menu, Button, Space, Spin
} from 'antd';
import {
  UserOutlined, BellOutlined, ApiOutlined, SettingOutlined,
  InfoCircleOutlined, ReloadOutlined, SaveOutlined
} from '@ant-design/icons';
import '../../styles/Setting.css';

// 添加CSS动画定义
const style = document.createElement('style');
style.textContent = `
  @keyframes slideInRight {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
`;
document.head.appendChild(style);

const Setting = () => {
  // 当前选中的标签页
  const [currentTab, setCurrentTab] = useState<string>('basic');
  // 显示成功消息标志
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  // 保存加载状态
  const [isSaving, setIsSaving] = useState(false);
  // 保存错误信息
  const [saveError, setSaveError] = useState<string | null>(null);
  // 使用响应式钩子
  const { isMobile, isTablet } = useResponsive();
  // 菜单模式状态 - 与主菜单保持一致的切换逻辑
  const [menuMode, setMenuMode] = useState<'horizontal' | 'inline'>(isMobile || isTablet ? 'horizontal' : 'inline');
  // 插件配置
  const [pluginConfigs, setPluginConfigs] = useState<PluginConfig[]>([]);
  // 插件配置状态，用于管理插件配置值
  const [pluginConfigValues, setPluginConfigValues] = useState<Record<string, Record<string, any>>>({});
  // 插件加载状态，用于管理每个插件的加载状态
  const [pluginLoadingStates, setPluginLoadingStates] = useState<Record<string, boolean>>({});
  // 插件错误信息，用于显示加载失败的错误信息
  const [pluginErrorMessages, setPluginErrorMessages] = useState<Record<string, string>>({});

  // 监听响应式状态变化，更新菜单模式
  useEffect(() => {
    // 与主菜单保持一致的切换逻辑
    setMenuMode(isMobile || isTablet ? 'horizontal' : 'inline');
  }, [isMobile, isTablet]);

  // 国际化支持
  const { t, i18n } = useTranslation();



  // 用户设置
  const [settings, setSettings] = useState<UserSettings>({
    username: 'admin',
    displayName: '系统管理员',
    email: 'admin@example.com',
    theme: 'light',
    language: 'zh-CN',
    showTips: true
  });

  // 通知设置
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings>({
    enableEmail: true,
    enableWebhook: false,
    webhookUrl: '',
    notifyOnAlert: true,
    notifyOnTaskComplete: true,
    notifyOnSystemUpdate: false
  });

  // API设置
  const [apiSettings, setApiSettings] = useState<ApiSettings>({
    apiKey: 'sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
    permissions: [
      {
        id: 'read',
        name: '读取权限',
        description: '允许读取系统数据和配置',
        enabled: true
      },
      {
        id: 'write',
        name: '写入权限',
        description: '允许修改系统数据和配置',
        enabled: false
      },
      {
        id: 'execute',
        name: '执行权限',
        description: '允许执行系统操作和任务',
        enabled: true
      }
    ]
  });

  // 系统配置
  const [systemConfig, setSystemConfig] = useState<SystemConfigType>({
    qlib_data_dir: 'data/qlib_data',
    max_workers: '4',
    data_download_dir: 'data/source',
    current_market_type: 'crypto',
    crypto_trading_mode: 'spot',
    default_exchange: 'binance',
    default_interval: '1d',
    default_commission: 0.001,
    default_initial_cash: 1000000,
    proxy_enabled: true,
    proxy_url: 'http://127.0.0.1:7897',
    proxy_username: '',
    proxy_password: '',
    // 实时数据配置
    realtime_enabled: false,
    data_mode: 'cache',
    frontend_update_interval: 1000,
    frontend_data_cache_size: 1000
  });

  // 系统信息
  const [systemInfo] = useState<SystemInfoType>({
    version: {
      system_version: '1.0.0',
      python_version: '3.10.0',
      build_date: '2024-01-01'
    },
    running_status: {
      uptime: '24h 30m',
      status: 'running',
      status_color: 'green',
      last_check: new Date().toISOString()
    },
    resource_usage: {
      cpu_usage: 30,
      memory_usage: '4.5GB / 16GB',
      disk_space: '120GB / 500GB'
    }
  });

  // 组件挂载时，直接使用window.APP_CONFIG更新本地状态和表单
  useEffect(() => {
    console.log('Setting component: 组件挂载，开始使用APP_CONFIG初始化配置');
    console.log('Setting component: 当前APP_CONFIG:', window.APP_CONFIG);
    
    // 手动触发配置更新
    updateLocalStateAndForm();
  }, []);

  // 加载插件配置
  useEffect(() => {
    const loadPluginConfigs = () => {
      console.log('Setting component: 加载插件配置');
      const configs = pluginManager.getAllPluginConfigs();
      console.log('Setting component: 插件配置:', configs);
      setPluginConfigs(configs);
    };

    // 初始加载
    loadPluginConfigs();

    // 监听插件变化（如果有相关事件）
    // 这里可以添加插件热重载的监听
  }, []);

  // 当切换到插件页面时，加载对应插件配置
  useEffect(() => {
    console.log('Setting component: 检测到标签页切换，当前标签页:', currentTab);
    if (currentTab.startsWith('plugin-')) {
      const pluginName = currentTab.replace('plugin-', '');
      console.log('Setting component: 当前在插件页面，插件名称:', pluginName);
      
      // 加载插件配置
      const loadPluginConfig = async () => {
        try {
          // 更新加载状态
          setPluginLoadingStates(prev => ({
            ...prev,
            [pluginName]: true
          }));
          
          // 调用 API 获取插件配置
          console.log('Setting component: 开始加载插件配置:', {
            pluginName,
            currentTab,
            pluginConfigValues: pluginConfigValues[pluginName]
          });
          const configData = await configApi.getPluginConfig(pluginName);
          console.log('Setting component: 插件配置加载成功:', configData);
          
          // 转换配置数据格式
          const formattedConfig: Record<string, any> = {};
          if (Array.isArray(configData)) {
            // 如果返回的是数组形式，转换为键值对
            configData.forEach(item => {
              formattedConfig[item.key] = item.value;
            });
          } else if (configData && typeof configData === 'object') {
            // 如果返回的是对象形式，直接使用
            Object.keys(configData).forEach(key => {
              formattedConfig[key] = configData[key];
            });
          } else {
            // 处理无效数据
            console.warn('Setting component: 插件配置数据格式无效:', configData);
          }
          
          console.log('Setting component: 格式化后的配置数据:', formattedConfig);
          
          // 更新插件配置值状态
          console.log('Setting component: 更新插件配置值状态:', {
            pluginName,
            formattedConfig
          });
          setPluginConfigValues(prev => {
            const updatedValues = {
              ...prev,
              [pluginName]: formattedConfig
            };
            console.log('Setting component: 更新后的插件配置值状态:', updatedValues);
            return updatedValues;
          });
          
          // 更新插件实例的配置
          const pluginInstance = pluginManager.getPlugin(pluginName);
          if (pluginInstance) {
            Object.keys(formattedConfig).forEach(key => {
              pluginInstance.instance.setConfig(key, formattedConfig[key]);
            });
            console.log('Setting component: 插件实例配置更新完成');
          }
        } catch (error) {
          console.error('Setting component: 加载插件配置失败:', error);
          // 加载失败时，使用插件默认配置
          const pluginInstance = pluginManager.getPlugin(pluginName);
          if (pluginInstance) {
            const defaultConfig: Record<string, any> = {};
            const configs = pluginInstance.instance.getSystemConfigs();
            configs.forEach((configItem: any) => {
              defaultConfig[configItem.key] = configItem.value;
            });
            console.log('Setting component: 使用插件默认配置:', defaultConfig);
            // 更新插件配置值状态
            setPluginConfigValues(prev => ({
              ...prev,
              [pluginName]: defaultConfig
            }));
          }
          // 保存错误信息
          const errorMessage = error instanceof Error ? error.message : '加载插件配置失败';
          setPluginErrorMessages(prev => ({
            ...prev,
            [pluginName]: errorMessage
          }));
        } finally {
          // 更新加载状态
          setPluginLoadingStates(prev => ({
            ...prev,
            [pluginName]: false
          }));
        }
      };
      
      loadPluginConfig();
    }
  }, [currentTab]);

  // 当插件配置加载完成后，更新插件配置值
  useEffect(() => {
    if (pluginConfigs.length > 0 && Object.keys(window.APP_CONFIG || {}).length > 0) {
      console.log('Setting component: 插件配置加载完成，更新插件配置值');
      updateLocalStateAndForm();
    }
  }, [pluginConfigs]);

  // 更新本地状态和表单数据
  const updateLocalStateAndForm = () => {
    console.log('Setting component: 开始更新本地状态和表单');
    console.log('Setting component: APP_CONFIG数据:', window.APP_CONFIG);
    
    const configs = window.APP_CONFIG || {};
    
    // 只在配置有数据时更新
    if (Object.keys(configs).length > 0) {
      console.log('Setting component: 配置有数据，开始更新状态');
      
      // 记录language字段的具体值
      console.log('Setting component: APP_CONFIG中的language:', configs.language);
      
      // 更新本地状态，确保UserSettings的language从系统配置获取
      setSettings(prev => {
        console.log('Setting component: 更新settings前的language:', prev.language);
        const newLanguage = configs.language !== undefined ? configs.language : prev.language;
        console.log('Setting component: 更新settings后的language:', newLanguage);
        return {
          ...prev,
          language: newLanguage,
          theme: configs.theme !== undefined ? configs.theme : prev.theme,
          showTips: configs.showTips !== undefined ? (configs.showTips === 'true' || configs.showTips === true) : prev.showTips
        };
      });

      setNotificationSettings(prev => ({
        ...prev,
        enableEmail: configs.enableEmail !== undefined ? (configs.enableEmail === 'true' || configs.enableEmail === true) : prev.enableEmail,
        enableWebhook: configs.enableWebhook !== undefined ? (configs.enableWebhook === 'true' || configs.enableWebhook === true) : prev.enableWebhook,
        webhookUrl: configs.webhookUrl || prev.webhookUrl,
        notifyOnAlert: configs.notifyOnAlert !== undefined ? (configs.notifyOnAlert === 'true' || configs.notifyOnAlert === true) : prev.notifyOnAlert,
        notifyOnTaskComplete: configs.notifyOnTaskComplete !== undefined ? (configs.notifyOnTaskComplete === 'true' || configs.notifyOnTaskComplete === true) : prev.notifyOnTaskComplete,
        notifyOnSystemUpdate: configs.notifyOnSystemUpdate !== undefined ? (configs.notifyOnSystemUpdate === 'true' || configs.notifyOnSystemUpdate === true) : prev.notifyOnSystemUpdate
      }));

      setApiSettings(prev => ({
        ...prev,
        apiKey: configs.apiKey || prev.apiKey,
        permissions: configs.apiPermissions ? JSON.parse(configs.apiPermissions) : prev.permissions
      }));

      setSystemConfig(prev => ({
        ...prev,
        qlib_data_dir: configs.qlib_data_dir || prev.qlib_data_dir,
        max_workers: configs.max_workers || prev.max_workers,
        data_download_dir: configs.data_download_dir || prev.data_download_dir,
        current_market_type: configs.current_market_type || prev.current_market_type,
        crypto_trading_mode: configs.crypto_trading_mode || prev.crypto_trading_mode,
        default_exchange: configs.default_exchange || prev.default_exchange,
        default_interval: configs.default_interval || prev.default_interval,
        default_commission: configs.default_commission !== undefined ? Number(configs.default_commission) : prev.default_commission,
        default_initial_cash: configs.default_initial_cash !== undefined ? Number(configs.default_initial_cash) : prev.default_initial_cash,
        proxy_enabled: configs.proxy_enabled !== undefined ? (configs.proxy_enabled === 'true' || configs.proxy_enabled === true) : prev.proxy_enabled,
        proxy_url: configs.proxy_url || prev.proxy_url,
        proxy_username: configs.proxy_username || prev.proxy_username,
        proxy_password: configs.proxy_password || prev.proxy_password,
        realtime_enabled: configs.realtime_enabled !== undefined ? (configs.realtime_enabled === 'true' || configs.realtime_enabled === true) : prev.realtime_enabled,
        data_mode: configs.data_mode || prev.data_mode,
        frontend_update_interval: configs.frontend_update_interval !== undefined ? Number(configs.frontend_update_interval) : prev.frontend_update_interval,
        frontend_data_cache_size: configs.frontend_data_cache_size !== undefined ? Number(configs.frontend_data_cache_size) : prev.frontend_data_cache_size
      }));

      // 更新插件配置
      console.log('Setting component: 开始更新插件配置');
      const newPluginConfigValues: Record<string, Record<string, any>> = {};
      pluginConfigs.forEach(pluginConfig => {
        console.log('Setting component: 更新插件配置:', pluginConfig.name);
        const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
        if (pluginInstance) {
          const pluginValues: Record<string, any> = {};
          pluginConfig.configs.forEach(configItem => {
            const configValue = configs[configItem.key];
            if (configValue !== undefined && configValue !== null) {
              console.log('Setting component: 更新插件配置项:', configItem.key, '值:', configValue);
              pluginInstance.instance.setConfig(configItem.key, configValue);
              pluginValues[configItem.key] = configValue;
            }
          });
          newPluginConfigValues[pluginConfig.name] = pluginValues;
        }
      });
      
      // 更新插件配置值状态
      setPluginConfigValues(newPluginConfigValues);


    } else {
      console.log('Setting component: APP_CONFIG没有数据，跳过更新');
    }
  };

  /**
   * 重新生成 API Key
   */
  const regenerateApiKey = () => {
    if (window.confirm('确定要重新生成 API Key 吗？当前的 API Key 将失效。')) {
      // 模拟生成随机 API Key
      const randomKey = 'sk_' + Math.random().toString(36).substring(2, 34);
      setApiSettings(prev => ({
        ...prev,
        apiKey: randomKey
      }));
    }
  };

  /**
   * 统一保存所有配置
   */
  const saveAllConfig = async () => {
    setIsSaving(true);
    setSaveError(null);

    try {
      // 准备请求数据 - 收集所有配置项
      const requestData: ConfigItem[] = [];

      // 处理basic配置
      requestData.push({
        key: 'language',
        value: settings.language,
        description: 'basic.language'
      });
      requestData.push({
        key: 'theme',
        value: settings.theme,
        description: 'basic.theme'
      });
      requestData.push({
        key: 'showTips',
        value: settings.showTips,
        description: 'basic.showTips'
      });

      // 处理notifications配置
      requestData.push({
        key: 'enableEmail',
        value: notificationSettings.enableEmail,
        description: 'notifications.enableEmail'
      });
      requestData.push({
        key: 'enableWebhook',
        value: notificationSettings.enableWebhook,
        description: 'notifications.enableWebhook'
      });
      requestData.push({
        key: 'webhookUrl',
        value: notificationSettings.webhookUrl,
        description: 'notifications.webhookUrl'
      });
      requestData.push({
        key: 'notifyOnAlert',
        value: notificationSettings.notifyOnAlert,
        description: 'notifications.notifyOnAlert'
      });
      requestData.push({
        key: 'notifyOnTaskComplete',
        value: notificationSettings.notifyOnTaskComplete,
        description: 'notifications.notifyOnTaskComplete'
      });
      requestData.push({
        key: 'notifyOnSystemUpdate',
        value: notificationSettings.notifyOnSystemUpdate,
        description: 'notifications.notifyOnSystemUpdate'
      });

      // 处理api配置
      requestData.push({
        key: 'apiKey',
        value: apiSettings.apiKey,
        description: 'api.apiKey'
      });
      // 处理API权限，将数组转换为字符串存储
      requestData.push({
        key: 'apiPermissions',
        value: JSON.stringify(apiSettings.permissions),
        description: 'api.permissions'
      });

      // 处理system配置
      requestData.push({
        key: 'qlib_data_dir',
        value: systemConfig.qlib_data_dir,
        description: 'system.qlib_data_dir'
      });
      requestData.push({
        key: 'max_workers',
        value: systemConfig.max_workers,
        description: 'system.max_workers'
      });
      requestData.push({
        key: 'data_download_dir',
        value: systemConfig.data_download_dir,
        description: 'system.data_download_dir'
      });
      requestData.push({
        key: 'current_market_type',
        value: systemConfig.current_market_type,
        description: 'system.current_market_type'
      });
      requestData.push({
        key: 'crypto_trading_mode',
        value: systemConfig.crypto_trading_mode,
        description: 'system.crypto_trading_mode'
      });
      requestData.push({
        key: 'default_exchange',
        value: systemConfig.default_exchange,
        description: 'system.default_exchange'
      });
      requestData.push({
        key: 'default_interval',
        value: systemConfig.default_interval,
        description: 'system.default_interval'
      });
      requestData.push({
        key: 'default_commission',
        value: systemConfig.default_commission,
        description: 'system.default_commission'
      });
      requestData.push({
        key: 'default_initial_cash',
        value: systemConfig.default_initial_cash,
        description: 'system.default_initial_cash'
      });
      requestData.push({
        key: 'proxy_enabled',
        value: systemConfig.proxy_enabled,
        description: 'system.proxy_enabled'
      });
      requestData.push({
        key: 'proxy_url',
        value: systemConfig.proxy_url,
        description: 'system.proxy_url'
      });
      requestData.push({
        key: 'proxy_username',
        value: systemConfig.proxy_username,
        description: 'system.proxy_username'
      });
      requestData.push({
        key: 'proxy_password',
        value: systemConfig.proxy_password,
        description: 'system.proxy_password'
      });
      // 实时数据配置
      requestData.push({
        key: 'realtime_enabled',
        value: systemConfig.realtime_enabled,
        description: 'system.realtime_enabled'
      });
      requestData.push({
        key: 'data_mode',
        value: systemConfig.data_mode,
        description: 'system.data_mode'
      });
      requestData.push({
        key: 'frontend_update_interval',
        value: systemConfig.frontend_update_interval,
        description: 'system.frontend_update_interval'
      });
      requestData.push({
        key: 'frontend_data_cache_size',
        value: systemConfig.frontend_data_cache_size,
        description: 'system.frontend_data_cache_size'
      });

      // 处理插件配置
      console.log('处理插件配置:', pluginConfigs);
      pluginConfigs.forEach(pluginConfig => {
        console.log('处理插件:', pluginConfig.name);
        pluginConfig.configs.forEach(configItem => {
          // 获取插件配置值
          const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
          if (pluginInstance) {
            const configValue = pluginInstance.instance.getConfig(configItem.key);
            console.log('插件配置项:', configItem.key, '值:', configValue);
            // 只保存非空值
            if (configValue !== undefined && configValue !== null && configValue !== '') {
              requestData.push({
                key: configItem.key,
                value: configValue,
                description: `${pluginConfig.name}.${configItem.key}`,
                plugin: pluginConfig.name,
                name: pluginConfig.menuName
              });
            }
          }
        });
      });

      console.log('保存所有配置:', requestData);

      // 直接调用API保存配置
      await configApi.updateConfig(requestData);
      
      // 保存设置成功后，重新加载配置数据
      console.log('保存设置成功，重新加载配置');
      const newConfigData = await configApi.getConfig();
      
      // 直接使用API返回的数据，不需要转换，保持与后端一致
      console.log('更新window.APP_CONFIG:', newConfigData);
      window.APP_CONFIG = newConfigData;
      
      // 更新本地状态和表单
      updateLocalStateAndForm();
      
      // 应用新的主题设置
      applyTheme(settings.theme);

      // 显示成功消息
      setShowSuccessMessage(true);
      setTimeout(() => {
        setShowSuccessMessage(false);
      }, 3000);
    } catch (error) {
      // 处理错误
      console.error('保存设置失败:', error);
      setSaveError('保存设置失败，请稍后重试');
      setTimeout(() => {
        setSaveError(null);
      }, 3000);
    } finally {
      setIsSaving(false);
    }
  };

  /**
   * 统一重置所有配置
   */
  const resetAllConfig = () => {
    if (window.confirm('确定要重置所有配置吗？此操作将恢复所有设置为默认值。')) {
      // 重置基本设置
      setSettings({
        username: 'admin',
        displayName: '系统管理员',
        email: 'admin@example.com',
        theme: 'light',
        language: 'zh-CN',
        showTips: true
      });

      // 重置通知设置
      setNotificationSettings({
        enableEmail: true,
        enableWebhook: false,
        webhookUrl: '',
        notifyOnAlert: true,
        notifyOnTaskComplete: true,
        notifyOnSystemUpdate: false
      });

      // 重置API设置
      setApiSettings({
        apiKey: 'sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
        permissions: [
          {
            id: 'read',
            name: '读取权限',
            description: '允许读取系统数据和配置',
            enabled: true
          },
          {
            id: 'write',
            name: '写入权限',
            description: '允许修改系统数据和配置',
            enabled: false
          },
          {
            id: 'execute',
            name: '执行权限',
            description: '允许执行系统操作和任务',
            enabled: true
          }
        ]
      });

      // 重置系统配置
      setSystemConfig({
        qlib_data_dir: 'data/qlib_data',
        max_workers: '4',
        data_download_dir: 'data/source',
        current_market_type: 'crypto',
        crypto_trading_mode: 'spot',
        default_exchange: 'binance',
        default_interval: '1d',
        default_commission: 0.001,
        default_initial_cash: 1000000,
        proxy_enabled: true,
        proxy_url: 'http://127.0.0.1:7897',
        proxy_username: '',
        proxy_password: '',
        realtime_enabled: false,
        data_mode: 'cache',
        frontend_update_interval: 1000,
        frontend_data_cache_size: 1000
      });

      // 显示成功消息
      setShowSuccessMessage(true);
      setTimeout(() => {
        setShowSuccessMessage(false);
      }, 3000);
    }
  };

  const { Sider, Content } = Layout;

  // 菜单项配置
  const [menuConfig, setMenuConfig] = useState<any[]>([]);

  // 更新菜单配置，包括插件配置子菜单
  useEffect(() => {
    const baseMenuConfig = [
      { key: 'basic', label: t('basic_settings'), icon: <UserOutlined /> },
      { key: 'system-config', label: t('system_config'), icon: <SettingOutlined /> },
      { key: 'notifications', label: t('notification_settings'), icon: <BellOutlined /> },
      { key: 'api', label: t('api_settings'), icon: <ApiOutlined /> },
      { key: 'system', label: t('system_info'), icon: <InfoCircleOutlined /> }
    ];

    // 添加插件配置子菜单
    const pluginMenuItems = pluginConfigs.map(config => ({
      key: `plugin-${config.name}`,
      label: config.menuName,
      icon: <SettingOutlined />
    }));

    setMenuConfig([...baseMenuConfig, ...pluginMenuItems]);
  }, [pluginConfigs, t]);

  // 渲染当前选中的模块
  const renderCurrentModule = () => {
    switch (currentTab) {
      case 'basic':
        return (
          <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center' }}><Spin size="large" /></div>}>
            <BasicSettings
              settings={settings}
              setSettings={setSettings}
              applyTheme={applyTheme}
              i18n={i18n}
            />
          </Suspense>
        );
      case 'system-config':
        return (
          <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center' }}><Spin size="large" /></div>}>
            <SystemConfig
              systemConfig={systemConfig}
              setSystemConfig={setSystemConfig}
            />
          </Suspense>
        );
      case 'notifications':
        return (
          <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center' }}><Spin size="large" /></div>}>
            <Notifications
              notificationSettings={notificationSettings}
              setNotificationSettings={setNotificationSettings}
            />
          </Suspense>
        );
      case 'api':
        return (
          <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center' }}><Spin size="large" /></div>}>
            <ApiSettings
              apiSettings={apiSettings}
              setApiSettings={setApiSettings}
              regenerateApiKey={regenerateApiKey}
            />
          </Suspense>
        );
      case 'system':
        return (
          <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center' }}><Spin size="large" /></div>}>
            <SystemInfo
              systemInfo={systemInfo}
              isSaving={isSaving}
              saveError={saveError}
              updateLocalStateAndForm={updateLocalStateAndForm}
            />
          </Suspense>
        );
      default:
        // 处理插件配置页面
        if (currentTab.startsWith('plugin-')) {
          return (
            <Suspense fallback={<div style={{ padding: '40px', textAlign: 'center' }}><Spin size="large" /></div>}>
              <Plugins
                pluginConfigs={pluginConfigs}
                currentTab={currentTab}
                pluginConfigValues={pluginConfigValues}
                setPluginConfigValues={setPluginConfigValues}
                pluginLoadingStates={pluginLoadingStates}
                pluginErrorMessages={pluginErrorMessages}
                pluginManager={pluginManager}
              />
            </Suspense>
          );
        }
        return null;
    }
  };

  return (
    <Layout className="settings-container" style={{ minHeight: '100vh', width: '100%', display: 'flex', flexDirection: 'column', transition: 'all 0.3s ease' }}>
      {/* 根据菜单模式选择不同的布局方向 */}
      <Layout style={{ 
        display: 'flex', 
        flexDirection: menuMode === 'horizontal' ? 'column' : 'row', 
        flex: 1, 
        minWidth: 0, 
        transition: 'all 0.3s ease' 
      }}>
        {/* 侧边栏导航 - 自适应宽度和位置 */}
        <Sider 
          width={menuMode === 'inline' ? 200 : 'auto'} 
          className="settings-sidebar"
          style={{
            flexShrink: 0,
            transition: 'all 0.3s ease',
            overflow: menuMode === 'horizontal' ? 'visible' : 'auto',
            background: '#fff',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.09)',
            display: 'flex',
            flexDirection: 'column',
            transform: 'translateZ(0)', // 启用硬件加速
            marginBottom: menuMode === 'horizontal' ? 12 : 0,
            width: menuMode === 'horizontal' ? '100%' : 200,
            maxWidth: menuMode === 'horizontal' ? 'none !important' : undefined
          }}
        >
          <Menu
            mode={menuMode}
            selectedKeys={[currentTab]}
            items={menuConfig}
            onSelect={({ key }) => setCurrentTab(key)}
            style={{
              width: menuMode === 'inline' ? '100%' : 'auto',
              borderRight: 0,
              borderBottom: menuMode === 'horizontal' ? '1px solid #f0f0f0' : 0,
              transition: 'all 0.3s ease',
              flex: 1
            }}
            overflowedIndicator={menuMode === 'horizontal' ? <SettingOutlined /> : null}
          />
        </Sider>

        {/* 主内容区域 - 完全铺满剩余空间 */}
        <Layout style={{ 
          flex: 1, 
          minWidth: 0, 
          display: 'flex', 
          flexDirection: 'column', 
          background: '#f0f2f5', 
          transition: 'all 0.3s ease',
          marginLeft: menuMode === 'horizontal' ? 0 : 0
        }}>
          {/* 内容区域 - 自适应铺满 */}
          <Content 
            className="settings-main" 
            style={{ 
              flex: 1, 
              minWidth: 0, 
              padding: '24px',
              overflow: 'auto',
              transition: 'all 0.3s ease'
            }}
          >
            {/* 子页面内容 - 确保完全铺满 */}
            <div style={{ width: '100%', height: '100%', background: '#fff', borderRadius: '8px', padding: '24px', boxShadow: '0 2px 8px rgba(0, 0, 0, 0.09)', transition: 'all 0.3s ease' }}>
              {renderCurrentModule()}
            </div>

            {/* 统一操作按钮区域 - 底部 */}
            <div className="settings-actions" style={{ 
              padding: '16px', 
              borderTop: '1px solid #f0f0f0', 
              backgroundColor: '#fff',
              display: 'flex',
              justifyContent: 'flex-end',
              alignItems: 'center',
              marginTop: '16px',
              borderRadius: '8px',
              boxShadow: '0 2px 8px rgba(0, 0, 0, 0.09)',
              transition: 'all 0.3s ease',
              transform: 'translateZ(0)' // 启用硬件加速
            }}>
              <Space size="middle">
                <Button
                  type="default"
                  onClick={resetAllConfig}
                  disabled={isSaving}
                  icon={<ReloadOutlined />}
                  style={{ transition: 'all 0.3s ease' }}
                >
                  重置所有
                </Button>
                <Button
                  type="primary"
                  onClick={saveAllConfig}
                  disabled={isSaving}
                  icon={<SaveOutlined />}
                  style={{ transition: 'all 0.3s ease' }}
                >
                  {isSaving ? '保存中...' : '保存设置'}
                </Button>
              </Space>
            </div>
          </Content>
        </Layout>
      </Layout>

      {/* 保存成功提示 */}
      {showSuccessMessage && (
        <div className="success-message" style={{ 
          position: 'fixed', 
          top: '20px', 
          right: '20px', 
          zIndex: 1000, 
          background: '#52c41a', 
          color: '#fff', 
          padding: '12px 24px', 
          borderRadius: '4px', 
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',
          transition: 'all 0.3s ease',
          transform: 'translateZ(0)', // 启用硬件加速
          animation: 'slideInRight 0.3s ease-out'
        }}>
          设置已成功保存！
        </div>
      )}
    </Layout>
  );
};

export default Setting;
