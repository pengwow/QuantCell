/**
 * 设置页面组件
 * 功能：提供用户界面配置、通知设置、API配置、系统信息等功能
 */
import { useState, useEffect } from 'react';
import '../styles/Setting.css';

// 菜单项类型定义
interface MenuItem {
  id: string;
  title: string;
  icon: string;
}

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
  proxy_enabled: string;
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
  // 加载状态
  const [isLoading, setIsLoading] = useState(true);
  // 错误信息
  const [error] = useState('');

  // 菜单项列表
  const menuItems: MenuItem[] = [
    { id: 'basic', title: '基本设置', icon: 'icon-basic' },
    { id: 'system-config', title: '系统配置', icon: 'icon-system-config' },
    { id: 'notifications', title: '通知设置', icon: 'icon-notification' },
    { id: 'api', title: 'API 配置', icon: 'icon-api' },
    { id: 'system', title: '系统信息', icon: 'icon-system' }
  ];

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
    proxy_enabled: 'true',
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

  // 原始设置
  const [originalSettings] = useState({
    basic: { ...settings },
    notifications: { ...notificationSettings },
    api: { ...apiSettings }
  });

  // 组件挂载时加载数据
  useEffect(() => {
    // 模拟获取系统信息
    setTimeout(() => {
      setIsLoading(false);
    }, 1000);
  }, []);

  /**
   * 保存设置
   */
  const saveSettings = () => {
    console.log('保存设置:', {
      basic: settings,
      notifications: notificationSettings,
      api: apiSettings
    });
    
    // 显示成功消息
    setShowSuccessMessage(true);
    setTimeout(() => {
      setShowSuccessMessage(false);
    }, 3000);
  };

  /**
   * 重置设置
   */
  const resetSettings = () => {
    if (window.confirm('确定要重置当前设置吗？')) {
      setSettings(originalSettings.basic);
      setNotificationSettings(originalSettings.notifications);
      setApiSettings(originalSettings.api);
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
   * 保存系统配置
   */
  const saveSystemConfig = () => {
    console.log('保存系统配置:', systemConfig);
    setShowSuccessMessage(true);
    setTimeout(() => {
      setShowSuccessMessage(false);
    }, 3000);
  };

  /**
   * 重置系统配置
   */
  const resetSystemConfig = () => {
    if (window.confirm('确定要重置系统配置吗？')) {
      setSystemConfig({
        qlib_data_dir: 'data/qlib_data',
        max_workers: '4',
        data_download_dir: 'data/source',
        current_market_type: 'crypto',
        crypto_trading_mode: 'spot',
        default_exchange: 'binance',
        default_interval: '1d',
        proxy_enabled: 'true',
        proxy_url: 'http://127.0.0.1:7897',
        proxy_username: '',
        proxy_password: ''
      });
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

  return (
    <div className="settings-container">
      <header className="page-header">
        <h1>系统设置</h1>
      </header>

      <div className="settings-content">
        {/* 侧边栏导航 */}
        <aside className="settings-sidebar">
          <nav className="settings-nav">
            <ul>
              {menuItems.map(menu => (
                <li 
                  key={menu.id}
                  className={currentTab === menu.id ? 'active' : ''}
                  onClick={() => setCurrentTab(menu.id)}
                >
                  <i className={menu.icon}></i>
                  <span>{menu.title}</span>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        {/* 主内容区域 */}
        <main className="settings-main">
          {/* 基本设置 */}
          {currentTab === 'basic' && (
            <div className="settings-panel">
              <h2>基本设置</h2>
              <div className="form-section">
                <h3>个人信息</h3>
                <div className="form-group">
                  <label htmlFor="username">用户名</label>
                  <input 
                    id="username" 
                    value={settings.username} 
                    type="text" 
                    className="form-control"
                    disabled
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="displayName">显示名称</label>
                  <input 
                    id="displayName" 
                    value={settings.displayName} 
                    type="text" 
                    className="form-control"
                    onChange={(e) => setSettings(prev => ({ ...prev, displayName: e.target.value }))}
                    placeholder="请输入显示名称"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="email">邮箱</label>
                  <input 
                    id="email" 
                    value={settings.email} 
                    type="email" 
                    className="form-control"
                    onChange={(e) => setSettings(prev => ({ ...prev, email: e.target.value }))}
                    placeholder="请输入邮箱地址"
                  />
                </div>
              </div>

              <div className="form-section">
                <h3>界面设置</h3>
                <div className="form-group">
                  <label htmlFor="theme">主题</label>
                  <select 
                    id="theme" 
                    value={settings.theme} 
                    className="form-control"
                    onChange={(e) => setSettings(prev => ({ ...prev, theme: e.target.value as 'light' | 'dark' | 'auto' }))}
                  >
                    <option value="light">浅色</option>
                    <option value="dark">深色</option>
                    <option value="auto">跟随系统</option>
                  </select>
                </div>
                <div className="form-group">
                  <label htmlFor="language">语言</label>
                  <select 
                    id="language" 
                    value={settings.language} 
                    className="form-control"
                    onChange={(e) => setSettings(prev => ({ ...prev, language: e.target.value as 'zh-CN' | 'en-US' }))}
                  >
                    <option value="zh-CN">简体中文</option>
                    <option value="en-US">English (US)</option>
                  </select>
                </div>
                <div className="form-group checkbox-group">
                  <input 
                    id="showTips" 
                    checked={settings.showTips} 
                    type="checkbox"
                    onChange={(e) => setSettings(prev => ({ ...prev, showTips: e.target.checked }))}
                  />
                  <label htmlFor="showTips">显示功能提示</label>
                </div>
              </div>

              {/* 底部操作按钮 */}
              <div className="settings-footer">
                <button className="btn btn-secondary" onClick={resetSettings}>
                  重置
                </button>
                <button className="btn btn-primary" onClick={saveSettings}>
                  保存设置
                </button>
              </div>
            </div>
          )}

          {/* 通知设置 */}
          {currentTab === 'notifications' && (
            <div className="settings-panel">
              <h2>通知设置</h2>
              <div className="form-section">
                <h3>通知方式</h3>
                <div className="form-group checkbox-group">
                  <input 
                    id="enableEmail" 
                    checked={notificationSettings.enableEmail} 
                    type="checkbox"
                    onChange={(e) => setNotificationSettings(prev => ({ ...prev, enableEmail: e.target.checked }))}
                  />
                  <label htmlFor="enableEmail">邮件通知</label>
                </div>
                <div className="form-group checkbox-group">
                  <input 
                    id="enableWebhook" 
                    checked={notificationSettings.enableWebhook} 
                    type="checkbox"
                    onChange={(e) => setNotificationSettings(prev => ({ ...prev, enableWebhook: e.target.checked }))}
                  />
                  <label htmlFor="enableWebhook">Webhook 通知</label>
                </div>
                {notificationSettings.enableWebhook && (
                  <div className="form-group">
                    <label htmlFor="webhookUrl">Webhook URL</label>
                    <input 
                      id="webhookUrl" 
                      value={notificationSettings.webhookUrl} 
                      type="text" 
                      className="form-control"
                      onChange={(e) => setNotificationSettings(prev => ({ ...prev, webhookUrl: e.target.value }))}
                      placeholder="请输入 Webhook URL"
                    />
                  </div>
                )}
              </div>

              <div className="form-section">
                <h3>通知内容</h3>
                <div className="form-group checkbox-group">
                  <input 
                    id="notifyOnAlert" 
                    checked={notificationSettings.notifyOnAlert} 
                    type="checkbox"
                    onChange={(e) => setNotificationSettings(prev => ({ ...prev, notifyOnAlert: e.target.checked }))}
                  />
                  <label htmlFor="notifyOnAlert">告警通知</label>
                </div>
                <div className="form-group checkbox-group">
                  <input 
                    id="notifyOnTaskComplete" 
                    checked={notificationSettings.notifyOnTaskComplete} 
                    type="checkbox"
                    onChange={(e) => setNotificationSettings(prev => ({ ...prev, notifyOnTaskComplete: e.target.checked }))}
                  />
                  <label htmlFor="notifyOnTaskComplete">任务完成通知</label>
                </div>
                <div className="form-group checkbox-group">
                  <input 
                    id="notifyOnSystemUpdate" 
                    checked={notificationSettings.notifyOnSystemUpdate} 
                    type="checkbox"
                    onChange={(e) => setNotificationSettings(prev => ({ ...prev, notifyOnSystemUpdate: e.target.checked }))}
                  />
                  <label htmlFor="notifyOnSystemUpdate">系统更新通知</label>
                </div>
              </div>

              {/* 底部操作按钮 */}
              <div className="settings-footer">
                <button className="btn btn-secondary" onClick={resetSettings}>
                  重置
                </button>
                <button className="btn btn-primary" onClick={saveSettings}>
                  保存设置
                </button>
              </div>
            </div>
          )}

          {/* API 配置 */}
          {currentTab === 'api' && (
            <div className="settings-panel">
              <h2>API 配置</h2>
              <div className="form-section">
                <h3>API 密钥</h3>
                <div className="form-group">
                  <label>API Key</label>
                  <div className="input-group">
                    <input 
                      value={apiSettings.apiKey} 
                      type="text" 
                      className="form-control"
                      disabled
                    />
                    <button className="btn btn-secondary" onClick={regenerateApiKey}>
                      重新生成
                    </button>
                  </div>
                  <p className="help-text">
                    API Key 用于调用系统 API。请妥善保管，避免泄露。
                  </p>
                </div>
              </div>

              <div className="form-section">
                <h3>API 权限</h3>
                <div className="permission-list">
                  {apiSettings.permissions.map(permission => (
                    <div key={permission.id} className="permission-item">
                      <div className="permission-info">
                        <h4>{permission.name}</h4>
                        <p>{permission.description}</p>
                      </div>
                      <div className="permission-toggle">
                        <label className="switch">
                          <input 
                            checked={permission.enabled} 
                            type="checkbox"
                            onChange={() => togglePermission(permission.id)}
                          />
                          <span className="slider round"></span>
                        </label>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 底部操作按钮 */}
              <div className="settings-footer">
                <button className="btn btn-secondary" onClick={resetSettings}>
                  重置
                </button>
                <button className="btn btn-primary" onClick={saveSettings}>
                  保存设置
                </button>
              </div>
            </div>
          )}

          {/* 系统配置 */}
          {currentTab === 'system-config' && (
            <div className="settings-panel">
              <h2>系统配置</h2>
              
              {/* 数据目录配置 */}
              <div className="form-section">
                <h3>数据目录配置</h3>
                <div className="form-group">
                  <label htmlFor="qlib_data_dir">QLib数据目录</label>
                  <input 
                    id="qlib_data_dir" 
                    value={systemConfig.qlib_data_dir} 
                    type="text" 
                    className="form-control"
                    onChange={(e) => setSystemConfig(prev => ({ ...prev, qlib_data_dir: e.target.value }))}
                    placeholder="请输入QLib数据目录"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="data_download_dir">数据下载目录</label>
                  <input 
                    id="data_download_dir" 
                    value={systemConfig.data_download_dir} 
                    type="text" 
                    className="form-control"
                    onChange={(e) => setSystemConfig(prev => ({ ...prev, data_download_dir: e.target.value }))}
                    placeholder="请输入数据下载目录"
                  />
                </div>
              </div>

              {/* 交易设置 */}
              <div className="form-section">
                <h3>交易设置</h3>
                <div className="form-group">
                  <label htmlFor="current_market_type">当前交易模式</label>
                  <select 
                    id="current_market_type" 
                    value={systemConfig.current_market_type} 
                    className="form-control"
                    onChange={(e) => setSystemConfig(prev => ({ ...prev, current_market_type: e.target.value }))}
                  >
                    <option value="crypto">加密货币</option>
                    <option value="stock">股票</option>
                  </select>
                </div>
                
                {systemConfig.current_market_type === 'crypto' && (
                  <>
                    <div className="form-group">
                      <label htmlFor="crypto_trading_mode">加密货币蜡烛图类型</label>
                      <select 
                        id="crypto_trading_mode" 
                        value={systemConfig.crypto_trading_mode} 
                        className="form-control"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, crypto_trading_mode: e.target.value }))}
                      >
                        <option value="spot">现货</option>
                        <option value="futures">期货</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label htmlFor="default_exchange">默认交易所</label>
                      <select 
                        id="default_exchange" 
                        value={systemConfig.default_exchange} 
                        className="form-control"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, default_exchange: e.target.value }))}
                      >
                        <option value="binance">Binance</option>
                        <option value="okx">OKX</option>
                      </select>
                    </div>
                  </>
                )}
                
                {systemConfig.current_market_type === 'stock' && (
                  <div className="form-group">
                    <label htmlFor="default_exchange">股票交易所</label>
                    <select 
                      id="default_exchange" 
                      value={systemConfig.default_exchange} 
                      className="form-control"
                      onChange={(e) => setSystemConfig(prev => ({ ...prev, default_exchange: e.target.value }))}
                    >
                      <option value="shanghai">上交所</option>
                      <option value="shenzhen">深交所</option>
                      <option value="hongkong">港交所</option>
                    </select>
                  </div>
                )}
                
                <div className="form-group">
                  <label htmlFor="default_interval">默认时间间隔</label>
                  <select 
                    id="default_interval" 
                    value={systemConfig.default_interval} 
                    className="form-control"
                    onChange={(e) => setSystemConfig(prev => ({ ...prev, default_interval: e.target.value }))}
                  >
                    <option value="1m">1分钟</option>
                    <option value="5m">5分钟</option>
                    <option value="15m">15分钟</option>
                    <option value="30m">30分钟</option>
                    <option value="1h">1小时</option>
                    <option value="4h">4小时</option>
                    <option value="1d">1天</option>
                  </select>
                </div>
              </div>

              {/* 代理设置 */}
              <div className="form-section">
                <h3>代理设置</h3>
                <div className="form-group checkbox-group">
                  <input 
                    id="proxy_enabled" 
                    checked={systemConfig.proxy_enabled === 'true'} 
                    type="checkbox"
                    onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_enabled: e.target.checked ? 'true' : 'false' }))}
                  />
                  <label htmlFor="proxy_enabled">是否启动代理</label>
                </div>
                
                {systemConfig.proxy_enabled === 'true' && (
                  <>
                    <div className="form-group">
                      <label htmlFor="proxy_url">代理地址</label>
                      <input 
                        id="proxy_url" 
                        value={systemConfig.proxy_url} 
                        type="text" 
                        className="form-control"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_url: e.target.value }))}
                        placeholder="请输入代理地址"
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="proxy_username">代理用户名</label>
                      <input 
                        id="proxy_username" 
                        value={systemConfig.proxy_username} 
                        type="text" 
                        className="form-control"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_username: e.target.value }))}
                        placeholder="请输入代理用户名"
                      />
                    </div>
                    <div className="form-group">
                      <label htmlFor="proxy_password">代理密码</label>
                      <input 
                        id="proxy_password" 
                        value={systemConfig.proxy_password} 
                        type="password" 
                        className="form-control"
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, proxy_password: e.target.value }))}
                        placeholder="请输入代理密码"
                      />
                    </div>
                  </>
                )}
              </div>

              {/* 底部操作按钮 */}
              <div className="settings-footer">
                <button className="btn btn-secondary" onClick={resetSystemConfig}>
                  重置
                </button>
                <button className="btn btn-primary" onClick={saveSystemConfig}>
                  保存设置
                </button>
              </div>
            </div>
          )}

          {/* 系统信息 */}
          {currentTab === 'system' && (
            <div className="settings-panel">
              <h2>系统信息</h2>
              
              {/* 加载状态 */}
              {isLoading ? (
                <div className="loading-state">
                  <div className="loading-spinner"></div>
                  <span>加载系统信息中...</span>
                </div>
              ) : error ? (
                <div className="error-state">
                  <div className="error-icon">⚠️</div>
                  <span>{error}</span>
                  <button className="btn btn-secondary" onClick={() => setIsLoading(true)}>
                    重试
                  </button>
                </div>
              ) : (
                <div className="system-info">
                  <div className="info-section">
                    <h3>版本信息</h3>
                    <div className="info-item">
                      <span className="info-label">系统版本：</span>
                      <span className="info-value">{systemInfo.version.system_version}</span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">Python 版本：</span>
                      <span className="info-value">{systemInfo.version.python_version}</span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">构建日期：</span>
                      <span className="info-value">{systemInfo.version.build_date}</span>
                    </div>
                    {systemInfo.apiVersion && (
                      <div className="info-item">
                        <span className="info-label">API 版本：</span>
                        <span className="info-value">{systemInfo.apiVersion}</span>
                      </div>
                    )}
                  </div>

                  <div className="info-section">
                    <h3>运行状态</h3>
                    <div className="info-item">
                      <span className="info-label">运行时间：</span>
                      <span className="info-value">{systemInfo.running_status.uptime}</span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">服务状态：</span>
                      <span 
                        className="info-value"
                        style={{ color: systemInfo.running_status.status_color === 'green' ? '#2ed573' : '#ff6348' }}
                      >
                        {systemInfo.running_status.status === 'running' ? '正常运行' : systemInfo.running_status.status}
                      </span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">最后检查：</span>
                      <span className="info-value">{new Date(systemInfo.running_status.last_check).toLocaleString()}</span>
                    </div>
                  </div>

                  <div className="info-section">
                    <h3>资源使用</h3>
                    <div className="info-item">
                      <span className="info-label">CPU 使用率：</span>
                      <span className="info-value">{systemInfo.resource_usage.cpu_usage}%</span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">内存使用：</span>
                      <span className="info-value">{systemInfo.resource_usage.memory_usage}</span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">磁盘空间：</span>
                      <span className="info-value">{systemInfo.resource_usage.disk_space}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </main>
      </div>

      {/* 保存成功提示 */}
      {showSuccessMessage && (
        <div className="success-message">
          设置已成功保存！
        </div>
      )}
    </div>
  );
};

export default Setting;