/**
 * 交易所配置模块
 * 功能：提供交易所连接配置和测试连接功能
 */
import { useState } from 'react';
import { Card, Form, Input, Select, Switch, Button, Space, Alert, Tag } from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, ApiOutlined, LoadingOutlined } from '@ant-design/icons';
import type { SystemConfig as SystemConfigType } from './types';
import { exchangeApi } from '@/api/index';

interface ExchangeConfigProps {
  systemConfig: SystemConfigType;
  setSystemConfig: React.Dispatch<React.SetStateAction<SystemConfigType>>;
}

// 连接测试结果类型
interface TestResult {
  success: boolean;
  status: string;
  message: string;
  response_time_ms?: number;
  details?: {
    tests?: {
      ping?: { success: boolean; error?: string };
      status?: { success: boolean; error?: string };
      market_data?: { success: boolean; symbol?: string; last_price?: number; error?: string };
      authentication?: { success: boolean; balance_available?: boolean; skipped?: boolean; reason?: string; error?: string };
    };
    exchange?: string;
    has_api_key?: boolean;
  };
}

const ExchangeConfig = ({
  systemConfig,
  setSystemConfig
}: ExchangeConfigProps) => {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);

  // 执行连接测试
  const handleTestConnection = async () => {
    setTesting(true);
    setTestResult(null);

    try {
      const result = await exchangeApi.testConnection({
        exchange_name: systemConfig.default_exchange,
        api_key: systemConfig.exchange_api_key || undefined,
        secret_key: systemConfig.exchange_secret_key || undefined,
        api_passphrase: systemConfig.exchange_api_passphrase || undefined,
        proxy_url: systemConfig.proxy_enabled ? systemConfig.proxy_url : undefined,
        trading_mode: systemConfig.crypto_trading_mode,
        testnet: systemConfig.exchange_testnet || false,
      });

      setTestResult(result);
    } catch (error: any) {
      setTestResult({
        success: false,
        status: 'error',
        message: error.message || '测试连接失败',
      });
    } finally {
      setTesting(false);
    }
  };

  // 获取状态标签颜色
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success':
        return 'success';
      case 'network_error':
      case 'proxy_error':
        return 'error';
      case 'auth_error':
      case 'permission_error':
        return 'warning';
      case 'timeout_error':
        return 'processing';
      default:
        return 'default';
    }
  };

  // 获取状态文本
  const getStatusText = (status: string) => {
    const statusMap: Record<string, string> = {
      success: '连接成功',
      network_error: '网络错误',
      auth_error: '认证失败',
      permission_error: '权限不足',
      proxy_error: '代理错误',
      timeout_error: '连接超时',
      unknown_error: '未知错误',
    };
    return statusMap[status] || status;
  };

  return (
    <div className="space-y-4">
      {/* 交易所选择 */}
      <Card size="small" title="交易所配置" className="mb-4">
        <Form layout="vertical">
          <Form.Item
            label="默认交易所"
            required
          >
            <Select
              value={systemConfig.default_exchange}
              onChange={(value) => setSystemConfig(prev => ({ ...prev, default_exchange: value }))}
              placeholder="请选择交易所"
            >
              <Select.Option value="binance">Binance (币安)</Select.Option>
              <Select.Option value="okx">OKX (欧易)</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="交易模式"
            required
          >
            <Select
              value={systemConfig.crypto_trading_mode}
              onChange={(value) => setSystemConfig(prev => ({ ...prev, crypto_trading_mode: value }))}
            >
              <Select.Option value="spot">现货</Select.Option>
              <Select.Option value="future">合约</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item
            label="测试网络"
          >
            <Switch
              checked={systemConfig.exchange_testnet || false}
              onChange={(checked) => setSystemConfig(prev => ({ ...prev, exchange_testnet: checked }))}
              checkedChildren="启用"
              unCheckedChildren="禁用"
            />
            <span className="ml-2 text-gray-500 text-sm">使用交易所测试网络（模拟交易环境）</span>
          </Form.Item>
        </Form>
      </Card>

      {/* API配置 */}
      <Card size="small" title="API配置" className="mb-4">
        <Form layout="vertical">
          <Form.Item
            label="API Key"
          >
            <Input.Password
              value={systemConfig.exchange_api_key || ''}
              onChange={(e) => setSystemConfig(prev => ({ ...prev, exchange_api_key: e.target.value }))}
              placeholder="请输入API Key"
            />
          </Form.Item>

          <Form.Item
            label="Secret Key"
          >
            <Input.Password
              value={systemConfig.exchange_secret_key || ''}
              onChange={(e) => setSystemConfig(prev => ({ ...prev, exchange_secret_key: e.target.value }))}
              placeholder="请输入Secret Key"
            />
          </Form.Item>

          {systemConfig.default_exchange === 'okx' && (
            <Form.Item
              label="API密码 (Passphrase)"
            >
              <Input.Password
                value={systemConfig.exchange_api_passphrase || ''}
                onChange={(e) => setSystemConfig(prev => ({ ...prev, exchange_api_passphrase: e.target.value }))}
                placeholder="请输入API密码（OKX必填）"
              />
            </Form.Item>
          )}
        </Form>
      </Card>

      {/* 测试连接按钮 */}
      <Card size="small" title="连接测试" className="mb-4">
        <Space direction="vertical" className="w-full">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-gray-600 text-sm mb-1">
                测试交易所连接状态、API Key有效性及代理设置
              </p>
              <p className="text-gray-400 text-xs">
                测试过程中不会产生实际交易或资金变动
              </p>
            </div>
            <Button
              type="primary"
              icon={testing ? <LoadingOutlined /> : <ApiOutlined />}
              onClick={handleTestConnection}
              loading={testing}
              disabled={testing}
            >
              {testing ? '测试中...' : '测试连接'}
            </Button>
          </div>

          {/* 测试结果 */}
          {testResult && (
            <Alert
              message={
                <div className="flex items-center gap-2">
                  {testResult.success ? (
                    <CheckCircleOutlined className="text-green-500" />
                  ) : (
                    <CloseCircleOutlined className="text-red-500" />
                  )}
                  <span>{testResult.message}</span>
                  {testResult.response_time_ms && (
                    <Tag color="blue">{testResult.response_time_ms}ms</Tag>
                  )}
                </div>
              }
              description={
                <div className="mt-2">
                  <div className="flex items-center gap-2 mb-2">
                    <span>状态:</span>
                    <Tag color={getStatusColor(testResult.status)}>
                      {getStatusText(testResult.status)}
                    </Tag>
                  </div>

                  {/* 详细测试结果 */}
                  {testResult.details?.tests && (
                    <div className="mt-3 pt-3 border-t border-gray-200">
                      <div className="grid grid-cols-2 gap-2 text-sm">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500">网络连接:</span>
                          {testResult.details.tests.ping?.success ? (
                            <span className="text-green-600 text-xs">通过</span>
                          ) : (
                            <span className="text-red-600 text-xs">失败</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500">交易所状态:</span>
                          {testResult.details.tests.status?.success ? (
                            <span className="text-green-600 text-xs">正常</span>
                          ) : (
                            <span className="text-orange-500 text-xs">异常</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500">市场数据:</span>
                          {testResult.details.tests.market_data?.success ? (
                            <span className="text-green-600 text-xs">正常</span>
                          ) : (
                            <span className="text-orange-500 text-xs">异常</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500">API认证:</span>
                          {testResult.details.tests.authentication?.skipped ? (
                            <span className="text-gray-500 text-xs">未测试</span>
                          ) : testResult.details.tests.authentication?.success ? (
                            <span className="text-green-600 text-xs">通过</span>
                          ) : (
                            <span className="text-red-600 text-xs">失败</span>
                          )}
                        </div>
                      </div>

                      {/* 详细信息展开 */}
                      {testResult.details.tests.market_data?.last_price && (
                        <div className="mt-2 text-sm text-gray-600">
                          BTC/USDT 最新价格: ${testResult.details.tests.market_data.last_price.toLocaleString()}
                        </div>
                      )}

                      {/* 错误详情 */}
                      {(testResult.details.tests.ping?.error ||
                        testResult.details.tests.authentication?.error) && (
                        <div className="mt-2 p-2 bg-gray-50 rounded text-xs text-gray-600">
                          {testResult.details.tests.ping?.error && (
                            <div>网络错误: {testResult.details.tests.ping.error}</div>
                          )}
                          {testResult.details.tests.authentication?.error && (
                            <div>认证错误: {testResult.details.tests.authentication.error}</div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              }
              type={testResult.success ? 'success' : 'error'}
              showIcon={false}
              className="mt-3"
            />
          )}
        </Space>
      </Card>
    </div>
  );
};

export default ExchangeConfig;
