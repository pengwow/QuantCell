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
import { BackwardOutlined, PlusOutlined, UploadOutlined, InfoCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { backtestApi, configApi, strategyApi, dataApi } from '../api';
import BacktestProgressModal, { type StepStatusState, type ProgressData } from '../components/BacktestProgressModal';

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
  const [defaultInterval, setDefaultInterval] = useState<string>('15m'); // 系统配置的默认时间间隔
  const [defaultCommission, setDefaultCommission] = useState<number>(0.001); // 系统配置的默认手续费
  const [defaultInitialCash, setDefaultInitialCash] = useState<number>(1000000); // 系统配置的默认初始资金
  
  // 策略创建相关状态
  const [createModalVisible, setCreateModalVisible] = useState<boolean>(false);
  const [createForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState<string>('new'); // 'new' 或 'upload'
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  // 回测进度弹窗状态
  const [progressVisible, setProgressVisible] = useState<boolean>(false);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [stepStatus, setStepStatus] = useState<StepStatusState>({
    dataPrep: 'wait',
    execution: 'wait',
    analysis: 'wait',
  });
  const [progressData, setProgressData] = useState<ProgressData>({
    overall: 0,
  });
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [, setCurrentTaskId] = useState<string>('');
  const [isBacktestRunning, setIsBacktestRunning] = useState<boolean>(false);
  const abortControllerRef = React.useRef<AbortController | null>(null);

  // 交易标的选项（参考数据采集页面的实现）
  const [symbolOptions, setSymbolOptions] = useState<Array<{ value: string; label: string; type: string; symbols?: string[] }>>([]);
  // 品种选项加载状态
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false);

  // 获取品种选项数据（参考数据采集页面的实现）
  const fetchSymbolOptions = async () => {
    try {
      setSymbolOptionsLoading(true);

      // 调用API获取品种选项数据
      const response = await dataApi.getCollectionSymbols({
        type: 'spot',
        exchange: 'binance'
      });

      // 处理数据池数据
      const dataPoolOptions = [];
      const directSymbolOptions = [];

      if (response) {
        // 处理数据池数据
        if (Array.isArray(response.data_pools)) {
          console.log('数据池数据:', response.data_pools);
          dataPoolOptions.push(...response.data_pools.map((pool: any) => ({
            value: `pool_${pool.id}`, // 使用pool_前缀标识数据池
            label: `⭐ ${pool.name}`, // 显示名称
            type: 'data_pool',
            symbols: pool.symbols
          })));
        }

        // 处理直接货币对数据
        if (Array.isArray(response.direct_symbols)) {
          directSymbolOptions.push(...response.direct_symbols.map((symbol: string) => ({
            value: symbol, // 直接使用货币对作为值
            label: symbol,
            type: 'direct_symbol'
          })));
        }
      }

      // 合并数据，数据池排在顶部
      const mergedOptions = [...dataPoolOptions, ...directSymbolOptions];
      setSymbolOptions(mergedOptions);
    } catch (error) {
      console.error('获取品种选项失败:', error);
      // 使用默认选项
      setSymbolOptions(getDefaultSymbolOptions());
    } finally {
      setSymbolOptionsLoading(false);
    }
  };

  // 获取数据池的货币对（用于回测提交时）
  const loadPoolSymbols = async (poolId: number) => {
    try {
      const response = await dataApi.getCollectionSymbols({
        type: 'spot',
        exchange: 'binance'
      });
      if (response && response.data_pools) {
        const pool = response.data_pools.find((p: any) => p.id === poolId);
        if (pool && pool.symbols) {
          return pool.symbols;
        }
      }
    } catch (error) {
      console.error('加载数据池货币对失败:', error);
    }
    return [];
  };

  // 获取默认交易标的选项（平铺结构，与数据采集页面一致）
  const getDefaultSymbolOptions = () => [
    { value: 'BTC/USDT', label: 'BTC/USDT', type: 'direct_symbol' },
    { value: 'ETH/USDT', label: 'ETH/USDT', type: 'direct_symbol' },
    { value: 'BNB/USDT', label: 'BNB/USDT', type: 'direct_symbol' },
    { value: 'SOL/USDT', label: 'SOL/USDT', type: 'direct_symbol' },
    { value: 'ADA/USDT', label: 'ADA/USDT', type: 'direct_symbol' },
    { value: 'DOT/USDT', label: 'DOT/USDT', type: 'direct_symbol' },
    { value: 'MATIC/USDT', label: 'MATIC/USDT', type: 'direct_symbol' },
    { value: 'LINK/USDT', label: 'LINK/USDT', type: 'direct_symbol' },
    { value: 'UNI/USDT', label: 'UNI/USDT', type: 'direct_symbol' },
    { value: 'LTC/USDT', label: 'LTC/USDT', type: 'direct_symbol' },
  ];

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
      setDefaultInterval('15m');
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

  // 组件挂载时加载策略列表、系统配置和品种选项
  useEffect(() => {
    loadStrategies();
    loadSystemConfig();
    fetchSymbolOptions();
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

  // 模拟回测进度（实际项目中应该通过WebSocket或轮询获取真实进度）
  const simulateBacktestProgress = async (symbols: string[]) => {
    // 阶段1：数据准备
    setCurrentStep(0);
    setStepStatus({ dataPrep: 'process', execution: 'wait', analysis: 'wait' });
    setProgressData({ overall: 5, dataPrep: { percent: 0 } });

    // 模拟数据完整性检查进度
    for (let i = 0; i <= 100; i += 20) {
      await new Promise(resolve => setTimeout(resolve, 200));
      setProgressData(prev => ({
        ...prev,
        overall: 5 + i * 0.15,
        dataPrep: { percent: i },
      }));
    }

    // 模拟发现数据缺失，开始下载
    setProgressData(prev => ({
      ...prev,
      dataPrep: { percent: 100, downloading: true, downloadProgress: 0 },
    }));

    // 模拟下载进度
    for (let i = 0; i <= 100; i += 10) {
      await new Promise(resolve => setTimeout(resolve, 300));
      setProgressData(prev => ({
        ...prev,
        overall: 20 + i * 0.15,
        dataPrep: { percent: 100, downloading: true, downloadProgress: i },
      }));
    }

    // 数据准备完成
    setStepStatus({ dataPrep: 'finish', execution: 'wait', analysis: 'wait' });

    // 阶段2：执行回测
    await new Promise(resolve => setTimeout(resolve, 500));
    setCurrentStep(1);
    setStepStatus({ dataPrep: 'finish', execution: 'process', analysis: 'wait' });

    // 模拟每个交易对的回测进度
    for (let i = 0; i < symbols.length; i++) {
      const symbol = symbols[i];
      for (let progress = 0; progress <= 100; progress += 25) {
        await new Promise(resolve => setTimeout(resolve, 200));
        setProgressData({
          overall: 35 + ((i * 100 + progress) / symbols.length) * 0.4,
          execution: {
            percent: progress,
            current: i + 1,
            total: symbols.length,
            currentSymbol: symbol,
          },
        });
      }
    }

    // 执行完成
    setStepStatus({ dataPrep: 'finish', execution: 'finish', analysis: 'wait' });

    // 阶段3：结果统计
    await new Promise(resolve => setTimeout(resolve, 500));
    setCurrentStep(2);
    setStepStatus({ dataPrep: 'finish', execution: 'finish', analysis: 'process' });

    // 模拟统计进度
    for (let i = 0; i <= 100; i += 25) {
      await new Promise(resolve => setTimeout(resolve, 200));
      setProgressData(prev => ({
        ...prev,
        overall: 75 + i * 0.25,
      }));
    }

    // 全部完成
    setStepStatus({ dataPrep: 'finish', execution: 'finish', analysis: 'finish' });
    setProgressData({ overall: 100 });
  };

  // 处理表单提交
  const handleSubmit = async (values: any) => {
    try {
      setLoading(true);
      setErrorMessage('');

      // 验证timeRange
      if (!values.timeRange || values.timeRange.length !== 2) {
        message.error('请选择有效的回测时间范围');
        return;
      }

      // 处理交易标的：检查是否选择了数据池
      let symbols: string[] = [];
      const selectedValues: string[] = values.symbols || [];
      const poolIds: number[] = [];

      // 分离数据池和普通货币对
      for (const value of selectedValues) {
        if (value.startsWith('pool_')) {
          // 提取数据池ID
          const poolId = parseInt(value.replace('pool_', ''));
          poolIds.push(poolId);
        } else {
          // 普通货币对
          symbols.push(value);
        }
      }

      // 如果有选择数据池，获取数据池中的所有货币对
      if (poolIds.length > 0) {
        message.loading('正在加载数据池中的货币对...', 0);
        for (const poolId of poolIds) {
          const poolAssets = await loadPoolSymbols(poolId);
          symbols = [...symbols, ...poolAssets];
        }
        message.destroy();

        // 去重
        symbols = [...new Set(symbols)];

        if (symbols.length === 0) {
          message.error('所选数据池中没有货币对，请选择其他数据池或货币对');
          setLoading(false);
          return;
        }

        message.success(`已加载 ${symbols.length} 个交易标的`);
      }

      // 验证是否有交易标的
      if (symbols.length === 0) {
        message.error('请至少选择一个交易标的或数据池');
        setLoading(false);
        return;
      }

      // 显示进度弹窗
      setProgressVisible(true);
      setCurrentStep(0);
      setStepStatus({ dataPrep: 'wait', execution: 'wait', analysis: 'wait' });
      setProgressData({ overall: 0 });

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
          symbols: symbols,
          start_time: startTime.format('YYYY-MM-DD HH:mm:ss'),
          end_time: endTime.format('YYYY-MM-DD HH:mm:ss'),
          interval: values.interval,
          commission: values.commission,
          initial_cash: values.initialCash,
        },
      };

      // 设置回测运行状态
      setIsBacktestRunning(true);

      // 生成任务ID
      const taskId = `bt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      setCurrentTaskId(taskId);

      // 创建 AbortController 用于取消请求
      abortControllerRef.current = new AbortController();

      // 启动模拟进度（实际项目中应该通过WebSocket或轮询获取真实进度）
      const progressPromise = simulateBacktestProgress(symbols);

      try {
        // 调用回测API，传入 signal 用于取消
        const backtestPromise = backtestApi.runBacktest(backtestData, abortControllerRef.current.signal);

        // 等待两者完成
        await Promise.all([progressPromise, backtestPromise]);

        message.success('回测已成功完成！');

        // 延迟关闭弹窗并返回列表
        setTimeout(() => {
          setProgressVisible(false);
          setIsBacktestRunning(false);
          setCurrentTaskId('');
          abortControllerRef.current = null;
          onRunBacktest();
        }, 1500);
      } catch (error: any) {
        // 检查是否是用户取消的请求
        if (error.name === 'AbortError' || error.message?.includes('aborted')) {
          console.log('回测已被用户终止');
          setErrorMessage('回测已终止');
          setStepStatus(prev => ({
            ...prev,
            execution: 'error',
            analysis: 'error',
          }));
          message.info('回测已终止');
        } else {
          console.error('执行回测失败:', error);
          setErrorMessage(error.message || '执行回测失败');

          // 设置错误状态
          setStepStatus(prev => {
            const newStatus = { ...prev };
            if (currentStep === 0) newStatus.dataPrep = 'error';
            else if (currentStep === 1) newStatus.execution = 'error';
            else newStatus.analysis = 'error';
            return newStatus;
          });

          message.error(error.message || '执行回测失败');
        }
        setIsBacktestRunning(false);
        setCurrentTaskId('');
        abortControllerRef.current = null;
      }
    } catch (error: any) {
      console.error('执行回测失败:', error);
      setErrorMessage(error.message || '执行回测失败');
      setIsBacktestRunning(false);
      setCurrentTaskId('');
      abortControllerRef.current = null;
      message.error(error.message || '执行回测失败');
    } finally {
      setLoading(false);
    }
  };

  // 终止回测
  const handleStopBacktest = async () => {
    try {
      // 使用 AbortController 取消请求
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        message.info('正在终止回测...');
      } else {
        // 如果没有 AbortController，直接重置状态
        setIsBacktestRunning(false);
        setCurrentTaskId('');
        setErrorMessage('回测已终止');
        setStepStatus(prev => ({
          ...prev,
          execution: 'error',
          analysis: 'error',
        }));
        message.info('回测已终止');
      }
    } catch (error: any) {
      console.error('终止回测失败:', error);
      message.error(error.message || '终止回测失败');
    }
  };

  // 查看回测进度
  const handleViewProgress = () => {
    setProgressVisible(true);
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
              interval: '15m',
              commission: 0.001,
              initialCash: 1000000,
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
                      mode="multiple"
                      placeholder="请选择或搜索品种"
                      style={{ width: '100%' }}
                      options={symbolOptions}
                      loading={symbolOptionsLoading}
                      showSearch
                      allowClear
                      maxTagCount={3}
                      maxTagPlaceholder={(omittedValues) => `+${omittedValues.length} 更多`}
                      filterOption={(input, option) => {
                        if (!input) return true;
                        const label = option?.label || '';
                        return label.toLowerCase().includes(input.toLowerCase());
                      }}
                    />
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
                {isBacktestRunning && !progressVisible && (
                  <Tooltip title="查看进行中的回测进度">
                    <Button
                      type="default"
                      icon={<EyeOutlined />}
                      onClick={handleViewProgress}
                    >
                      查看回测进度
                    </Button>
                  </Tooltip>
                )}
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

      {/* 回测进度弹窗 */}
      <BacktestProgressModal
        visible={progressVisible}
        onCancel={() => {
          setProgressVisible(false);
          // 如果回测已完成或出错，返回首页并刷新
          if (!isBacktestRunning) {
            onRunBacktest();
          }
        }}
        currentStep={currentStep}
        stepStatus={stepStatus}
        progressData={progressData}
        errorMessage={errorMessage}
        onStop={handleStopBacktest}
        isRunning={isBacktestRunning}
      />
    </div>
  );
};

export default BacktestConfig;