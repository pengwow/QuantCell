/**
 * 回测配置页面组件
 * 功能：配置策略回测参数，包括策略信息和回测信息
 */
import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';
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
import { PlusOutlined, UploadOutlined, InfoCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { backtestApi, configApi, strategyApi, dataApi } from '../../api';
import BacktestProgressModal from '../../components/BacktestProgressModal';
import type { StepStatusState, ProgressData } from '../../components/BacktestProgressModal';
import type { Strategy, StrategyParam, BacktestProgressData } from '../../types/backtest';
import { pollBacktestProgress } from '../../api/backtest';
import PageContainer from '@/components/PageContainer';

const { RangePicker } = DatePicker;
const { Option } = Select;
const { TabPane } = Tabs;
const { Dragger } = Upload;

interface BacktestConfigProps {
  onRunBacktest?: () => void;
  strategy?: Strategy;
}

const BacktestConfig: React.FC<BacktestConfigProps> = ({ onRunBacktest, strategy: propStrategy }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const [form] = Form.useForm();
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  // 从 location.state 获取策略信息（从策略管理页面传递过来）
  const locationStrategy = location.state?.strategy as Strategy | undefined;
  const showConfig = location.state?.showConfig as boolean | undefined;

  // 优先使用 location.state 中的策略，其次是 props 中的策略
  const strategy = locationStrategy || propStrategy;
  const [defaultInterval, setDefaultInterval] = useState<string>('15m');
  const [defaultCommission, setDefaultCommission] = useState<number>(0.001);
  const [defaultInitialCash, setDefaultInitialCash] = useState<number>(1000000);

  const [createModalVisible, setCreateModalVisible] = useState<boolean>(false);
  const [createForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState<string>('new');
  const [uploadFile, setUploadFile] = useState<File | null>(null);

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
  const [, setBacktestProgressData] = useState<BacktestProgressData | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [currentTaskId, setCurrentTaskId] = useState<string>('');
  const [isBacktestRunning, setIsBacktestRunning] = useState<boolean>(false);
  const abortControllerRef = React.useRef<AbortController | null>(null);
  const stopPollingRef = React.useRef<(() => void) | null>(null);

  const [symbolOptions, setSymbolOptions] = useState<Array<{ value: string; label: string; type: string; symbols?: string[] }>>([]);
  const [symbolOptionsLoading, setSymbolOptionsLoading] = useState(false);

  const fetchSymbolOptions = async () => {
    try {
      setSymbolOptionsLoading(true);

      const response = await dataApi.getCollectionSymbols({
        type: 'spot',
        exchange: 'binance'
      });

      const dataPoolOptions: Array<{ value: string; label: string; type: string; symbols?: string[] }> = [];
      const directSymbolOptions: Array<{ value: string; label: string; type: string; symbols?: string[] }> = [];

      if (response) {
        if (Array.isArray(response.data_pools)) {
          console.log('数据池数据:', response.data_pools);
          dataPoolOptions.push(...response.data_pools.map((pool: any) => ({
            value: `pool_${pool.id}`,
            label: `⭐ ${pool.name}`,
            type: 'data_pool',
            symbols: pool.symbols
          })));
        }

        if (Array.isArray(response.direct_symbols)) {
          directSymbolOptions.push(...response.direct_symbols.map((symbol: string) => ({
            value: symbol,
            label: symbol,
            type: 'direct_symbol'
          })));
        }
      }

      const mergedOptions = [...dataPoolOptions, ...directSymbolOptions];
      setSymbolOptions(mergedOptions);
    } catch (error) {
      console.error('获取品种选项失败:', error);
      setSymbolOptions(getDefaultSymbolOptions());
    } finally {
      setSymbolOptionsLoading(false);
    }
  };

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

  const loadSystemConfig = async () => {
    try {
      const configData = await configApi.getConfig();
      console.log('系统配置响应:', configData);

      if (configData && typeof configData === 'object') {
        // 处理按 name 分组的新格式
        // 格式: { "backtest": { "default_interval": "15m", ... }, ... }
        let configs: any = {};

        // 将分组配置扁平化
        Object.entries(configData).forEach(([, groupValues]) => {
          if (groupValues && typeof groupValues === 'object') {
            Object.entries(groupValues as Record<string, any>).forEach(([key, value]) => {
              configs[key] = value;
            });
          }
        });

        // 如果没有获取到配置，尝试兼容旧格式
        if (Object.keys(configs).length === 0 && configData.configs) {
          configs = configData.configs;
        }

        const intervalConfig = configs.default_interval || configs.DEFAULT_INTERVAL;
        if (intervalConfig) {
          const intervalValue = intervalConfig.value || intervalConfig;
          setDefaultInterval(intervalValue);
          console.log('成功加载默认时间间隔:', intervalValue);
        }

        const commissionConfig = configs.default_commission || configs.DEFAULT_COMMISSION;
        if (commissionConfig !== undefined) {
          const commissionValue = commissionConfig.value || commissionConfig;
          setDefaultCommission(Number(commissionValue));
          console.log('成功加载默认手续费:', commissionValue);
        }

        const initialCashConfig = configs.default_initial_cash || configs.DEFAULT_INITIAL_CASH;
        if (initialCashConfig !== undefined) {
          const initialCashValue = initialCashConfig.value || initialCashConfig;
          setDefaultInitialCash(Number(initialCashValue));
          console.log('成功加载默认初始资金:', initialCashValue);
        }
      }
    } catch (error) {
      console.error('加载系统配置失败:', error);
      setDefaultInterval('15m');
      setDefaultCommission(0.001);
      setDefaultInitialCash(1000000);
    }
  };

  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await backtestApi.getStrategies();
      console.log('策略列表响应:', response);

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
      setStrategies([]);
    } finally {
      setLoading(false);
    }
  };

  // 加载上次回测配置
  const loadLastBacktestConfig = () => {
    try {
      const lastConfig = localStorage.getItem('lastBacktestConfig');
      if (lastConfig) {
        const config = JSON.parse(lastConfig);
        console.log('[BacktestConfig] 加载上次回测配置:', config);
        
        // 填充交易标的
        if (config.symbols && config.symbols.length > 0) {
          form.setFieldsValue({
            symbols: config.symbols,
          });
          console.log('[BacktestConfig] 已自动填充交易标的:', config.symbols);
        }
        
        // 填充其他配置（如果存在）
        if (config.interval) {
          form.setFieldsValue({ interval: config.interval });
        }
        if (config.commission !== undefined) {
          form.setFieldsValue({ commission: config.commission });
        }
        if (config.initialCash !== undefined) {
          form.setFieldsValue({ initialCash: config.initialCash });
        }
        if (config.startTime && config.endTime) {
          form.setFieldsValue({
            timeRange: [dayjs(config.startTime), dayjs(config.endTime)],
          });
        }
      }
    } catch (error) {
      console.error('[BacktestConfig] 加载上次回测配置失败:', error);
    }
  };

  // 保存回测配置到 localStorage
  const saveBacktestConfig = (values: any, symbols: string[]) => {
    try {
      const config = {
        symbols: symbols,
        interval: values.interval,
        commission: values.commission,
        initialCash: values.initialCash,
        startTime: values.timeRange?.[0]?.format('YYYY-MM-DD HH:mm:ss'),
        endTime: values.timeRange?.[1]?.format('YYYY-MM-DD HH:mm:ss'),
        savedAt: new Date().toISOString(),
      };
      localStorage.setItem('lastBacktestConfig', JSON.stringify(config));
      console.log('[BacktestConfig] 已保存回测配置:', config);
    } catch (error) {
      console.error('[BacktestConfig] 保存回测配置失败:', error);
    }
  };

  useEffect(() => {
    loadStrategies();
    loadSystemConfig();
    fetchSymbolOptions();
    loadLastBacktestConfig();

    // 组件卸载时清理资源
    return () => {
      stopProgressPolling();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // 处理从策略管理页面传递过来的策略信息
  useEffect(() => {
    console.log('[BacktestConfig] location.state:', location.state);
    console.log('[BacktestConfig] locationStrategy:', locationStrategy);
    console.log('[BacktestConfig] propStrategy:', propStrategy);
    console.log('[BacktestConfig] 最终使用的 strategy:', strategy);
    console.log('[BacktestConfig] showConfig:', showConfig);

    if (strategy) {
      console.log('[BacktestConfig] 设置策略到表单:', strategy);
      setSelectedStrategy(strategy);

      const defaultParams: Record<string, any> = {};
      if (strategy.params) {
        strategy.params.forEach(p => {
          defaultParams[p.name] = p.default;
        });
      }

      form.setFieldsValue({
        strategy: strategy.name,
        params: defaultParams,
      });

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

      message.success(`已加载策略: ${strategy.name}`);
    }
  }, [strategy, form, location.state, locationStrategy, propStrategy, showConfig]);

  useEffect(() => {
    form.setFieldsValue({
      interval: defaultInterval,
      commission: defaultCommission,
      initialCash: defaultInitialCash
    });
  }, [defaultInterval, defaultCommission, defaultInitialCash, form]);

  const handleCreateStrategy = () => {
    setCreateModalVisible(true);
    createForm.resetFields();
    setActiveTab('new');
    setUploadFile(null);
  };

  const handleCreateModalClose = () => {
    setCreateModalVisible(false);
  };

  const handleCreateSubmit = async (values: any) => {
    try {
      setLoading(true);

      if (activeTab === 'new') {
        const strategyData = {
          name: values.strategyName,
          description: values.description,
          params: values.params ? JSON.parse(values.params) : {},
        };

        await strategyApi.createStrategy(strategyData);
        message.success('策略创建成功');
      } else if (activeTab === 'upload' && uploadFile) {
        const formData = new FormData();
        formData.append('file', uploadFile);
        formData.append('name', values.strategyName || uploadFile.name.replace('.py', ''));

        await backtestApi.uploadStrategy(formData);
        message.success('策略上传成功');
      }

      loadStrategies();
      setCreateModalVisible(false);
    } catch (error) {
      console.error('创建策略失败:', error);
      message.error('创建策略失败');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (file: File) => {
    setUploadFile(file);
    return false;
  };

  const handleStrategyChange = (value: string) => {
    const strategy = strategies.find(s => s.name === value);
    setSelectedStrategy(strategy || null);

    if (strategy && strategy.params) {
      const defaultParams: Record<string, any> = {};
      strategy.params.forEach(param => {
        defaultParams[param.name] = param.default;
      });
      form.setFieldValue('params', defaultParams);

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

  /**
   * 处理后端返回的进度数据，更新前端状态
   */
  const handleProgressUpdate = (data: BacktestProgressData) => {
    setBacktestProgressData(data);

    // 检查是否有错误（包括初始化阶段错误）
    if (data.error) {
      setErrorMessage(data.error.message);
      message.error(data.error.message);

      // 如果是初始化阶段错误，停止轮询并更新状态
      if (data.error.stage === 'initialization' || data.error.stage === 'polling') {
        stopProgressPolling();
        setIsBacktestRunning(false);
        setLoading(false);

        // 更新步骤状态为错误
        setStepStatus({
          dataPrep: 'error',
          execution: 'error',
          analysis: 'error',
        });
        return;
      }
    }

    // 检查任务状态
    if (data.status === 'failed') {
      stopProgressPolling();
      setIsBacktestRunning(false);
      setLoading(false);
      
      // 更新步骤状态为错误
      setStepStatus({
        dataPrep: data.data_prep?.status === 'failed' ? 'error' : 'finish',
        execution: data.execution?.status === 'failed' ? 'error' : 'finish',
        analysis: data.analysis?.status === 'failed' ? 'error' : 'finish',
      });
      
      // 显示错误消息
      if (data.error) {
        message.error(data.error.message);
      } else {
        message.error('回测执行失败');
      }
      
      return; // 立即返回，不再执行后续代码
    }
    
    // 检查任务是否完成
    if (data.status === 'completed') {
      stopProgressPolling();
      setIsBacktestRunning(false);
      setLoading(false);
      message.success('回测执行成功！');
      return; // 立即返回，不再执行后续代码
    }

    // 更新总体进度
    setProgressData({
      overall: data.overall_progress,
      dataPrep: data.data_prep ? {
        percent: data.data_prep.progress,
        downloading: data.data_prep.current_step === 'downloading' || !!data.data_prep.downloading,
        downloadProgress: data.data_prep.downloading?.progress || 0,
        message: data.data_prep.message,
      } : undefined,
      execution: data.execution ? {
        percent: data.execution.progress,
        current: data.execution.completed_symbols,
        total: data.execution.total_symbols,
        currentSymbol: data.execution.current_symbol,
        message: data.execution.message,
      } : undefined,
      analysis: data.analysis ? {
        percent: data.analysis.progress,
        message: data.analysis.message,
      } : undefined,
    });

    // 更新步骤状态
    const newStepStatus: StepStatusState = {
      dataPrep: 'wait',
      execution: 'wait',
      analysis: 'wait',
    };

    // 数据准备阶段状态
    if (data.data_prep) {
      if (data.data_prep.status === 'completed') {
        newStepStatus.dataPrep = 'finish';
      } else if (data.data_prep.status === 'running') {
        newStepStatus.dataPrep = 'process';
      } else if (data.data_prep.status === 'failed') {
        newStepStatus.dataPrep = 'error';
      }
    }

    // 执行阶段状态
    if (data.execution) {
      if (data.execution.status === 'completed') {
        newStepStatus.execution = 'finish';
      } else if (data.execution.status === 'running') {
        newStepStatus.execution = 'process';
      } else if (data.execution.status === 'failed') {
        newStepStatus.execution = 'error';
      }
    }

    // 结果统计阶段状态
    if (data.analysis) {
      if (data.analysis.status === 'completed') {
        newStepStatus.analysis = 'finish';
      } else if (data.analysis.status === 'running') {
        newStepStatus.analysis = 'process';
      } else if (data.analysis.status === 'failed') {
        newStepStatus.analysis = 'error';
      }
    }

    setStepStatus(newStepStatus);

    // 更新当前步骤
    if (data.current_stage === 'data_prep') {
      setCurrentStep(0);
    } else if (data.current_stage === 'execution') {
      setCurrentStep(1);
    } else if (data.current_stage === 'analysis' || data.current_stage === 'completed') {
      setCurrentStep(2);
    }
  };

  /**
   * 开始轮询获取回测进度
   */
  const startProgressPolling = (taskId: string) => {
    // 停止之前的轮询
    if (stopPollingRef.current) {
      stopPollingRef.current();
    }

    // 重置状态
    setCurrentStep(0);
    setStepStatus({ dataPrep: 'process', execution: 'wait', analysis: 'wait' });
    setProgressData({ overall: 0 });

    // 开始新的轮询
    stopPollingRef.current = pollBacktestProgress(taskId, handleProgressUpdate, {
      initialInterval: 500,
      maxInterval: 5000,
      maxRetries: 60,
      timeout: 300000
    });
  };

  /**
   * 停止轮询
   */
  const stopProgressPolling = () => {
    if (stopPollingRef.current) {
      stopPollingRef.current();
      stopPollingRef.current = null;
    }
  };

  const handleSubmit = async (values: any) => {
    try {
      setLoading(true);
      setErrorMessage('');

      if (!values.timeRange || values.timeRange.length !== 2) {
        message.error('请选择有效的回测时间范围');
        return;
      }

      let symbols: string[] = [];
      const selectedValues: string[] = values.symbols || [];
      const poolIds: number[] = [];

      for (const value of selectedValues) {
        if (value.startsWith('pool_')) {
          const poolId = parseInt(value.replace('pool_', ''));
          poolIds.push(poolId);
        } else {
          symbols.push(value);
        }
      }

      if (poolIds.length > 0) {
        message.loading('正在加载数据池中的货币对...', 0);
        for (const poolId of poolIds) {
          const poolAssets = await loadPoolSymbols(poolId);
          symbols = [...symbols, ...poolAssets];
        }
        message.destroy();

        symbols = [...new Set(symbols)];

        if (symbols.length === 0) {
          message.error('所选数据池中没有货币对，请选择其他数据池或货币对');
          setLoading(false);
          return;
        }

        message.success(`已加载 ${symbols.length} 个交易标的`);
      }

      if (symbols.length === 0) {
        message.error('请至少选择一个交易标的或数据池');
        setLoading(false);
        return;
      }

      // 保存回测配置到 localStorage
      saveBacktestConfig(values, symbols);

      setProgressVisible(true);
      setCurrentStep(0);
      setStepStatus({ dataPrep: 'wait', execution: 'wait', analysis: 'wait' });
      setProgressData({ overall: 0 });

      const [startTime, endTime] = values.timeRange;

      const strategyParams = values.params || {};

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

      setIsBacktestRunning(true);
      setErrorMessage('');

      abortControllerRef.current = new AbortController();

      // 添加启动超时机制（30秒）
      const startTimeout = setTimeout(() => {
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
          message.error('回测启动超时，请检查网络连接或代理配置');
          setErrorMessage('回测启动超时，请检查网络连接或代理配置');
          setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
          setIsBacktestRunning(false);
          setLoading(false);
        }
      }, 30000);

      try {
        // 先启动回测，获取 task_id
        const backtestResult = await backtestApi.runBacktest(backtestData, abortControllerRef.current.signal);

        // 清除启动超时
        clearTimeout(startTimeout);

        console.log('[BacktestConfig] 回测结果:', backtestResult);

        // 检查回测是否启动成功
        if (backtestResult?.status === 'failed') {
          const errorMsg = backtestResult.message || '回测启动失败';
          console.error('[BacktestConfig] 回测启动失败:', errorMsg);
          message.error(errorMsg);
          setErrorMessage(errorMsg);
          setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
          setIsBacktestRunning(false);
          setLoading(false);
          return;
        }

        // 从后端返回结果中获取 task_id
        const serverTaskId = backtestResult?.data?.task_id || backtestResult?.task_id;

        if (!serverTaskId) {
          console.error('[BacktestConfig] 后端未返回 task_id');
          message.error('回测启动失败：未获取到任务ID');
          setErrorMessage('回测启动失败：未获取到任务ID');
          setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
          setIsBacktestRunning(false);
          setLoading(false);
          return;
        }

        console.log('[BacktestConfig] 使用后端返回的 task_id:', serverTaskId);
        setCurrentTaskId(serverTaskId);

        // 立即显示进度弹窗
        setProgressVisible(true);

        // 延迟开始轮询，给后端一些初始化时间
        setTimeout(() => {
          startProgressPolling(serverTaskId);
        }, 500);

        // 注意：不再立即显示成功消息，而是等待轮询完成
        // message.success('回测任务已创建，正在执行中...');
      } catch (error: any) {
        // 清除启动超时
        clearTimeout(startTimeout);

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
          const errorMsg = error.message || '执行回测失败';
          setErrorMessage(errorMsg);

          setStepStatus(prev => {
            const newStatus = { ...prev };
            if (currentStep === 0) newStatus.dataPrep = 'error';
            else if (currentStep === 1) newStatus.execution = 'error';
            else newStatus.analysis = 'error';
            return newStatus;
          });

          message.error(errorMsg);
        }
        setIsBacktestRunning(false);
        setCurrentTaskId('');
        abortControllerRef.current = null;
        // 停止轮询
        stopProgressPolling();
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

  const handleStopBacktest = async () => {
    try {
      // 停止轮询
      stopProgressPolling();

      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        message.info('正在终止回测...');
      } else {
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

  const handleViewProgress = () => {
    setProgressVisible(true);
  };

  return (
    <PageContainer title={t('backtest_config')}>
      <div className="space-y-6">
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
          <Card title="策略信息" className="mb-6">
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
                  <div style={{ background: 'transparent', padding: '16px', borderRadius: '4px', border: '1px solid var(--ant-color-border)' }}>
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

          <Card title="回测信息" className="mb-6">
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
            </Space>
          </Form.Item>
        </Form>
      </Spin>

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

      <BacktestProgressModal
        visible={progressVisible}
        onCancel={() => {
          setProgressVisible(false);
          // 停止轮询
          stopProgressPolling();
          if (!isBacktestRunning) {
            onRunBacktest?.();
          }
        }}
        currentStep={currentStep}
        stepStatus={stepStatus}
        progressData={progressData}
        errorMessage={errorMessage}
        onStop={handleStopBacktest}
        isRunning={isBacktestRunning}
        taskId={currentTaskId}
        strategyName={selectedStrategy?.name}
      />
    </div>
    </PageContainer>
  );
};

export default BacktestConfig;
