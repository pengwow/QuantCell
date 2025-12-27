/**
 * 设置页面组件
 * 功能：提供用户界面配置、通知设置、API配置、系统信息等功能
 */
import { useState, useEffect } from 'react';
import { configApi } from '../api';
import { 
  Layout, Menu, Form, Input, Select, Switch, Button, 
  Typography, Card, Space 
} from 'antd';
import { 
  UserOutlined, BellOutlined, ApiOutlined, SettingOutlined, 
  InfoCircleOutlined, ReloadOutlined, SaveOutlined, 
  EyeInvisibleOutlined, EyeTwoTone 
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
  // 保存加载状态
  const [isSaving, setIsSaving] = useState(false);
  // 保存错误信息
  const [saveError, setSaveError] = useState<string | null>(null);

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
    const loadSettings = async () => {
      setIsLoading(true);
      setSaveError(null);
      
      try {
        // 调用API获取配置
        console.log('加载配置...');
        const configData = await configApi.getConfig();
        console.log('获取配置成功:', configData);
        
        // 更新状态
        if (configData.basic) {
          setSettings(configData.basic);
        }
        if (configData.notifications) {
          setNotificationSettings(configData.notifications);
        }
        if (configData.api) {
          setApiSettings(configData.api);
        }
        if (configData.system) {
          setSystemConfig(configData.system);
        }
      } catch (error) {
        console.error('加载配置失败:', error);
        setSaveError('加载配置失败，使用默认设置');
      } finally {
        setIsLoading(false);
      }
    };
    
    loadSettings();
  }, []);

  /**
   * 保存设置
   */
  const saveSettings = async () => {
    setIsSaving(true);
    setSaveError(null);
    
    try {
      // 准备请求数据
      const requestData = {
        basic: settings,
        notifications: notificationSettings,
        api: apiSettings
      };
      
      console.log('保存设置:', requestData);
      
      // 调用API保存配置
      await configApi.updateConfig(requestData);
      
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
  const saveSystemConfig = async () => {
    setIsSaving(true);
    setSaveError(null);
    
    try {
      // 准备请求数据
      const requestData = {
        system: systemConfig
      };
      
      console.log('保存系统配置:', requestData);
      
      // 调用API保存配置
      await configApi.updateConfig(requestData);
      
      // 显示成功消息
      setShowSuccessMessage(true);
      setTimeout(() => {
        setShowSuccessMessage(false);
      }, 3000);
    } catch (error) {
      // 处理错误
      console.error('保存系统配置失败:', error);
      setSaveError('保存系统配置失败，请稍后重试');
      setTimeout(() => {
        setSaveError(null);
      }, 3000);
    } finally {
      setIsSaving(false);
    }
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

  const { Sider, Content } = Layout;
  const { Text } = Typography;

  // 菜单项配置
  const menuConfig = [
    { key: 'basic', label: '基本设置', icon: <UserOutlined /> },
    { key: 'system-config', label: '系统配置', icon: <SettingOutlined /> },
    { key: 'notifications', label: '通知设置', icon: <BellOutlined /> },
    { key: 'api', label: 'API 配置', icon: <ApiOutlined /> },
    { key: 'system', label: '系统信息', icon: <InfoCircleOutlined /> }
  ];

  return (
    <Layout className="settings-container">
      {/* 页面头部 */}
      {/* <Header className="page-header">
        <Title level={2} style={{ color: '#333', margin: 0, fontSize: '20px', fontWeight: 500 }}>系统设置</Title>
      </Header> */}

      <Layout>
        {/* 侧边栏导航 */}
        <Sider width={200} className="settings-sidebar">
          <Menu
            mode="inline"
            selectedKeys={[currentTab]}
            items={menuConfig}
            onSelect={({ key }) => setCurrentTab(key)}
            style={{ height: '100%', borderRight: 0 }}
          />
        </Sider>

        {/* 主内容区域 */}
        <Content className="settings-main">
          {/* 基本设置 */}
          {currentTab === 'basic' && (
            <Card className="settings-panel" title="基本设置" bordered>
              <Form
                layout="vertical"
                initialValues={settings}
              >
                <Form.Item label="个人信息" name="personal" noStyle>
                  <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      label="用户名"
                      name="username"
                      rules={[{ required: true, message: '请输入用户名' }]}
                    >
                      <Input disabled />
                    </Form.Item>
                    <Form.Item
                      label="显示名称"
                      name="displayName"
                      rules={[{ required: true, message: '请输入显示名称' }]}
                    >
                      <Input 
                        placeholder="请输入显示名称" 
                        onChange={(e) => setSettings(prev => ({ ...prev, displayName: e.target.value }))}
                      />
                    </Form.Item>
                    <Form.Item
                      label="邮箱"
                      name="email"
                      rules={[
                        { required: true, message: '请输入邮箱地址' },
                        { type: 'email', message: '请输入有效的邮箱地址' }
                      ]}
                    >
                      <Input 
                        placeholder="请输入邮箱地址" 
                        onChange={(e) => setSettings(prev => ({ ...prev, email: e.target.value }))}
                      />
                    </Form.Item>
                  </Card>
                </Form.Item>

                <Form.Item label="界面设置" name="interface" noStyle>
                  <Card size="small">
                    <Form.Item
                      label="主题"
                      name="theme"
                      rules={[{ required: true, message: '请选择主题' }]}
                    >
                      <Select 
                        onChange={(value) => setSettings(prev => ({ ...prev, theme: value as 'light' | 'dark' | 'auto' }))}
                      >
                        <Select.Option value="light">浅色</Select.Option>
                        <Select.Option value="dark">深色</Select.Option>
                        <Select.Option value="auto">跟随系统</Select.Option>
                      </Select>
                    </Form.Item>
                    <Form.Item
                      label="语言"
                      name="language"
                      rules={[{ required: true, message: '请选择语言' }]}
                    >
                      <Select 
                        onChange={(value) => setSettings(prev => ({ ...prev, language: value as 'zh-CN' | 'en-US' }))}
                      >
                        <Select.Option value="zh-CN">简体中文</Select.Option>
                        <Select.Option value="en-US">English (US)</Select.Option>
                      </Select>
                    </Form.Item>
                    <Form.Item
                      name="showTips"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="显示" 
                        unCheckedChildren="隐藏" 
                        onChange={(checked) => setSettings(prev => ({ ...prev, showTips: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>显示功能提示</Text>
                    </Form.Item>
                  </Card>
                </Form.Item>

                {/* 底部操作按钮 */}
                <div className="settings-footer">
                  <Space>
                    <Button 
                      type="default" 
                      onClick={resetSettings} 
                      disabled={isSaving}
                      icon={<ReloadOutlined />}
                    >
                      重置
                    </Button>
                    <Button 
                      type="primary" 
                      onClick={saveSettings} 
                      disabled={isSaving}
                      icon={<SaveOutlined />}
                    >
                      {isSaving ? '保存中...' : '保存设置'}
                    </Button>
                  </Space>
                </div>
              </Form>
            </Card>
          )}

          {/* 通知设置 */}
          {currentTab === 'notifications' && (
            <Card className="settings-panel" title="通知设置" bordered>
              <Form
                layout="vertical"
                initialValues={notificationSettings}
              >
                <Form.Item label="通知方式" name="notificationMethods" noStyle>
                  <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      name="enableEmail"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="启用" 
                        unCheckedChildren="禁用" 
                        onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableEmail: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>邮件通知</Text>
                    </Form.Item>
                    <Form.Item
                      name="enableWebhook"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="启用" 
                        unCheckedChildren="禁用" 
                        onChange={(checked) => setNotificationSettings(prev => ({ ...prev, enableWebhook: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>Webhook 通知</Text>
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
                </Form.Item>

                <Form.Item label="通知内容" name="notificationContent" noStyle>
                  <Card size="small">
                    <Form.Item
                      name="notifyOnAlert"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="启用" 
                        unCheckedChildren="禁用" 
                        onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnAlert: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>告警通知</Text>
                    </Form.Item>
                    <Form.Item
                      name="notifyOnTaskComplete"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="启用" 
                        unCheckedChildren="禁用" 
                        onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnTaskComplete: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>任务完成通知</Text>
                    </Form.Item>
                    <Form.Item
                      name="notifyOnSystemUpdate"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="启用" 
                        unCheckedChildren="禁用" 
                        onChange={(checked) => setNotificationSettings(prev => ({ ...prev, notifyOnSystemUpdate: checked }))}
                      />
                      <Text style={{ marginLeft: 8 }}>系统更新通知</Text>
                    </Form.Item>
                  </Card>
                </Form.Item>

                {/* 底部操作按钮 */}
                <div className="settings-footer">
                  <Space>
                    <Button 
                      type="default" 
                      onClick={resetSettings}
                      icon={<ReloadOutlined />}
                    >
                      重置
                    </Button>
                    <Button 
                      type="primary" 
                      onClick={saveSettings}
                      icon={<SaveOutlined />}
                    >
                      保存设置
                    </Button>
                  </Space>
                </div>
              </Form>
            </Card>
          )}

          {/* API 配置 */}
          {currentTab === 'api' && (
            <Card className="settings-panel" title="API 配置" bordered>
              <Form
                layout="vertical"
                initialValues={apiSettings}
              >
                <Form.Item label="API 密钥" name="apiKeySection" noStyle>
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
                </Form.Item>

                <Form.Item label="API 权限" name="apiPermissions" noStyle>
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
                </Form.Item>

                {/* 底部操作按钮 */}
                <div className="settings-footer">
                  <Space>
                    <Button 
                      type="default" 
                      onClick={resetSettings}
                      icon={<ReloadOutlined />}
                    >
                      重置
                    </Button>
                    <Button 
                      type="primary" 
                      onClick={saveSettings}
                      icon={<SaveOutlined />}
                    >
                      保存设置
                    </Button>
                  </Space>
                </div>
              </Form>
            </Card>
          )}

          {/* 系统配置 */}
          {currentTab === 'system-config' && (
            <Card className="settings-panel" title="系统配置" bordered>
              <Form
                layout="vertical"
                initialValues={systemConfig}
              >
                {/* 数据目录配置 */}
                <Form.Item label="数据目录配置" name="dataDirConfig" noStyle>
                  <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      label="QLib数据目录"
                      name="qlib_data_dir"
                      rules={[{ required: true, message: '请输入QLib数据目录' }]}
                    >
                      <Input 
                        placeholder="请输入QLib数据目录" 
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, qlib_data_dir: e.target.value }))}
                      />
                    </Form.Item>
                    <Form.Item
                      label="数据下载目录"
                      name="data_download_dir"
                      rules={[{ required: true, message: '请输入数据下载目录' }]}
                    >
                      <Input 
                        placeholder="请输入数据下载目录" 
                        onChange={(e) => setSystemConfig(prev => ({ ...prev, data_download_dir: e.target.value }))}
                      />
                    </Form.Item>
                  </Card>
                </Form.Item>

                {/* 交易设置 */}
                <Form.Item label="交易设置" name="tradingConfig" noStyle>
                  <Card size="small" style={{ marginBottom: 16 }}>
                    <Form.Item
                      label="当前交易模式"
                      name="current_market_type"
                      rules={[{ required: true, message: '请选择交易模式' }]}
                    >
                      <Select 
                        onChange={(value) => setSystemConfig(prev => ({ ...prev, current_market_type: value }))}
                      >
                        <Select.Option value="crypto">加密货币</Select.Option>
                        <Select.Option value="stock">股票</Select.Option>
                      </Select>
                    </Form.Item>
                    
                    {systemConfig.current_market_type === 'crypto' && (
                      <>
                        <Form.Item
                          label="加密货币蜡烛图类型"
                          name="crypto_trading_mode"
                          rules={[{ required: true, message: '请选择蜡烛图类型' }]}
                        >
                          <Select 
                            onChange={(value) => setSystemConfig(prev => ({ ...prev, crypto_trading_mode: value }))}
                          >
                            <Select.Option value="spot">现货</Select.Option>
                            <Select.Option value="futures">期货</Select.Option>
                          </Select>
                        </Form.Item>
                        <Form.Item
                          label="默认交易所"
                          name="default_exchange"
                          rules={[{ required: true, message: '请选择默认交易所' }]}
                        >
                          <Select 
                            onChange={(value) => setSystemConfig(prev => ({ ...prev, default_exchange: value }))}
                          >
                            <Select.Option value="binance">Binance</Select.Option>
                            <Select.Option value="okx">OKX</Select.Option>
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
                      label="默认时间间隔"
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
                  </Card>
                </Form.Item>

                {/* 代理设置 */}
                <Form.Item label="代理设置" name="proxyConfig" noStyle>
                  <Card size="small">
                    <Form.Item
                      name="proxy_enabled"
                      valuePropName="checked"
                    >
                      <Switch 
                        checkedChildren="启用" 
                        unCheckedChildren="禁用" 
                        onChange={(checked) => setSystemConfig(prev => ({ ...prev, proxy_enabled: checked ? 'true' : 'false' }))}
                      />
                      <Text style={{ marginLeft: 8 }}>是否启动代理</Text>
                    </Form.Item>
                    
                    {systemConfig.proxy_enabled === 'true' && (
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
                </Form.Item>

                {/* 底部操作按钮 */}
                <div className="settings-footer">
                  <Space>
                    <Button 
                      type="default" 
                      onClick={resetSystemConfig}
                      icon={<ReloadOutlined />}
                    >
                      重置
                    </Button>
                    <Button 
                      type="primary" 
                      onClick={saveSystemConfig}
                      icon={<SaveOutlined />}
                    >
                      保存设置
                    </Button>
                  </Space>
                </div>
              </Form>
            </Card>
          )}

          {/* 系统信息 */}
          {currentTab === 'system' && (
            <Card className="settings-panel" title="系统信息" bordered>
              {/* 加载状态 */}
              {isLoading ? (
                <div className="loading-state" style={{ textAlign: 'center', padding: '40px' }}>
                  <div className="loading-spinner"></div>
                  <span style={{ display: 'block', marginTop: '16px' }}>加载系统信息中...</span>
                </div>
              ) : saveError ? (
                <div className="error-state" style={{ textAlign: 'center', padding: '40px' }}>
                  <div className="error-icon" style={{ fontSize: '24px', marginBottom: '8px' }}>⚠️</div>
                  <span style={{ display: 'block', marginBottom: '16px' }}>{saveError}</span>
                  <Button type="default" onClick={() => setIsLoading(true)}>
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
          )}
        </Content>
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