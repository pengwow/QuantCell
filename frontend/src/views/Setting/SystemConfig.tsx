/**
 * 系统配置模块
 * 功能：提供数据目录、交易设置、代理配置等系统级配置
 */
import React from 'react';
import { Card, Form, Input, Select, Switch, InputNumber, Tooltip, Typography } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { SystemConfig } from './types';

interface SystemConfigProps {
  systemConfig: SystemConfig;
  setSystemConfig: React.Dispatch<React.SetStateAction<SystemConfig>>;
}

const SystemConfig: React.FC<SystemConfigProps> = ({
  systemConfig,
  setSystemConfig
}) => {
  const { Text } = Typography;
  const [systemConfigForm] = Form.useForm();

  return (
    <div style={{ display: 'block' }}>
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

          {/* 代理设置 */}
          <Card size="small" style={{ marginBottom: 16 }}>
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
          
          {/* 实时数据配置 */}
          <Card size="small">
            <Form.Item
              name="realtime_enabled"
              valuePropName="checked"
            >
              <div style={{ display: 'flex', alignItems: 'center' }}>
                <Switch
                  checkedChildren="启用"
                  unCheckedChildren="禁用"
                  onChange={(checked) => setSystemConfig(prev => ({ ...prev, realtime_enabled: checked }))}
                />
                <Text style={{ marginLeft: 8 }}>是否启用实时引擎</Text>
              </div>
            </Form.Item>
            
            {systemConfig.realtime_enabled && (
              <>
                <Form.Item
                  label={
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      数据模式
                      <Tooltip title="选择数据模式：实时模式直接从WebSocket获取数据，缓存模式从数据库缓存获取数据" placement="right">
                        <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                      </Tooltip>
                    </div>
                  }
                  name="data_mode"
                  rules={[{ required: true, message: '请选择数据模式' }]}
                >
                  <Select
                    onChange={(value) => setSystemConfig(prev => ({ ...prev, data_mode: value as 'realtime' | 'cache' }))}
                  >
                    <Select.Option value="realtime">实时模式</Select.Option>
                    <Select.Option value="cache">缓存模式</Select.Option>
                  </Select>
                </Form.Item>
                
                <Form.Item
                  label={
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      前端更新间隔(毫秒)
                      <Tooltip title="前端图表数据更新的时间间隔，单位为毫秒" placement="right">
                        <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                      </Tooltip>
                    </div>
                  }
                  name="frontend_update_interval"
                  rules={[{ required: true, message: '请输入前端更新间隔' }]}
                >
                  <InputNumber
                    onChange={(value: number | null) => setSystemConfig(prev => ({ ...prev, frontend_update_interval: value || 1000 }))}
                    min={100}
                    max={5000}
                    step={100}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
                
                <Form.Item
                  label={
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      前端数据缓存大小
                      <Tooltip title="前端图表缓存的数据点数量" placement="right">
                        <QuestionCircleOutlined style={{ marginLeft: 8, color: '#1890ff' }} />
                      </Tooltip>
                    </div>
                  }
                  name="frontend_data_cache_size"
                  rules={[{ required: true, message: '请输入前端数据缓存大小' }]}
                >
                  <InputNumber
                    onChange={(value: number | null) => setSystemConfig(prev => ({ ...prev, frontend_data_cache_size: value || 1000 }))}
                    min={100}
                    max={10000}
                    step={100}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </>
            )}
          </Card>
        </Form>
      </Card>
    </div>
  );
};

export default SystemConfig;
