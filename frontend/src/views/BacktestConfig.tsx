/**
 * 回测配置页面组件
 * 功能：配置策略回测参数，包括策略信息和回测信息
 */
import React, { useState, useEffect } from 'react';
import dayjs from 'dayjs';
import {
  Card,
  Form,
  Input,
  Select,
  DatePicker,
  InputNumber,
  Button,
  Space,
  Row,
  Col,
  Spin,
  message,
  Modal,
  Upload,
  Tabs,
  Switch,
  Tooltip,
} from 'antd';
import { BackwardOutlined, PlusOutlined, UploadOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { backtestApi, configApi, strategyApi } from '../api';

const { RangePicker } = DatePicker;
const { Option } = Select;
const { TabPane } = Tabs;
const { Dragger } = Upload;

interface StrategyParam {
  name: string;
  type: string;
  default: any;
  description: string;
  required: boolean;
}

interface Strategy {
  name: string;
  file_name: string;
  file_path: string;
  description: string;
  version: string;
  tags?: string[];
  params: StrategyParam[];
  created_at: string;
  updated_at: string;
}

interface BacktestConfigProps {
  onBack: () => void;
  onRunBacktest: () => void;
  strategy?: Strategy; // 新增：接收外部传入的策略信息
}

const BacktestConfig: React.FC<BacktestConfigProps> = ({ onBack, onRunBacktest, strategy }) => {
  const [form] = Form.useForm();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [defaultInterval, setDefaultInterval] = useState<string>('1d'); // 系统配置的默认时间间隔
  const [defaultCommission, setDefaultCommission] = useState<number>(0.001); // 系统配置的默认手续费
  const [defaultInitialCash, setDefaultInitialCash] = useState<number>(1000000); // 系统配置的默认初始资金
  
  // 策略创建相关状态
  const [createModalVisible, setCreateModalVisible] = useState<boolean>(false);
  const [createForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState<string>('new'); // 'new' 或 'upload'
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // 加载系统配置
  const loadSystemConfig = async () => {
    try {
      const configData = await configApi.getConfig();
      console.log('系统配置响应:', configData);
      
      // 正确处理后端返回的数据格式，提取配置项
      if (configData && typeof configData === 'object') {
        // 检查配置数据的格式，可能是直接对象或包含configs字段
        let configs: any = configData;
        if (configData.configs && typeof configData.configs === 'object') {
          configs = configData.configs;
        }
        
        // 获取default_interval配置
        const intervalConfig = configs.default_interval || configs.DEFAULT_INTERVAL;
        if (intervalConfig) {
          // 如果是对象形式，可能包含value字段
          const intervalValue = intervalConfig.value || intervalConfig;
          setDefaultInterval(intervalValue);
          console.log('成功加载默认时间间隔:', intervalValue);
        }
        
        // 获取default_commission配置
        const commissionConfig = configs.default_commission || configs.DEFAULT_COMMISSION;
        if (commissionConfig !== undefined) {
          // 如果是对象形式，可能包含value字段
          const commissionValue = commissionConfig.value || commissionConfig;
          setDefaultCommission(Number(commissionValue));
          console.log('成功加载默认手续费:', commissionValue);
        }
        
        // 获取default_initial_cash配置
        const initialCashConfig = configs.default_initial_cash || configs.DEFAULT_INITIAL_CASH;
        if (initialCashConfig !== undefined) {
          // 如果是对象形式，可能包含value字段
          const initialCashValue = initialCashConfig.value || initialCashConfig;
          setDefaultInitialCash(Number(initialCashValue));
          console.log('成功加载默认初始资金:', initialCashValue);
        }
      }
    } catch (error) {
      console.error('加载系统配置失败:', error);
      // 使用默认值，不影响组件正常使用
      setDefaultInterval('1d');
      setDefaultCommission(0.001);
      setDefaultInitialCash(1000000);
    }
  };

  // 加载策略列表
  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await backtestApi.getStrategies();
      console.log('策略列表响应:', response);
      
      // 正确处理后端返回的数据格式，从响应对象中提取strategies字段
      if (response && typeof response === 'object' && Array.isArray(response.strategies)) {
        setStrategies(response.strategies);
        console.log('成功加载策略列表:', response.strategies);
      } else {
        setStrategies([]);
        console.error('策略列表数据格式错误:', response);
        message.warning('策略列表数据格式错误，显示空列表');
      }
    } catch (error) {
      console.error('加载策略列表失败:', error);
      message.error('加载策略列表失败');
      // 即使出错，也要确保strategies是数组
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  };

  // 组件挂载时加载策略列表和系统配置
  useEffect(() => {
    loadStrategies();
    loadSystemConfig();
  }, []);

  // 当传入的策略信息变化时，初始化表单
  useEffect(() => {
    if (strategy) {
      setSelectedStrategy(strategy);
      
      // 构建默认参数对象
      const defaultParams: Record<string, any> = {};
      if (strategy.params) {
        strategy.params.forEach(p => {
          defaultParams[p.name] = p.default;
        });
      }

      // 设置表单值，包括策略名称和默认参数
      form.setFieldsValue({
        strategy: strategy.name,
        params: defaultParams,
      });

      // 如果是demo策略，自动填充回测配置
      if (strategy.tags && strategy.tags.includes('demo')) {
        form.setFieldsValue({
          symbols: ['BTC/USDT'],
          timeRange: [dayjs('2024-01-01'), dayjs('2024-02-01')],
          interval: '15m',
          initialCash: 100000,
          commission: 0.001
        });
        message.info('已自动填充演示策略的回测配置');
      }
    }
  }, [strategy, form]);

  // 当默认配置项变化时，更新表单初始值
  useEffect(() => {
    form.setFieldsValue({
      interval: defaultInterval,
      commission: defaultCommission,
      initialCash: defaultInitialCash
    });
  }, [defaultInterval, defaultCommission, defaultInitialCash, form]);

  // 打开策略创建模态框
  const handleCreateStrategy = () => {
    setCreateModalVisible(true);
    createForm.resetFields();
    setActiveTab('new');
    setUploadFile(null);
  };

  // 关闭策略创建模态框
  const handleCreateModalClose = () => {
    setCreateModalVisible(false);
  };

  // 处理策略创建提交
  const handleCreateSubmit = async (values: any) => {
    try {
      setLoading(true);
      
      if (activeTab === 'new') {
        // 创建新策略
        const strategyData = {
          name: values.strategyName,
          description: values.description,
          params: values.params ? JSON.parse(values.params) : {},
        };
        
        await strategyApi.createStrategy(strategyData);
        message.success('策略创建成功');
      } else if (activeTab === 'upload' && uploadFile) {
        // 上传策略文件
        const formData = new FormData();
        formData.append('file', uploadFile);
        formData.append('name', values.strategyName || uploadFile.name.replace('.py', ''));
        
        await backtestApi.uploadStrategy(formData);
        message.success('策略上传成功');
      }
      
      // 重新加载策略列表
      loadStrategies();
      setCreateModalVisible(false);
    } catch (error) {
      console.error('创建策略失败:', error);
      message.error('创建策略失败');
    } finally {
      setLoading(false);
    }
  };

  // 处理文件上传
  const handleFileUpload = (file: File) => {
    setUploadFile(file);
    return false; // 阻止自动上传
  };

  // 处理策略变更
  const handleStrategyChange = (value: string) => {
    const strategy = strategies.find(s => s.name === value);
    setSelectedStrategy(strategy || null);
    
    if (strategy && strategy.params) {
      // 构建默认参数对象
      const defaultParams: Record<string, any> = {};
      strategy.params.forEach(param => {
        defaultParams[param.name] = param.default;
      });
      form.setFieldValue('params', defaultParams);

      // 如果是demo策略，自动填充回测配置
      if (strategy.tags && strategy.tags.includes('demo')) {
        form.setFieldsValue({
          symbols: ['BTC/USDT'],
          timeRange: [dayjs('2024-01-01'), dayjs('2024-02-01')],
          interval: '15m',
          initialCash: 100000,
          commission: 0.001
        });
        message.info('已自动填充演示策略的回测配置');
      }
    } else {
      form.setFieldValue('params', {});
    }
  };

  // 渲染参数输入控件
  const renderParamInput = (param: StrategyParam) => {
    const type = param.type ? param.type.toLowerCase() : 'string';
    
    if (type === 'int' || type === 'integer') {
      return <InputNumber style={{ width: '100%' }} precision={0} />;
    }
    if (type === 'float' || type === 'number') {
      return <InputNumber style={{ width: '100%' }} step={0.01} />;
    }
    if (type === 'bool' || type === 'boolean') {
      return <Switch />;
    }
    return <Input />;
  };

  // 处理表单提交
  const handleSubmit = async (values: any) => {
    try {
      setLoading(true);
      
      // 验证timeRange
      if (!values.timeRange || values.timeRange.length !== 2) {
        message.error('请选择有效的回测时间范围');
        return;
      }
      
      // 格式化时间
      const [startTime, endTime] = values.timeRange;
      
      // 获取策略参数
      const strategyParams = values.params || {};
      
      // 构建回测请求数据
      const backtestData = {
        strategy_config: {
          strategy_name: values.strategy,
          params: strategyParams,
        },
        backtest_config: {
          symbols: values.symbols,
          start_time: startTime.format('YYYY-MM-DD'),
          end_time: endTime.format('YYYY-MM-DD'),
          interval: values.interval,
          commission: values.commission,
          initial_cash: values.initialCash,
        },
      };

      // 调用回测API
      await backtestApi.runBacktest(backtestData);
      message.success('回测已开始执行');
      
      // 返回回测列表页面
      onRunBacktest();
    } catch (error: any) {
      console.error('执行回测失败:', error);
      message.error(error.message || '执行回测失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="backtest-config-container">
      <Card
        title={
          <div className="card-header">
            <Button
              type="text"
              icon={<BackwardOutlined />}
              onClick={onBack}
              style={{ marginRight: 16 }}
            >
              返回
            </Button>
            回测配置
          </div>
        }
      >
        <Spin spinning={loading}>
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
            initialValues={{
              interval: '1d',
              commission: 0.001,
              initialCash: 1000000,
              symbols: ['BTC/USDT'],
              timeRange: [dayjs().subtract(30, 'day'), dayjs()],
            }}
          >
            {/* 策略信息部分 */}
            <Card type="inner" title="策略信息" style={{ marginBottom: 24 }}>
              <Row gutter={16}>
                <Col span={24}>
                  <Form.Item
                    name="strategy"
                    label="策略名称"
                    rules={[{ required: true, message: '请选择策略名称' }]}
                  >
                    <Select 
                      placeholder="请选择策略"
                      style={{ width: '100%' }}
                      onChange={handleStrategyChange}
                    >
                      {strategies.map((strategy) => (
                        <Option key={strategy.name} value={strategy.name}>
                          {strategy.name}
                          {strategy.tags && strategy.tags.includes('demo') && (
                            <span style={{ 
                              marginLeft: 8, 
                              fontSize: 12, 
                              color: '#1890ff', 
                              background: '#e6f7ff', 
                              padding: '2px 6px', 
                              borderRadius: 4, 
                              border: '1px solid #91d5ff' 
                            }}>
                              demo
                            </span>
                          )}
                        </Option>
                      ))}
                    </Select>
                  </Form.Item>
                  <div style={{ marginBottom: 16, textAlign: 'right' }}>
                    <Button 
                      type="dashed" 
                      icon={<PlusOutlined />} 
                      onClick={handleCreateStrategy}
                    >
                      创建新策略
                    </Button>
                  </div>
                </Col>

                <Col span={24}>
                  <div style={{ marginBottom: 8 }}>策略参数配置</div>
                  {selectedStrategy?.params && selectedStrategy.params.length > 0 ? (
                    <div style={{ background: '#f5f5f5', padding: '16px', borderRadius: '4px' }}>
                      <Row gutter={24}>
                        {selectedStrategy.params.map((param) => (
                          <Col span={12} key={param.name}>
                            <Form.Item
                              name={['params', param.name]}
                              label={
                                <span>
                                  {param.name}
                                  {param.description && (
                                    <Tooltip title={param.description}>
                                      <InfoCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
                                    </Tooltip>
                                  )}
                                </span>
                              }
                              initialValue={param.default}
                              valuePropName={
                                (param.type === 'bool' || param.type === 'boolean') ? 'checked' : 'value'
                              }
                            >
                              {renderParamInput(param)}
                            </Form.Item>
                          </Col>
                        ))}
                      </Row>
                    </div>
                  ) : (
                    <div style={{ color: '#999', textAlign: 'center', padding: '20px 0', border: '1px dashed #d9d9d9', borderRadius: '4px' }}>
                      {selectedStrategy ? '该策略没有可配置参数' : '请先选择策略以配置参数'}
                    </div>
                  )}
                </Col>
              </Row>
            </Card>

            {/* 回测信息部分 */}
            <Card type="inner" title="回测信息" style={{ marginBottom: 24 }}>
              <Row gutter={16}>
                <Col span={24}>
                  <Form.Item
                    name="symbols"
                    label="交易标的"
                    rules={[{ required: true, message: '请选择交易标的' }]}
                  >
                    <Select
                      mode="tags"
                      placeholder="请输入或选择交易标的 (如 BTC/USDT)"
                      style={{ width: '100%' }}
                      tokenSeparators={[',']}
                    >
                      <Option value="BTC/USDT">BTC/USDT</Option>
                      <Option value="ETH/USDT">ETH/USDT</Option>
                    </Select>
                  </Form.Item>
                </Col>

                <Col span={12}>
                  <Form.Item
                    name="timeRange"
                    label="时间范围"
                    rules={[{ required: true, message: '请选择回测时间范围' }]}
                  >
                    <RangePicker
                      format="YYYY-MM-DD"
                      placeholder={['开始日期', '结束日期']}
                    />
                  </Form.Item>
                </Col>

                <Col span={12}>
                  <Form.Item
                    name="interval"
                    label="周期"
                    rules={[{ required: true, message: '请选择回测周期' }]}
                  >
                    <Select placeholder="请选择回测周期">
                      <Option value="1m">1分钟</Option>
                      <Option value="5m">5分钟</Option>
                      <Option value="15m">15分钟</Option>
                      <Option value="30m">30分钟</Option>
                      <Option value="1h">1小时</Option>
                      <Option value="4h">4小时</Option>
                      <Option value="1d">1天</Option>
                    </Select>
                  </Form.Item>
                </Col>

                <Col span={12}>
                  <Form.Item
                    name="commission"
                    label="手续费"
                    rules={[{ required: true, message: '请输入手续费率' }]}
                  >
                    <InputNumber
                      placeholder="请输入手续费率"
                      min={0}
                      max={1}
                      step={0.0001}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>

                <Col span={12}>
                  <Form.Item
                    name="initialCash"
                    label="初始资金"
                    rules={[{ required: true, message: '请输入初始资金' }]}
                  >
                    <InputNumber
                      placeholder="请输入初始资金"
                      min={1000}
                      max={100000000}
                      step={1000}
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Card>

            {/* 操作按钮 */}
            <Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" loading={loading}>
                  运行回测
                </Button>
                <Button onClick={onBack}>
                  取消
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Spin>
      </Card>

      {/* 策略创建模态框 */}
      <Modal
        title="创建策略"
        open={createModalVisible}
        onCancel={handleCreateModalClose}
        footer={null}
        width={800}
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="新建策略" key="new">
            <Form
              form={createForm}
              layout="vertical"
              onFinish={handleCreateSubmit}
              initialValues={{
                params: "{}",
              }}
            >
              <Form.Item
                name="strategyName"
                label="策略名称"
                rules={[{ required: true, message: '请输入策略名称' }]}
              >
                <Input placeholder="请输入策略名称" />
              </Form.Item>
              
              <Form.Item
                name="description"
                label="策略描述"
              >
                <Input.TextArea placeholder="请输入策略描述" rows={3} />
              </Form.Item>
              
              <Form.Item
                name="params"
                label="策略参数"
                rules={[
                  {
                    validator: (_, value) => {
                      try {
                        if (value) {
                          JSON.parse(value);
                        }
                        return Promise.resolve();
                      } catch (error) {
                        return Promise.reject(new Error('策略参数必须是有效的JSON格式'));
                      }
                    },
                  },
                ]}
              >
                <Input.TextArea 
                  placeholder="请输入策略参数，格式为JSON字符串" 
                  rows={4} 
                />
              </Form.Item>
              
              <Form.Item style={{ textAlign: 'right' }}>
                <Space>
                  <Button onClick={handleCreateModalClose}>取消</Button>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    创建设置
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </TabPane>
          
          <TabPane tab="上传策略文件" key="upload">
            <Form
              form={createForm}
              layout="vertical"
              onFinish={handleCreateSubmit}
            >
              <Form.Item
                name="strategyName"
                label="策略名称"
                rules={[{ required: true, message: '请输入策略名称' }]}
              >
                <Input placeholder="请输入策略名称（留空则使用文件名）" />
              </Form.Item>
              
              <Form.Item label="上传策略文件">
                <Dragger
                  name="file"
                  multiple={false}
                  beforeUpload={handleFileUpload}
                  showUploadList={false}
                  accept=".py"
                >
                  <p className="ant-upload-drag-icon">
                    <UploadOutlined />
                  </p>
                  <p className="ant-upload-text">点击或拖拽Python文件到此处上传</p>
                  <p className="ant-upload-hint">
                    支持单个Python文件上传，文件大小不超过2MB
                  </p>
                </Dragger>
                {uploadFile && (
                  <div style={{ marginTop: 16 }}>
                    <p>已选择文件: {uploadFile.name}</p>
                  </div>
                )}
              </Form.Item>
              
              <Form.Item style={{ textAlign: 'right' }}>
                <Space>
                  <Button onClick={handleCreateModalClose}>取消</Button>
                  <Button type="primary" htmlType="submit" loading={loading}>
                    上传策略
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </TabPane>
        </Tabs>
      </Modal>
    </div>
  );
};

export default BacktestConfig;