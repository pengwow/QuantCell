/**
 * 设置页面组件
 * 功能：提供用户界面配置、通知设置、API配置、系统信息等功能
 */
import { useState, useEffect } from 'react';
import { configApi } from '../api';
import type { AppConfig } from '../utils/configLoader';
import { useTranslation } from 'react-i18next';
import { applyTheme } from '../utils/themeManager';
import { pluginManager } from '../plugins/PluginManager';

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
  Layout, Menu, Form, Input, Select, Switch, Button,
  Typography, Card, Space, InputNumber, Tooltip, Spin
} from 'antd';
import {
  UserOutlined, BellOutlined, ApiOutlined, SettingOutlined,
  InfoCircleOutlined, ReloadOutlined, SaveOutlined,
  EyeInvisibleOutlined, EyeTwoTone, QuestionCircleOutlined
} from '@ant-design/icons';
import '../styles/Setting.css';



// 用户设置类型定义
interface UserSettings {
  username: string;
  displayName: string;
  email: string;
  theme: 'light' | 'dark' | 'auto';
  language: 'zh-CN' | 'en-US';
  showTips: boolean;
}

// 通知设置类型定义
interface NotificationSettings {
  enableEmail: boolean;
  enableWebhook: boolean;
  webhookUrl: string;
  notifyOnAlert: boolean;
  notifyOnTaskComplete: boolean;
  notifyOnSystemUpdate: boolean;
}

// API权限类型定义
interface ApiPermission {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

// API设置类型定义
interface ApiSettings {
  apiKey: string;
  permissions: ApiPermission[];
}

// 系统配置类型定义
interface SystemConfig {
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
}

// 版本信息类型定义
interface VersionInfo {
  system_version: string;
  python_version: string;
  build_date: string;
}

// 运行状态类型定义
interface RunningStatus {
  uptime: string;
  status: string;
  status_color: string;
  last_check: string;
}

// 资源使用类型定义
interface ResourceUsage {
  cpu_usage: number;
  memory_usage: string;
  disk_space: string;
}

// 系统信息类型定义
interface SystemInfo {
  version: VersionInfo;
  running_status: RunningStatus;
  resource_usage: ResourceUsage;
  apiVersion?: string;
}

const Setting = () => {
  // 当前选中的标签页
  const [currentTab, setCurrentTab] = useState<string>('basic');
  // 显示成功消息标志
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  // 保存加载状态
  const [isSaving, setIsSaving] = useState(false);
  // 保存错误信息
  const [saveError, setSaveError] = useState<string | null>(null);
  // 菜单模式状态
  const [menuMode, setMenuMode] = useState<'horizontal' | 'inline'>(window.innerWidth < 768 ? 'horizontal' : 'inline');
  // 插件配置
  const [pluginConfigs, setPluginConfigs] = useState<Array<{
    name: string;
    configs: any[];
    menuName: string;
  }>>([]);
  // 插件配置状态，用于管理插件配置值
  const [pluginConfigValues, setPluginConfigValues] = useState<Record<string, Record<string, any>>>({});
  // 插件加载状态，用于管理每个插件的加载状态
  const [pluginLoadingStates, setPluginLoadingStates] = useState<Record<string, boolean>>({});
  // 插件错误信息，用于显示加载失败的错误信息
  const [pluginErrorMessages, setPluginErrorMessages] = useState<Record<string, string>>({});

  // 监听窗口大小变化
  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth;
      setMenuMode(width < 768 ? 'horizontal' : 'inline');
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 国际化支持
  const { t, i18n } = useTranslation();

  // 表单实例 - 始终在组件顶层创建
  const [basicForm] = Form.useForm();
  const [notificationForm] = Form.useForm();
  const [apiForm] = Form.useForm();
  const [systemConfigForm] = Form.useForm();

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
  const [systemConfig, setSystemConfig] = useState<SystemConfig>({
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
    proxy_password: ''
  });

  // 系统信息
  const [systemInfo] = useState<SystemInfo>({
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
            configs.forEach(configItem => {
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

  // 监听 APP_CONFIG 变化，当配置更新时重新加载插件配置值
  // useEffect(() => {
  //   console.log('Setting component: 监听 APP_CONFIG 变化');
    
  //   // 初始检查
  //   if (Object.keys(window.APP_CONFIG || {}).length > 0) {
  //     console.log('Setting component: APP_CONFIG 已初始化，更新插件配置值');
  //     updateLocalStateAndForm();
  //   }
    
  //   // 定期检查 APP_CONFIG 变化
  //   const checkInterval = setInterval(() => {
  //     if (Object.keys(window.APP_CONFIG || {}).length > 0) {
  //       console.log('Setting component: APP_CONFIG 已更新，重新加载插件配置值');
  //       updateLocalStateAndForm();
  //     }
  //   }, 1000); // 每秒检查一次
    
  //   // 清理函数
  //   return () => {
  //     clearInterval(checkInterval);
  //   };
  // }, []);

  // 监听 currentTab 变化，当切换到插件配置页面时加载对应插件的配置
  // 注意：此钩子已被合并到上面的 useEffect 中，避免重复加载

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
        proxy_password: configs.proxy_password || prev.proxy_password
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

      // 构建表单数据，使用APP_CONFIG数据或本地状态默认值
      const finalBasicConfig = {
        language: configs.language !== undefined ? configs.language : settings.language,
        theme: configs.theme !== undefined ? configs.theme : settings.theme,
        showTips: configs.showTips !== undefined ? (configs.showTips === 'true' || configs.showTips === true) : settings.showTips
      };

      console.log('Setting component: 最终用于更新表单的basicConfig:', finalBasicConfig);
      console.log('Setting component: finalBasicConfig中的language:', finalBasicConfig.language);
      
      const finalNotificationConfig = {
        enableEmail: configs.enableEmail !== undefined ? (configs.enableEmail === 'true' || configs.enableEmail === true) : notificationSettings.enableEmail,
        enableWebhook: configs.enableWebhook !== undefined ? (configs.enableWebhook === 'true' || configs.enableWebhook === true) : notificationSettings.enableWebhook,
        webhookUrl: configs.webhookUrl || notificationSettings.webhookUrl,
        notifyOnAlert: configs.notifyOnAlert !== undefined ? (configs.notifyOnAlert === 'true' || configs.notifyOnAlert === true) : notificationSettings.notifyOnAlert,
        notifyOnTaskComplete: configs.notifyOnTaskComplete !== undefined ? (configs.notifyOnTaskComplete === 'true' || configs.notifyOnTaskComplete === true) : notificationSettings.notifyOnTaskComplete,
        notifyOnSystemUpdate: configs.notifyOnSystemUpdate !== undefined ? (configs.notifyOnSystemUpdate === 'true' || configs.notifyOnSystemUpdate === true) : notificationSettings.notifyOnSystemUpdate
      };

      const finalApiConfig = {
        apiKey: configs.apiKey || apiSettings.apiKey,
        permissions: configs.apiPermissions ? JSON.parse(configs.apiPermissions) : apiSettings.permissions
      };

      const finalSystemConfig = {
        qlib_data_dir: configs.qlib_data_dir || systemConfig.qlib_data_dir,
        max_workers: configs.max_workers || systemConfig.max_workers,
        data_download_dir: configs.data_download_dir || systemConfig.data_download_dir,
        current_market_type: configs.current_market_type || systemConfig.current_market_type,
        crypto_trading_mode: configs.crypto_trading_mode || systemConfig.crypto_trading_mode,
        default_exchange: configs.default_exchange || systemConfig.default_exchange,
        default_interval: configs.default_interval || systemConfig.default_interval,
        default_commission: configs.default_commission !== undefined ? Number(configs.default_commission) : systemConfig.default_commission,
        default_initial_cash: configs.default_initial_cash !== undefined ? Number(configs.default_initial_cash) : systemConfig.default_initial_cash,
        proxy_enabled: configs.proxy_enabled !== undefined ? (configs.proxy_enabled === 'true' || configs.proxy_enabled === true) : systemConfig.proxy_enabled,
        proxy_url: configs.proxy_url || systemConfig.proxy_url,
        proxy_username: configs.proxy_username || systemConfig.proxy_username,
        proxy_password: configs.proxy_password || systemConfig.proxy_password
      };

      // 更新表单
      console.log('Setting component: 开始更新basicForm');
      basicForm.setFieldsValue(finalBasicConfig);
      notificationForm.setFieldsValue(finalNotificationConfig);
      apiForm.setFieldsValue(finalApiConfig);
      systemConfigForm.setFieldsValue(finalSystemConfig);
      console.log('Setting component: 表单更新完成');
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
        proxy_password: ''
      });

      // 显示成功消息
      setShowSuccessMessage(true);
      setTimeout(() => {
        setShowSuccessMessage(false);
      }, 3000);
    }
  };

  /**
   * 切换API权限
   * @param permissionId 权限ID
   */
  const togglePermission = (permissionId: string) => {
    setApiSettings(prev => ({
      ...prev,
      permissions: prev.permissions.map(permission => {
        if (permission.id === permissionId) {
          return {
            ...permission,
            enabled: !permission.enabled
          };
        }
        return permission;
      })
    }));
  };

  const { Sider, Content } = Layout;
  const { Text } = Typography;

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

  return (
    <Layout className="settings-container">
      {/* 页面头部 */}
      {/* <Header className="page-header">
        <Title level={2} style={{ color: '#333', margin: 0, fontSize: '20px', fontWeight: 500 }}>系统设置</Title>
      </Header> */}

      <Layout>
        {/* 侧边栏导航 */}
        <Sider 
          width={menuMode === 'inline' ? 200 : 'auto'} 
          className="settings-sidebar"
          style={menuMode === 'horizontal' ? { overflow: 'visible' } : {}}
        >
          <Menu
            mode={menuMode}
            selectedKeys={[currentTab]}
            items={menuConfig}
            onSelect={({ key }) => setCurrentTab(key)}
            style={menuMode === 'inline' ? { height: '100%', borderRight: 0 } : { width: '100%' }}
          />
        </Sider>

        {/* 主内容区域 */}
        <Layout style={{ flex: 1, minWidth: 0 }}>

          {/* 内容区域 */}
          <Content className="settings-main" style={{ flex: 1, minWidth: 0, padding: '16px' }}>
          {/* 基本设置 */}
          <div style={{ display: currentTab === 'basic' ? 'block' : 'none' }}>
            <Card className="settings-panel" title={t('basic_settings')} variant="outlined">
              <Form
                form={basicForm}
                layout="vertical"
                initialValues={settings}
              >
                <Card size="small">
                  <Form.Item
                    label={t('theme')}
                    name="theme"
                    rules={[{ required: true, message: t('please_select') }]}
                  >
                    <Select
                      onChange={(value) => {
                        const themeValue = value as 'light' | 'dark' | 'auto';
                        setSettings(prev => ({ ...prev, theme: themeValue }));
                        applyTheme(themeValue);
                      }}
                      options={[
                        { value: 'light', label: t('light') },
                        { value: 'dark', label: t('dark') },
                        { value: 'auto', label: t('follow_system') }
                      ]}
                    >
                    </Select>
                  </Form.Item>
                  <Form.Item
                    label={t('language')}
                    name="language"
                    rules={[{ required: true, message: t('please_select') }]}
                  >
                    <Select
                      onChange={(value) => {
                        setSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }));
                        // 更新i18n语言
                        i18n.changeLanguage(value);
                      }}
                      options={[
                        { value: 'zh-CN', label: t('chinese') },
                        { value: 'en-US', label: t('english') }
                      ]}
                    >
                    </Select>
                  </Form.Item>
                  {/* <Form.Item
                      name="showTips"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="显示" 
                        unCheckedChildren="隐藏" 
                        onChange={(checked) => setSettings(prev => ({ ...prev, showTips: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>显示功能提示</Text>
                    </Form.Item> */}
                </Card>
                {/* <Form.Item label="界面设置" name="interface" noStyle>
                  
                </Form.Item> */}


              </Form>
            </Card>
          </div>

          {/* 通知设置 */}
          <div style={{ display: currentTab === 'notifications' ? 'block' : 'none' }}>
            <Card className="settings-panel" title="通知设置" variant="outlined">
              <Form
                form={notificationForm}
                layout="vertical"
                initialValues={notificationSettings}
              >
                <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      name="enableEmail"
                      valuePropName="checked"
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Switch
                          checkedChildren="启用"
                          unCheckedChildren="禁用"
                          onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableEmail: checked }))}
                        />
                        <Text style={{ marginLeft: 8 }}>邮件通知</Text>
                      </div>
                    </Form.Item>
                    <Form.Item
                      name="enableWebhook"
                      valuePropName="checked"
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Switch
                          checkedChildren="启用"
                          unCheckedChildren="禁用"
                          onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableWebhook: checked }))}
                        />
                        <Text style={{ marginLeft: 8 }}>Webhook 通知</Text>
                      </div>
                    </Form.Item>
                    {notificationSettings.enableWebhook && (
                      <Form.Item
                        label="Webhook URL"
                        name="webhookUrl"
                        rules={[{ required: true, message: '请输入 Webhook URL' }]}
                      >
                        <Input
                          placeholder="请输入 Webhook URL"
                          onChange={(e) => setNotificationSettings(prev => ({ ...prev, webhookUrl: e.target.value }))}
                        />
                      </Form.Item>
                    )}
                  </Card>
                {/* <Form.Item label="通知方式" name="notificationMethods" noStyle>
                  
                </Form.Item> */}
<Card size="small">
                    <Form.Item
                      name="notifyOnAlert"
                      valuePropName="checked"
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Switch
                          checkedChildren="启用"
                          unCheckedChildren="禁用"
                          onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnAlert: checked }))}
                        />
                        <Text style={{ marginLeft: 8 }}>告警通知</Text>
                      </div>
                    </Form.Item>
                    <Form.Item
                      name="notifyOnTaskComplete"
                      valuePropName="checked"
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Switch
                          checkedChildren="启用"
                          unCheckedChildren="禁用"
                          onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnTaskComplete: checked }))}
                        />
                        <Text style={{ marginLeft: 8 }}>任务完成通知</Text>
                      </div>
                    </Form.Item>
                    <Form.Item
                      name="notifyOnSystemUpdate"
                      valuePropName="checked"
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Switch
                          checkedChildren="启用"
                          unCheckedChildren="禁用"
                          onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnSystemUpdate: checked }))}
                        />
                        <Text style={{ marginLeft: 8 }}>系统更新通知</Text>
                      </div>
                    </Form.Item>
                  </Card>
                {/* <Form.Item label="通知内容" name="notificationContent" noStyle>
                  
                </Form.Item> */}


              </Form>
            </Card>
          </div>

          {/* API 配置 */}
          <div style={{ display: currentTab === 'api' ? 'block' : 'none' }}>
            <Card className="settings-panel" title="API 配置" variant="outlined">
              <Form
                form={apiForm}
                layout="vertical"
                initialValues={apiSettings}
              >
                <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      label="API Key"
                      name="apiKey"
                      rules={[{ required: true, message: 'API Key 不能为空' }]}
                    >
                      <Input.Password
                        placeholder="API Key"
                        disabled
                        iconRender={(visible) => (visible ? <EyeTwoTone /> : <EyeInvisibleOutlined />)}
                      />
                    </Form.Item>
                    <Form.Item>
                      <Space>
                        <Button
                          type="default"
                          onClick={regenerateApiKey}
                          icon={<ReloadOutlined />}
                        >
                          重新生成
                        </Button>
                        <Text type="secondary">
                          API Key 用于调用系统 API。请妥善保管，避免泄露。
                        </Text>
                      </Space>
                    </Form.Item>
                  </Card>
                {/* <Form.Item label="API 密钥" name="apiKeySection" noStyle>
                  
                </Form.Item> */}
<Card size="small">
                    {apiSettings.permissions.map(permission => (
                      <Form.Item key={permission.id} name={permission.id} noStyle>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                          <div>
                            <h4 style={{ margin: '0 0 4px 0' }}>{permission.name}</h4>
                            <Text type="secondary" style={{ fontSize: '12px' }}>{permission.description}</Text>
                          </div>
                          <Switch
                            checked={permission.enabled}
                            checkedChildren="启用"
                            unCheckedChildren="禁用"
                            onChange={() => togglePermission(permission.id)}
                          />
                        </div>
                      </Form.Item>
                    ))}
                  </Card>
                {/* <Form.Item label="API 权限" name="apiPermissions" noStyle>
                  
                </Form.Item> */}


              </Form>
            </Card>
          </div>

          {/* 系统配置 */}
          <div style={{ display: currentTab === 'system-config' ? 'block' : 'none' }}>
            <Card className="settings-panel" title="系统配置" variant="outlined">
              <Form
                form={systemConfigForm}
                layout="vertical"
                initialValues={systemConfig}
              >
                {/* 数据目录配置 */}
                <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      label={
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          QLib数据目录
                          <Tooltip title="QLib数据的存储目录，用于存放下载的市场数据" placement="right">
                            <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                          </Tooltip>
                        </div>
                      }
                      name="qlib_data_dir"
                      rules={[{ required: true, message: '请输入QLib数据目录' }]}
                    >
                      <Input
                        placeholder="请输入QLib数据目录"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, qlib_data_dir: e.target.value }))}
                      />
                    </Form.Item>
                    <Form.Item
                      label={
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          数据下载目录
                          <Tooltip title="数据下载的临时存储目录，用于存放原始数据" placement="right">
                            <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                          </Tooltip>
                        </div>
                      }
                      name="data_download_dir"
                      rules={[{ required: true, message: '请输入数据下载目录' }]}
                    >
                      <Input
                        placeholder="请输入数据下载目录"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, data_download_dir: e.target.value }))}
                      />
                    </Form.Item>
                  </Card>
                {/* <Form.Item label="数据目录配置" name="dataDirConfig" noStyle>
                  
                </Form.Item> */}

                {/* 交易设置 */}
                <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      label={
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          当前交易模式
                          <Tooltip title="选择当前的交易市场模式，如加密货币、股票等" placement="right">
                            <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                          </Tooltip>
                        </div>
                      }
                      name="current_market_type"
                      rules={[{ required: true, message: '请选择交易模式' }]}
                    >
                      <Select
                        onChange={(value) => setSystemConfig(prev => ({ ...prev, current_market_type: value }))}
                      >
                        <Select.Option value="crypto">加密货币</Select.Option>
                        <Select.Option value="stock" disabled>股票</Select.Option>
                        <Select.Option value="future" disabled>期货</Select.Option>
                      </Select>
                    </Form.Item>

                    {systemConfig.current_market_type === 'crypto' && (
                      <>
                        <Form.Item
                          label={
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              加密货币蜡烛图类型
                              <Tooltip title="选择加密货币的交易模式，如现货或合约" placement="right">
                                <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                              </Tooltip>
                            </div>
                          }
                          name="crypto_trading_mode"
                          rules={[{ required: true, message: '请选择蜡烛图类型' }]}
                        >
                          <Select
                            onChange={(value) => setSystemConfig(prev => ({ ...prev, crypto_trading_mode: value }))}
                          >
                            <Select.Option value="spot">现货</Select.Option>
                            <Select.Option value="futures" disabled>合约</Select.Option>
                          </Select>
                        </Form.Item>
                        <Form.Item
                          label={
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              默认交易所
                              <Tooltip title="选择默认的加密货币交易所" placement="right">
                                <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                              </Tooltip>
                            </div>
                          }
                          name="default_exchange"
                          rules={[{ required: true, message: '请选择默认交易所' }]}
                        >
                          <Select
                            onChange={(value) => setSystemConfig(prev => ({ ...prev, default_exchange: value }))}
                          >
                            <Select.Option value="binance">Binance</Select.Option>
                            <Select.Option value="okx" disabled>OKX</Select.Option>
                          </Select>
                        </Form.Item>
                      </>
                    )}

                    {systemConfig.current_market_type === 'stock' && (
                      <Form.Item
                        label="股票交易所"
                        name="default_exchange"
                        rules={[{ required: true, message: '请选择股票交易所' }]}
                      >
                        <Select
                          onChange={(value) => setSystemConfig(prev => ({ ...prev, default_exchange: value }))}
                        >
                          <Select.Option value="shanghai">上交所</Select.Option>
                          <Select.Option value="shenzhen">深交所</Select.Option>
                          <Select.Option value="hongkong">港交所</Select.Option>
                        </Select>
                      </Form.Item>
                    )}

                    <Form.Item
                      label={
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          默认时间间隔
                          <Tooltip title="选择默认的K线时间间隔，如1分钟、1小时、1天等" placement="right">
                            <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                          </Tooltip>
                        </div>
                      }
                      name="default_interval"
                      rules={[{ required: true, message: '请选择默认时间间隔' }]}
                    >
                      <Select
                        onChange={(value) => setSystemConfig(prev => ({ ...prev, default_interval: value }))}
                      >
                        <Select.Option value="1m">1分钟</Select.Option>
                        <Select.Option value="5m">5分钟</Select.Option>
                        <Select.Option value="15m">15分钟</Select.Option>
                        <Select.Option value="30m">30分钟</Select.Option>
                        <Select.Option value="1h">1小时</Select.Option>
                        <Select.Option value="4h">4小时</Select.Option>
                        <Select.Option value="1d">1天</Select.Option>
                      </Select>
                    </Form.Item>
                    
                    <Form.Item
                      label={
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          默认手续费
                          <Tooltip title="设置默认的交易手续费率" placement="right">
                            <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                          </Tooltip>
                        </div>
                      }
                      name="default_commission"
                      rules={[{ required: true, message: '请输入默认手续费率' }]}
                    >
                      <InputNumber
                        onChange={(value: number | null) => setSystemConfig(prev => ({ ...prev, default_commission: value || 0 }))}
                        min={0}
                        max={1}
                        step={0.0001}
                        style={{ width: '100%' }}
                      />
                    </Form.Item>
                    
                    <Form.Item
                      label={
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          默认初始资金
                          <Tooltip title="设置默认的回测初始资金" placement="right">
                            <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                          </Tooltip>
                        </div>
                      }
                      name="default_initial_cash"
                      rules={[{ required: true, message: '请输入默认初始资金' }]}
                    >
                      <InputNumber
                        onChange={(value: number | null) => setSystemConfig(prev => ({ ...prev, default_initial_cash: value || 1000000 }))}
                        min={1000}
                        max={100000000}
                        step={1000}
                        style={{ width: '100%' }}
                      />
                    </Form.Item>
                  </Card>
                {/* <Form.Item label="交易设置" name="tradingConfig" noStyle>
                  
                </Form.Item> */}

                {/* 代理设置 */}
                <Card size="small">
                    <Form.Item
                      name="proxy_enabled"
                      valuePropName="checked"
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <Switch
                          checkedChildren="启用"
                          unCheckedChildren="禁用"
                          onChange={(checked) => setSystemConfig(prev => ({ ...prev, proxy_enabled: checked }))}
                        />
                        <Text style={{ marginLeft: 8 }}>是否启动代理</Text>
                      </div>
                    </Form.Item>

                    {systemConfig.proxy_enabled && (
                      <>
                        <Form.Item
                          label="代理地址"
                          name="proxy_url"
                          rules={[{ required: true, message: '请输入代理地址' }]}
                        >
                          <Input
                            placeholder="请输入代理地址"
                            onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_url: e.target.value }))}
                          />
                        </Form.Item>
                        <Form.Item
                          label="代理用户名"
                          name="proxy_username"
                        >
                          <Input
                            placeholder="请输入代理用户名"
                            onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_username: e.target.value }))}
                          />
                        </Form.Item>
                        <Form.Item
                          label="代理密码"
                          name="proxy_password"
                        >
                          <Input.Password
                            placeholder="请输入代理密码"
                            onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_password: e.target.value }))}
                          />
                        </Form.Item>
                      </>
                    )}
                  </Card>
                {/* <Form.Item label="代理设置" name="proxyConfig" noStyle>
                  
                </Form.Item> */}


              </Form>
            </Card>
          </div>

          {/* 系统信息 */}
          <div style={{ display: currentTab === 'system' ? 'block' : 'none' }}>
            <Card className="settings-panel" title="系统信息" variant="outlined">
              {/* 加载状态 */}
              {isSaving ? (
                <div className="loading-state" style={{ textAlign: 'center', padding: '40px' }}>
                  <div className="loading-spinner"></div>
                  <span style={{ display: 'block', marginTop: '16px' }}>加载系统信息中...</span>
                </div>
              ) : saveError ? (
                <div className="error-state" style={{ textAlign: 'center', padding: '40px' }}>
                  <div className="error-icon" style={{ fontSize: '24px', marginBottom: '8px' }}>⚠️</div>
                  <span style={{ display: 'block', marginBottom: '16px' }}>{saveError}</span>
                  <Button type="default" onClick={updateLocalStateAndForm}>
                    重试
                  </Button>
                </div>
              ) : (
                <div className="system-info">
                  <Card size="small" title="版本信息" style={{ marginBottom: 16 }}>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>系统版本：</span>
                      <span className="info-value">{systemInfo.version.system_version}</span>
                    </div>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>Python 版本：</span>
                      <span className="info-value">{systemInfo.version.python_version}</span>
                    </div>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>构建日期：</span>
                      <span className="info-value">{systemInfo.version.build_date}</span>
                    </div>
                    {systemInfo.apiVersion && (
                      <div className="info-item" style={{ marginBottom: '8px' }}>
                        <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>API 版本：</span>
                        <span className="info-value">{systemInfo.apiVersion}</span>
                      </div>
                    )}
                  </Card>

                  <Card size="small" title="运行状态" style={{ marginBottom: 16 }}>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>运行时间：</span>
                      <span className="info-value">{systemInfo.running_status.uptime}</span>
                    </div>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>服务状态：</span>
                      <span
                        className="info-value"
                        style={{ color: systemInfo.running_status.status_color === 'green' ? '#52c41a' : '#ff4d4f', fontWeight: 'bold' }}
                      >
                        {systemInfo.running_status.status === 'running' ? '正常运行' : systemInfo.running_status.status}
                      </span>
                    </div>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>最后检查：</span>
                      <span className="info-value">{new Date(systemInfo.running_status.last_check).toLocaleString()}</span>
                    </div>
                  </Card>

                  <Card size="small" title="资源使用">
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>CPU 使用率：</span>
                      <span className="info-value">{systemInfo.resource_usage.cpu_usage}%</span>
                    </div>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>内存使用：</span>
                      <span className="info-value">{systemInfo.resource_usage.memory_usage}</span>
                    </div>
                    <div className="info-item" style={{ marginBottom: '8px' }}>
                      <span className="info-label" style={{ display: 'inline-block', width: '120px', fontWeight: 'bold' }}>磁盘空间：</span>
                      <span className="info-value">{systemInfo.resource_usage.disk_space}</span>
                    </div>
                  </Card>
                </div>
              )}
            </Card>
          </div>

          {/* 插件配置 */}
          {pluginConfigs.map(pluginConfig => (
            <div key={pluginConfig.name} style={{ display: currentTab === `plugin-${pluginConfig.name}` ? 'block' : 'none' }}>
              <Card className="settings-panel" title={pluginConfig.menuName} variant="outlined">
                <Form layout="vertical">
                  {pluginConfig.configs.map(configItem => (
                    <Card key={configItem.key} size="small" style={{ marginBottom: 16 }}>
                      {/* 加载状态显示 */}
                      {pluginLoadingStates[pluginConfig.name] ? (
                        <div style={{ textAlign: 'center', padding: '40px' }}>
                          <Spin size="large" />
                          <div style={{ marginTop: '16px', color: '#666' }}>加载插件配置中...</div>
                        </div>
                      ) : (
                        <>
                          {/* 错误信息显示 */}
                          {pluginErrorMessages[pluginConfig.name] && (
                            <div style={{ 
                              padding: '16px', 
                              marginBottom: '16px', 
                              backgroundColor: '#fff2f0', 
                              border: '1px solid #ffccc7', 
                              borderRadius: '4px',
                              color: '#ff4d4f'
                            }}>
                              <div style={{ fontWeight: 'bold', marginBottom: '8px' }}>加载错误</div>
                              <div>{pluginErrorMessages[pluginConfig.name]}</div>
                              <div style={{ marginTop: '8px', fontSize: '12px', color: '#999' }}>
                                已使用插件默认配置
                              </div>
                            </div>
                          )}
                          {/* 调试日志 */}
                          {console.log('Setting component: 渲染插件配置项:', {
                            pluginName: pluginConfig.name,
                            configKey: configItem.key,
                            configValue: pluginConfigValues[pluginConfig.name]?.[configItem.key] || window.APP_CONFIG?.[configItem.key] || configItem.value,
                            pluginConfigValues: pluginConfigValues[pluginConfig.name]
                          })}
                          {configItem.type === 'string' && (
                            <Form.Item
                              label={
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                  {configItem.description}
                                  <Tooltip title={configItem.description} placement="right">
                                    <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                                  </Tooltip>
                                </div>
                              }
                            >
                              <Input
                                placeholder={configItem.description}
                                value={
                                  pluginConfigValues[pluginConfig.name]?.[configItem.key] !== undefined ? 
                                    pluginConfigValues[pluginConfig.name][configItem.key] : 
                                    (window.APP_CONFIG?.[configItem.key] !== undefined ? 
                                      window.APP_CONFIG[configItem.key] : 
                                      configItem.value
                                    )
                                }
                                onChange={(e) => {
                                  const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                                  if (pluginInstance) {
                                    const value = e.target.value;
                                    const pluginName = pluginConfig.name;
                                    console.log('Setting component: 更新插件配置值:', {
                                      pluginName,
                                      configKey: configItem.key,
                                      value
                                    });
                                    // 更新插件实例的配置
                                    pluginInstance.instance.setConfig(configItem.key, value);
                                    // 更新插件配置值状态
                                    setPluginConfigValues(prev => {
                                      const updatedValues = {
                                        ...prev,
                                        [pluginName]: {
                                          ...prev[pluginName],
                                          [configItem.key]: value
                                        }
                                      };
                                      console.log('Setting component: 更新后的插件配置值状态:', updatedValues);
                                      return updatedValues;
                                    });
                                  }
                                }}
                              />
                            </Form.Item>
                          )}
                          {configItem.type === 'number' && (
                            <Form.Item
                              label={
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                  {configItem.description}
                                  <Tooltip title={configItem.description} placement="right">
                                    <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                                  </Tooltip>
                                </div>
                              }
                            >
                              <InputNumber
                                style={{ width: '100%' }}
                                value={
                                  pluginConfigValues[pluginConfig.name]?.[configItem.key] !== undefined ? 
                                    pluginConfigValues[pluginConfig.name][configItem.key] : 
                                    (window.APP_CONFIG?.[configItem.key] !== undefined ? 
                                      Number(window.APP_CONFIG[configItem.key]) : 
                                      Number(configItem.value)
                                    )
                                }
                                onChange={(value: number | null) => {
                                  const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                                  if (pluginInstance) {
                                    const finalValue = value || 0;
                                    const pluginName = pluginConfig.name;
                                    console.log('Setting component: 更新插件配置值:', {
                                      pluginName,
                                      configKey: configItem.key,
                                      value: finalValue
                                    });
                                    // 更新插件实例的配置
                                    pluginInstance.instance.setConfig(configItem.key, finalValue);
                                    // 更新插件配置值状态
                                    setPluginConfigValues(prev => {
                                      const updatedValues = {
                                        ...prev,
                                        [pluginName]: {
                                          ...prev[pluginName],
                                          [configItem.key]: finalValue
                                        }
                                      };
                                      console.log('Setting component: 更新后的插件配置值状态:', updatedValues);
                                      return updatedValues;
                                    });
                                  }
                                }}
                              />
                            </Form.Item>
                          )}
                          {configItem.type === 'boolean' && (
                            <Form.Item
                              label={
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                  {configItem.description}
                                  <Tooltip title={configItem.description} placement="right">
                                    <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                                  </Tooltip>
                                </div>
                              }
                            >
                              <Switch
                                checkedChildren="启用"
                                unCheckedChildren="禁用"
                                checked={
                                  pluginConfigValues[pluginConfig.name]?.[configItem.key] !== undefined ? 
                                    pluginConfigValues[pluginConfig.name][configItem.key] : 
                                    (window.APP_CONFIG?.[configItem.key] !== undefined ? 
                                      (window.APP_CONFIG[configItem.key] === 'true' || window.APP_CONFIG[configItem.key] === true) : 
                                      (configItem.value === 'true' || configItem.value === true)
                                    )
                                }
                                onChange={(checked) => {
                                  const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                                  if (pluginInstance) {
                                    const pluginName = pluginConfig.name;
                                    console.log('Setting component: 更新插件配置值:', {
                                      pluginName,
                                      configKey: configItem.key,
                                      value: checked
                                    });
                                    // 更新插件实例的配置
                                    pluginInstance.instance.setConfig(configItem.key, checked);
                                    // 更新插件配置值状态
                                    setPluginConfigValues(prev => {
                                      const updatedValues = {
                                        ...prev,
                                        [pluginName]: {
                                          ...prev[pluginName],
                                          [configItem.key]: checked
                                        }
                                      };
                                      console.log('Setting component: 更新后的插件配置值状态:', updatedValues);
                                      return updatedValues;
                                    });
                                  }
                                }}
                              />
                            </Form.Item>
                          )}
                          {configItem.type === 'select' && configItem.options && (
                            <Form.Item
                              label={
                                <div style={{ display: 'flex', alignItems: 'center' }}>
                                  {configItem.description}
                                  <Tooltip title={configItem.description} placement="right">
                                    <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                                  </Tooltip>
                                </div>
                              }
                            >
                              <Select
                                options={configItem.options.map((option: string) => ({
                                  value: option,
                                  label: option
                                }))}
                                value={
                                  pluginConfigValues[pluginConfig.name]?.[configItem.key] || 
                                  window.APP_CONFIG?.[configItem.key] || 
                                  configItem.value
                                }
                                onChange={(value) => {
                                  const pluginInstance = pluginManager.getPlugin(pluginConfig.name);
                                  if (pluginInstance) {
                                    const pluginName = pluginConfig.name;
                                    console.log('Setting component: 更新插件配置值:', {
                                      pluginName,
                                      configKey: configItem.key,
                                      value
                                    });
                                    // 更新插件实例的配置
                                    pluginInstance.instance.setConfig(configItem.key, value);
                                    // 更新插件配置值状态
                                    setPluginConfigValues(prev => {
                                      const updatedValues = {
                                        ...prev,
                                        [pluginName]: {
                                          ...prev[pluginName],
                                          [configItem.key]: value
                                        }
                                      };
                                      console.log('Setting component: 更新后的插件配置值状态:', updatedValues);
                                      return updatedValues;
                                    });
                                  }
                                }}
                              />
                            </Form.Item>
                          )}
                        </>
                      )}
                    </Card>
                  ))}
                </Form>
              </Card>
            </div>
          ))}
          {/* 统一操作按钮区域 - 底部 */}
          <div className="settings-actions" style={{ 
            padding: '16px', 
            borderTop: '1px solid #f0f0f0', 
            backgroundColor: '#fff',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            marginTop: '16px'
          }}>
            <Space size="middle">
              <Button
                type="default"
                onClick={resetAllConfig}
                disabled={isSaving}
                icon={<ReloadOutlined />}
              >
                重置所有
              </Button>
              <Button
                type="primary"
                onClick={saveAllConfig}
                disabled={isSaving}
                icon={<SaveOutlined />}
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
        <div className="success-message" style={{ position: 'fixed', top: '20px', right: '20px', zIndex: 1000, background: '#52c41a', color: '#fff', padding: '12px 24px', borderRadius: '4px', boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)' }}>
          设置已成功保存！
        </div>
      )}
    </Layout>
  );
};

export default Setting;