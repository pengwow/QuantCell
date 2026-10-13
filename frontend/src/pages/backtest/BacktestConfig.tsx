import { QUANT_COLORS } from '@/utils/colors';
/**
 * 回测配置页面组件
 * 功能：配置策略回测参数，包括策略信息和回测信息
 */
import React, { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
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
  Upload,
  Tabs,
  Switch,
  Tooltip,
  App,
  Modal,
  Progress,
  Tag,
} from 'antd';
import { PlusOutlined, UploadOutlined, InfoCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { backtestApi, configApi, strategyApi } from '../../api';
import { dataApi } from '../../api/dataApi';
import { factorApi } from '../../api/factor';
import type { FactorDetail } from '../../api/factor';
import BacktestProgressModal from '../../components/BacktestProgressModal';
import type { StepStatusState, ProgressData } from '../../components/BacktestProgressModal';
import type { Strategy, StrategyParam, BacktestProgressData } from '../../types/backtest';
import { pollBacktestProgress } from '../../api/backtest';
import PageContainer from '@/components/PageContainer';
import { setPageTitle } from '@/utils/pageTitle';
import type { Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;
const { Option } = Select;
const { TabPane } = Tabs;
const { Dragger } = Upload;

interface BacktestConfigProps {
  onRunBacktest?: () => void;
  strategy?: Strategy;
}

// 系统配置项兼容 { value: x } 包装与直接标量两种返回形态，统一抽取标量值
const extractConfigScalar = (item: unknown): string | number | undefined => {
  if (typeof item === 'string' || typeof item === 'number') return item;
  if (item && typeof item === 'object' && 'value' in item) {
    const wrapped = (item as { value?: unknown }).value;
    if (typeof wrapped === 'string' || typeof wrapped === 'number') return wrapped;
  }
  return undefined;
};

// 创建策略弹窗表单值
interface CreateStrategyFormValues {
  strategyName: string;
  description?: string;
  params?: string;
}

// 回测主表单值
interface BacktestFormValues {
  strategy?: string;
  symbols?: string[];
  timeRange?: [Dayjs, Dayjs];
  interval?: string;
  factorNames?: string[];
  commission?: number;
  initialCash?: number;
  params?: Record<string, unknown>;
}

const BacktestConfig: React.FC<BacktestConfigProps> = ({ onRunBacktest, strategy: propStrategy }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const watchedStrategy = Form.useWatch('strategy', form);

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('backtest_config') || '回测配置');
  }, [t]);

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
  const [defaultInitialCash, setDefaultInitialCash] = useState<number>(1000);

  const [createModalVisible, setCreateModalVisible] = useState<boolean>(false);
  const [createForm] = Form.useForm();
  const [activeTab, setActiveTab] = useState<string>('new');
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [progressVisible, setProgressVisible] = useState<boolean>(false);
  // 回测前数据预检弹窗状态
  const [precheckVisible, setPrecheckVisible] = useState(false);
  const [precheckMissing, setPrecheckMissing] = useState<Array<{ symbol: string; timeframe: string; expected_path: string }>>([]);
  const [precheckDownloading, setPrecheckDownloading] = useState(false);
  const [precheckDownloadProgress, setPrecheckDownloadProgress] = useState(0);
  const [precheckDownloadMsg, setPrecheckDownloadMsg] = useState('');
  // 预检待执行的回测数据（下载完成后用它启动回测）
  const pendingBacktestDataRef = useRef<any>(null);
  const precheckAbortRef = useRef<AbortController | null>(null);
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
  const [factorOptions, setFactorOptions] = useState<FactorDetail[]>([]);

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
          dataPoolOptions.push(...response.data_pools.map((pool) => ({
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
        const pool = response.data_pools.find((p) => p.id === poolId);
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
        let configs: Record<string, unknown> = {};

        // 将分组配置扁平化
        Object.entries(configData).forEach(([, groupValues]) => {
          if (groupValues && typeof groupValues === 'object') {
            Object.entries(groupValues as Record<string, unknown>).forEach(([key, value]) => {
              configs[key] = value;
            });
          }
        });

        // 如果没有获取到配置，尝试兼容旧格式
        if (Object.keys(configs).length === 0) {
          const legacyConfigs = configData.configs;
          if (legacyConfigs && typeof legacyConfigs === 'object') {
            configs = legacyConfigs as Record<string, unknown>;
          }
        }

        const intervalConfig = configs['default_interval'] || configs['DEFAULT_INTERVAL'];
        if (intervalConfig !== undefined) {
          const intervalValue = extractConfigScalar(intervalConfig);
          if (intervalValue !== undefined) {
            setDefaultInterval(String(intervalValue));
            console.log('成功加载默认时间间隔:', intervalValue);
          }
        }

        const commissionConfig = configs['default_commission'] || configs['DEFAULT_COMMISSION'];
        if (commissionConfig !== undefined) {
          const commissionValue = extractConfigScalar(commissionConfig);
          if (commissionValue !== undefined) {
            setDefaultCommission(Number(commissionValue));
            console.log('成功加载默认手续费:', commissionValue);
          }
        }

        const initialCashConfig = configs['default_initial_cash'] || configs['DEFAULT_INITIAL_CASH'];
        if (initialCashConfig !== undefined) {
          const initialCashValue = extractConfigScalar(initialCashConfig);
          if (initialCashValue !== undefined) {
            setDefaultInitialCash(Number(initialCashValue));
            console.log('成功加载默认初始资金:', initialCashValue);
          }
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
        // API 返回的 StrategyInfo 字段较宽松，映射为页面需要的 Strategy 结构
        setStrategies(response.strategies.map((s) => ({
          name: s.name,
          file_name: s.file_name ?? s.name,
          file_path: s.file_path ?? '',
          description: s.description ?? '',
          version: s.version,
          tags: undefined,
          params: (s.params ?? []) as StrategyParam[],
          factors: (s.factors ?? []) as any,
          created_at: s.created_at ?? '',
          updated_at: s.updated_at ?? '',
        })));
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
  const saveBacktestConfig = (values: BacktestFormValues, symbols: string[]) => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 挂载时一次性初始化
  }, []);

  // 加载因子库中可计算的因子，供回测因子多选
  useEffect(() => {
    factorApi
      .listDetail()
      .then((r) => setFactorOptions(r.factors.filter((f) => f.supported)))
      .catch(() => setFactorOptions([]));
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
      // 从 strategies 列表取完整对象（含 factors），location/prop 传入的可能缺字段
      const fullStrategy = strategies.find(s => s.name === strategy.name) || strategy;
      setSelectedStrategy(fullStrategy);

      const defaultParams: Record<string, unknown> = {};
      if (fullStrategy.params) {
        fullStrategy.params.forEach(p => {
          defaultParams[p.name] = p.default;
        });
      }

      form.setFieldsValue({
        strategy: fullStrategy.name,
        params: defaultParams,
      });

      if (fullStrategy.tags && fullStrategy.tags.includes('demo')) {
        form.setFieldsValue({
          symbols: ['BTC/USDT'],
          timeRange: [dayjs('2024-01-01'), dayjs('2024-02-01')],
          interval: '15m',
          initialCash: 100000,
          commission: 0.001
        });
        message.info('已自动填充演示策略的回测配置');
      }

      message.success(`已加载策略: ${fullStrategy.name}`);
    }
  }, [strategy, form, location.state, locationStrategy, propStrategy, showConfig, message, strategies]);

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

  const handleCreateSubmit = async (values: CreateStrategyFormValues) => {
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

  // 根据策略 factors 与因子库交集，回填回测因子多选框
  const autoFillFactorNames = (strategy: Strategy | null) => {
    const factorNamesInLibrary = new Set(factorOptions.map(f => f.name));
    const matchedFactors = (strategy?.factors ?? [])
      .map(f => f.name)
      .filter(name => factorNamesInLibrary.has(name));
    form.setFieldValue('factorNames', matchedFactors);
  };

  // factorOptions 或 selectedStrategy 变化时，回填因子（覆盖预选与加载时序两种场景）
  useEffect(() => {
    if (selectedStrategy) {
      autoFillFactorNames(selectedStrategy);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [factorOptions, selectedStrategy]);

  const handleStrategyChange = (value: string) => {
    const strategy = strategies.find(s => s.name === value);
    setSelectedStrategy(strategy || null);

    if (strategy && strategy.params) {
      const defaultParams: Record<string, unknown> = {};
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

    autoFillFactorNames(strategy || null);
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
   * 重构版本：简化逻辑，确保状态正确更新
   */
  const handleProgressUpdate = (data: BacktestProgressData) => {
    console.log('[handleProgressUpdate] 收到进度数据:', JSON.stringify(data, null, 2));
    setBacktestProgressData(data);

    // 处理错误状态
    if (data.error && (data.error.stage === 'initialization' || data.error.stage === 'polling')) {
      setErrorMessage(data.error.message);
      message.error(data.error.message);
      stopProgressPolling();
      setIsBacktestRunning(false);
      setLoading(false);
      setStepStatus({ dataPrep: 'error', execution: 'error', analysis: 'error' });
      return;
    }

    // 根据后端状态计算前端状态
    const newStepStatus: StepStatusState = {
      dataPrep: mapStatus(data.data_prep?.status),
      execution: mapStatus(data.execution?.status),
      analysis: mapStatus(data.analysis?.status),
    };

    // 计算当前步骤
    let newCurrentStep = 0;
    if (data.current_stage === 'execution') {
      newCurrentStep = 1;
    } else if (data.current_stage === 'analysis' || data.current_stage === 'completed') {
      newCurrentStep = 2;
    }

    // 构建进度数据 - 确保所有字段都有默认值
    const newProgressData: ProgressData = {
      overall: data.overall_progress || 0,
      dataPrep: {
        percent: data.data_prep?.progress || 0,
        downloading: data.data_prep?.current_step === 'downloading' || !!data.data_prep?.downloading,
        downloadProgress: data.data_prep?.downloading?.progress || 0,
        message: data.data_prep?.message || getDefaultMessage(data.data_prep?.current_step, 'data_prep'),
      },
      execution: {
        percent: data.execution?.progress || 0,
        current: data.execution?.completed_symbols || 0,
        total: data.execution?.total_symbols || 1,
        currentSymbol: data.execution?.current_symbol || '',
        message: data.execution?.message || '准备执行回测...',
      },
      analysis: {
        percent: data.analysis?.progress || 0,
        message: data.analysis?.message || '等待结果统计...',
      },
    };

    // 更新所有状态
    setProgressData(newProgressData);
    setStepStatus(newStepStatus);
    setCurrentStep(newCurrentStep);

    console.log('[handleProgressUpdate] 更新后的状态:', {
      progressData: newProgressData,
      stepStatus: newStepStatus,
      currentStep: newCurrentStep,
    });

    // 处理完成状态
    if (data.status === 'completed') {
      stopProgressPolling();
      setIsBacktestRunning(false);
      setLoading(false);
      message.success('回测执行成功！');
      return;
    }

    // 处理失败状态
    if (data.status === 'failed') {
      stopProgressPolling();
      setIsBacktestRunning(false);
      setLoading(false);
      if (data.error) {
        setErrorMessage(data.error.message);
        message.error(data.error.message);
      } else {
        message.error('回测执行失败');
      }
      return;
    }
  };

  /**
   * 将后端状态映射为前端步骤状态
   */
  const mapStatus = (status?: string): StepStatusState['dataPrep'] => {
    switch (status) {
      case 'completed':
        return 'finish';
      case 'running':
        return 'process';
      case 'failed':
        return 'error';
      default:
        return 'wait';
    }
  };

  /**
   * 获取默认消息
   */
  const getDefaultMessage = (step?: string, stage?: string): string => {
    if (stage === 'data_prep') {
      switch (step) {
        case 'checking':
          return '正在检查数据完整性...';
        case 'downloading':
          return '正在下载数据...';
        case 'loading':
          return '正在加载数据...';
        default:
          return '准备数据...';
      }
    }
    return '处理中...';
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
    setProgressData({
      overall: 0,
      dataPrep: {
        percent: 0,
        downloading: false,
        downloadProgress: 0,
        message: '准备开始...',
      },
      execution: {
        percent: 0,
        current: 0,
        total: 1,
        currentSymbol: '',
        message: '等待数据准备...',
      },
      analysis: {
        percent: 0,
        message: '等待执行完成...',
      },
    });

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

  /** 执行回测（提交回测任务并轮询进度）。从 handleSubmit 提取，供预检后和下载后复用。 */
  const executeBacktest = async (backtestData: any) => {
    setIsBacktestRunning(true);
    setErrorMessage('');

    abortControllerRef.current = new AbortController();

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
      const backtestResult = await backtestApi.runBacktest(backtestData, abortControllerRef.current.signal);
      clearTimeout(startTimeout);

      if (backtestResult?.status === 'failed') {
        const errorMsg = backtestResult.message || '回测启动失败';
        message.error(errorMsg);
        setErrorMessage(errorMsg);
        setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
        setIsBacktestRunning(false);
        setLoading(false);
        return;
      }

      const serverTaskId = backtestResult?.data?.task_id || backtestResult?.task_id;
      if (!serverTaskId) {
        message.error('回测启动失败：未获取到任务ID');
        setErrorMessage('回测启动失败：未获取到任务ID');
        setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
        setIsBacktestRunning(false);
        setLoading(false);
        return;
      }

      setCurrentTaskId(serverTaskId);
      setProgressVisible(true);
      setTimeout(() => {
        startProgressPolling(serverTaskId);
      }, 500);
    } catch (error) {
      clearTimeout(startTimeout);
      if (error instanceof Error && (error.name === 'AbortError' || error.message?.includes('aborted'))) {
        setErrorMessage('回测已终止');
        setStepStatus(prev => ({ ...prev, execution: 'error', analysis: 'error' }));
        message.info('回测已终止');
      } else {
        const errorMsg = error instanceof Error ? error.message : '执行回测失败';
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
      stopProgressPolling();
    }
  };

  /** 预检弹窗：下载缺失数据，完成后自动回测（跳过下载失败的品种）。 */
  const handlePrecheckDownload = async () => {
    const pendingData = pendingBacktestDataRef.current;
    if (!pendingData) return;

    // 去重缺失品种和周期
    const missingSymbols = [...new Set(precheckMissing.map(m => m.symbol))];
    const missingTimeframes = [...new Set(precheckMissing.map(m => m.timeframe))];
    const cfg = pendingData.backtest_config;

    setPrecheckDownloading(true);
    setPrecheckDownloadProgress(0);
    setPrecheckDownloadMsg('正在创建下载任务...');
    precheckAbortRef.current = new AbortController();

    try {
      // 1. 创建下载任务
      const downloadRes: any = await dataApi.downloadCryptoData({
        symbols: missingSymbols,
        interval: missingTimeframes,
        start: cfg.start_time,
        end: cfg.end_time,
        candle_type: 'spot',
      });
      const taskId = downloadRes?.task_id || downloadRes?.data?.task_id;
      if (!taskId) {
        throw new Error('下载任务创建失败，未返回 task_id');
      }

      // 2. 轮询下载进度（每 2 秒，超时 10 分钟）
      setPrecheckDownloadMsg('下载中...');
      const maxWait = 10 * 60 * 1000;
      const startTime = Date.now();
      let failedSymbols: string[] = [];

      while (Date.now() - startTime < maxWait) {
        if (precheckAbortRef.current?.signal.aborted) break;
        await new Promise(r => setTimeout(r, 2000));

        const status: any = await dataApi.getTaskStatus(taskId);
        const info = status?.task_info || status;
        const st = info?.status;
        const progress = info?.progress || {};
        setPrecheckDownloadProgress(progress.percentage || 0);

        if (st === 'completed') {
          // 下载全部成功
          break;
        }
        if (st === 'failed') {
          // 部分或全部失败，从 params 取出原始 symbols 对比进度
          const params = info?.params || {};
          const allSymbols: string[] = params.symbols || missingSymbols;
          const completed = progress.completed || 0;
          const total = progress.total || allSymbols.length;
          // 简单策略：completed < total 时，认为未完成的为失败（后端未提供精确失败清单时）
          if (completed < total) {
            failedSymbols = allSymbols.slice(completed);
          }
          break;
        }
      }

      if (precheckAbortRef.current?.signal.aborted) {
        setPrecheckDownloadMsg('下载已取消');
        return;
      }

      // 3. 剔除下载失败的品种，启动回测
      const allSymbols: string[] = cfg.symbols || [];
      const remainingSymbols = failedSymbols.length > 0
        ? allSymbols.filter(s => !failedSymbols.includes(s))
        : allSymbols;

      setPrecheckVisible(false);
      setPrecheckDownloading(false);

      if (remainingSymbols.length === 0) {
        message.error('所有品种均无可用数据，请前往数据管理页下载');
        return;
      }

      if (failedSymbols.length > 0) {
        message.warning(`${failedSymbols.length} 个品种下载失败已跳过，将用剩余 ${remainingSymbols.length} 个品种回测`);
      } else {
        message.success('数据下载完成，开始回测');
      }

      const modifiedData = {
        ...pendingData,
        backtest_config: { ...cfg, symbols: remainingSymbols },
      };
      await executeBacktest(modifiedData);
    } catch (e: any) {
      setPrecheckDownloadMsg(`下载失败：${e?.message || '未知错误'}`);
      message.error(`数据下载失败：${e?.message || '未知错误'}`);
    } finally {
      setPrecheckDownloading(false);
    }
  };

  const handleSubmit = async (values: BacktestFormValues) => {
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

      const [startTime, endTime] = values.timeRange!;

      const strategyParams = values.params || {};

      // factor_timing 使用第一个所选因子作为信号因子
      if (values.strategy === 'factor_timing' && values.factorNames && values.factorNames.length > 0) {
        strategyParams.factor_name = values.factorNames[0];
      }

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
          factor_names: values.factorNames && values.factorNames.length > 0 ? values.factorNames : null,
        },
      };

      // 回测前数据预检：检查哪些品种缺少本地数据
      try {
        const precheck = await backtestApi.precheckData({
          symbols: symbols,
          timeframes: [values.interval || '15m'],
          candle_type: 'spot',
        });
        if (!precheck.all_available && precheck.missing.length > 0) {
          // 有缺失品种：弹窗提示，等待用户确认下载
          pendingBacktestDataRef.current = backtestData;
          setPrecheckMissing(precheck.missing);
          setPrecheckVisible(true);
          setLoading(false);
          return;
        }
      } catch (e) {
        // 预检失败不阻塞回测，降级走原有流程让引擎自行处理
        console.warn('[BacktestConfig] 数据预检失败，跳过:', e);
      }

      await executeBacktest(backtestData);
    } catch (error) {
      console.error('执行回测失败:', error);
      setErrorMessage(error instanceof Error ? error.message : '执行回测失败');
      setIsBacktestRunning(false);
      setCurrentTaskId('');
      abortControllerRef.current = null;
      message.error(error instanceof Error ? error.message : '执行回测失败');
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
    } catch (error) {
      console.error('终止回测失败:', error);
      message.error(error instanceof Error ? error.message : '终止回测失败');
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
                            color: QUANT_COLORS.info,
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

              <Col span={24}>
                <Form.Item
                  name="factorNames"
                  label={t('backtest_factors') || '回测因子'}
                  extra={
                    watchedStrategy === 'factor_timing'
                      ? t('backtest_factor_timing_hint') ||
                        'factor_timing 策略将使用第一个所选因子；不选则不注入因子'
                      : t('backtest_factor_optional_hint') || '不选则按无因子方式回测'
                  }
                >
                  <Select
                    mode="multiple"
                    allowClear
                    showSearch
                    optionFilterProp="label"
                    placeholder={t('backtest_factors_placeholder') || '选择因子库因子（可空）'}
                    options={factorOptions.map((f) => ({
                      value: f.name,
                      label: `${f.label} (${f.name})`,
                    }))}
                  />
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
                      } catch {
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

      {/* 回测前数据预检弹窗 */}
      <Modal
        title="数据缺失提醒"
        open={precheckVisible}
        onCancel={() => {
          if (precheckDownloading) {
            precheckAbortRef.current?.abort();
          }
          setPrecheckVisible(false);
          setPrecheckDownloading(false);
        }}
        footer={precheckDownloading ? null : [
          <Button key="cancel" onClick={() => setPrecheckVisible(false)}>取消</Button>,
          <Button
            key="download"
            type="primary"
            onClick={handlePrecheckDownload}
          >
            下载并回测
          </Button>,
        ]}
        width={560}
      >
        <Space direction="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
          <div>
            以下 <b>{precheckMissing.length}</b> 个品种×周期缺少本地数据，回测前需要下载：
          </div>
          <div style={{ maxHeight: 240, overflowY: 'auto', border: '1px solid #f0f0f0', borderRadius: 6, padding: 12 }}>
            <Space wrap size={[8, 8]}>
              {precheckMissing.map((m, i) => (
                <Tag key={`${m.symbol}-${m.timeframe}-${i}`} color="orange" style={{ fontFamily: 'monospace' }}>
                  {m.symbol} · {m.timeframe}
                </Tag>
              ))}
            </Space>
          </div>
          {precheckDownloading && (
            <>
              <Progress percent={precheckDownloadProgress} status="active" />
              <div style={{ color: '#666', fontSize: 13 }}>{precheckDownloadMsg}</div>
            </>
          )}
          <div style={{ color: '#999', fontSize: 12 }}>
            下载将覆盖回测所选时间范围。如自动下载失败，可
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/data-management')}>
              前往数据管理页手动处理
            </Button>
            。
          </div>
        </Space>
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
