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
  Segmented,
  Button,
  Space,
  Flex,
  Row,
  Col,
  Spin,
  Switch,
  Tooltip,
  App,
  Modal,
  Progress,
  Tag,
  theme,
} from 'antd';
import { PlusOutlined, InfoCircleOutlined, EyeOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { backtestApi, configApi } from '../../api';
import { dataApi } from '../../api/dataApi';
import { factorApi } from '../../api/factor';
import type { FactorDetail } from '../../api/factor';
import BacktestProgressModal from '../../components/BacktestProgressModal';
import type { StepStatusState, ProgressData } from '../../components/BacktestProgressModal';
import type { Strategy, StrategyParam, BacktestProgressData } from '../../types/backtest';
import { pollBacktestProgress } from '../../api/backtest';
import PageContainer from '@/components/PageContainer';
import { usePageBack } from '@/hooks/usePageBack';
import { setPageTitle } from '@/utils/pageTitle';
import SymbolSelect from '@/components/SymbolSelect';
import SymbolParamOverrides from '../../components/strategyParams/SymbolParamOverrides';
import {
  buildMarginSpecsPayload,
  pickDirectSymbols,
  type MarginSpecRow,
} from './marginSpecs';
import { formatCashGrouped, formatFeePercent } from './bcFormat';
import type { Dayjs } from 'dayjs';
// 页面级样式（.bc-grid / .bc-form 等）：全局原语在 global.css 的 .qc-*，此处只补页面缺口
import './backtest.css';

const { RangePicker } = DatePicker;
const { Option } = Select;

// K 线周期档位：与原 Select 完全同集（真实能力不减），demo .seg 形制为 mono 裸值
const INTERVAL_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'].map((v) => ({ value: v, label: v }));

// demo 2276「预计运行 N bar」估算用：bar 间隔 → 毫秒（与 INTERVAL_OPTIONS 同全集）
const INTERVAL_MS: Record<string, number> = {
  '1m': 60_000,
  '5m': 300_000,
  '15m': 900_000,
  '30m': 1_800_000,
  '1h': 3_600_000,
  '4h': 14_400_000,
  '1d': 86_400_000,
};

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
  tradingMode?: string;
  capitalMode?: 'per_symbol' | 'shared';
  // 按标的参数覆盖（提交进 strategy_config.strategy_params_by_symbol；同时进 localStorage 供恢复）
  params_by_symbol?: Record<string, Record<string, unknown>>;
  // 以品种为键存行值：用下标对齐品种在增删时会串写到别的行，symbol 作 key 从根上避免
  margin_specs?: Record<string, MarginSpecRow>;
}

const BacktestConfig: React.FC<BacktestConfigProps> = ({ onRunBacktest, strategy: propStrategy }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  // 统一返回逻辑：returnUrl 优先（保留列表筛选状态），否则历史返回
  const handleBack = usePageBack();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const watchedStrategy = Form.useWatch('strategy', form);
  // 主题 token：策略下拉的描述文字取 token 颜色，保证亮暗主题下都协调
  const { token } = theme.useToken();
  // symbols 可在表单中动态增删，这里按实时值判断是否多品种回测，决定「资金使用方式」是否可用
  const watchedSymbols = Form.useWatch('symbols', form);
  const isMultiSymbol = (watchedSymbols?.length ?? 0) > 1;
  // 保证金区块只在永续合约下出现（币本位由后端拦截，前端没有 market 选择器）
  const watchedTradingMode = Form.useWatch('tradingMode', form);
  // 行渲染只依赖已注册的 symbols：若反过来依赖 margin_specs 的 watch 值，
  // 字段又要先渲染才注册，两者互锁会导致整个区块永远不渲染
  const specSymbols = pickDirectSymbols(watchedSymbols);
  // 页头副标取表单实时值（真实口径）：初始资金/手续费随表单联动，runner 取后端默认 kernel
  const watchedCommission = Form.useWatch('commission', form);
  const watchedInitialCash = Form.useWatch('initialCash', form);
  // 资金使用方式（.qc-seg 形制）：value 沿用后端契约 per_symbol/shared，文案沿用既有词条
  const capitalOptions = [
    { value: 'per_symbol', label: t('backtest_capital_per_symbol') },
    { value: 'shared', label: t('backtest_capital_shared') },
  ];

  // 设置页面标题
  useEffect(() => {
    setPageTitle(t('backtest_config'));
  }, [t]);

  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  // 按标的参数覆盖（spec 2026-11-28）：{symbol: {param: value}}，提交进 strategy_config.strategy_params_by_symbol
  const [paramsBySymbol, setParamsBySymbol] = useState<Record<string, Record<string, unknown>>>({});

  // LLM 类型判定：与后端 _strategy_kind 同口径（策略 params 里 name=mode 的取值 llm，
  // 见 backend/strategy/service.py:353）。表单值优先（用户可覆盖 mode），未改过时回落到档案默认值
  const watchedParams = Form.useWatch('params', form) as Record<string, unknown> | undefined;
  const watchedTimeRange = Form.useWatch('timeRange', form) as [Dayjs, Dayjs] | undefined;
  const watchedInterval = Form.useWatch('interval', form) as string | undefined;
  const modeParamDefault = selectedStrategy?.params?.find((p) => p.name === 'mode')?.default;
  // demo 2276/2735「预计运行 N bar」：起止 × bar 间隔纯算术估算（未计缺 bar / 停机段，故 UI 标「估算」）
  const estimatedBars =
    watchedTimeRange?.[0] && watchedTimeRange[1] && INTERVAL_MS[watchedInterval ?? '15m']
      ? Math.max(
          0,
          Math.floor(
            watchedTimeRange[1].diff(watchedTimeRange[0]) / INTERVAL_MS[watchedInterval ?? '15m'],
          ),
        )
      : null;
  const isLlmStrategy = watchedParams?.mode !== undefined
    ? watchedParams.mode === 'llm'
    : modeParamDefault === 'llm';

  // 从 location.state 获取策略信息（从策略管理页面传递过来）
  const locationStrategy = location.state?.strategy as Strategy | undefined;
  const showConfig = location.state?.showConfig as boolean | undefined;

  // 优先使用 location.state 中的策略，其次是 props 中的策略
  const strategy = locationStrategy || propStrategy;
  const [defaultInterval, setDefaultInterval] = useState<string>('15m');
  const [defaultCommission, setDefaultCommission] = useState<number>(0.001);
  const [defaultInitialCash, setDefaultInitialCash] = useState<number>(1000);

  const [progressVisible, setProgressVisible] = useState<boolean>(false);
  // 回测前数据预检弹窗状态
  const [precheckVisible, setPrecheckVisible] = useState(false);
  const [precheckMissing, setPrecheckMissing] = useState<Array<{ symbol: string; interval: string; expected_path: string }>>([]);
  const [precheckDownloading, setPrecheckDownloading] = useState(false);
  const [precheckDownloadProgress, setPrecheckDownloadProgress] = useState(0);
  const [precheckDownloadMsg, setPrecheckDownloadMsg] = useState('');
  // 逐品种下载进度: { symbol, interval, percentage, status }
  const [precheckSymbolsProgress, setPrecheckSymbolsProgress] = useState<
    { symbol: string; interval: string; percentage: number; status: string }[]
  >([]);
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

  const [factorOptions, setFactorOptions] = useState<FactorDetail[]>([]);

  const loadSystemConfig = async () => {
    try {
      const configData = await configApi.getConfig();
      console.log('System config response:', configData);

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
            console.log('Default interval loaded:', intervalValue);
          }
        }

        const commissionConfig = configs['default_commission'] || configs['DEFAULT_COMMISSION'];
        if (commissionConfig !== undefined) {
          const commissionValue = extractConfigScalar(commissionConfig);
          if (commissionValue !== undefined) {
            setDefaultCommission(Number(commissionValue));
            console.log('Default commission loaded:', commissionValue);
          }
        }

        const initialCashConfig = configs['default_initial_cash'] || configs['DEFAULT_INITIAL_CASH'];
        if (initialCashConfig !== undefined) {
          const initialCashValue = extractConfigScalar(initialCashConfig);
          if (initialCashValue !== undefined) {
            setDefaultInitialCash(Number(initialCashValue));
            console.log('Default initial cash loaded:', initialCashValue);
          }
        }
      }
    } catch (error) {
      console.error('Failed to load system config:', error);
      setDefaultInterval('15m');
      setDefaultCommission(0.001);
      setDefaultInitialCash(1000000);
    }
  };

  const loadStrategies = async () => {
    try {
      setLoading(true);
      const response = await backtestApi.getStrategies();
      console.log('Strategy list response:', response);

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
        console.log('Strategy list loaded:', response.strategies);
      } else {
        setStrategies([]);
        console.error('Invalid strategy list data:', response);
        message.warning(t('backtest_strategy_list_invalid'));
      }
    } catch (error) {
      console.error('Failed to load strategy list:', error);
      message.error(t('backtest_strategy_list_load_failed'));
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
        console.log('[BacktestConfig] Last saved config loaded:', config);
        
        // 填充交易标的
        if (config.symbols && config.symbols.length > 0) {
          form.setFieldsValue({
            symbols: config.symbols,
          });
          console.log('[BacktestConfig] Symbols auto-filled:', config.symbols);
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
        if (config.tradingMode) {
          form.setFieldsValue({ tradingMode: config.tradingMode });
        }
        if (config.capitalMode !== undefined) {
          form.setFieldsValue({ capitalMode: config.capitalMode });
        }
        if (config.startTime && config.endTime) {
          form.setFieldsValue({
            timeRange: [dayjs(config.startTime), dayjs(config.endTime)],
          });
        }
        // 按标的覆盖恢复（上次保存的口径；策略未选时 state 先存着，选完策略后覆盖入口即用）
        if (config.paramsBySymbol && typeof config.paramsBySymbol === 'object') {
          setParamsBySymbol(config.paramsBySymbol);
        }
      }
    } catch (error) {
      console.error('[BacktestConfig] Failed to load last backtest config:', error);
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
        tradingMode: values.tradingMode || 'spot',
        capitalMode: values.capitalMode,
        startTime: values.timeRange?.[0]?.format('YYYY-MM-DD HH:mm:ss'),
        endTime: values.timeRange?.[1]?.format('YYYY-MM-DD HH:mm:ss'),
        paramsBySymbol: values.params_by_symbol,
        savedAt: new Date().toISOString(),
      };
      localStorage.setItem('lastBacktestConfig', JSON.stringify(config));
      console.log('[BacktestConfig] Backtest config saved:', config);
    } catch (error) {
      console.error('[BacktestConfig] Failed to save backtest config:', error);
    }
  };

  useEffect(() => {
    loadStrategies();
    loadSystemConfig();
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
    console.log('[BacktestConfig] Final strategy:', strategy);
    console.log('[BacktestConfig] showConfig:', showConfig);

    if (strategy) {
      console.log('[BacktestConfig] Strategy set to form:', strategy);
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
        message.info(t('backtest_demo_config_filled'));
      }

      message.success(t('backtest_strategy_loaded', { name: fullStrategy.name }));
    }
  }, [strategy, form, location.state, locationStrategy, propStrategy, showConfig, message, strategies]);

  useEffect(() => {
    form.setFieldsValue({
      interval: defaultInterval,
      commission: defaultCommission,
      initialCash: defaultInitialCash
    });
  }, [defaultInterval, defaultCommission, defaultInitialCash, form]);

  // 创建/上传策略统一走策略编辑器页面：无路由参数进入时会自动打开创建流程（模板+类型选择），
  // 编辑器带完整代码窗口与 AI 助手，比本页旧的表单弹窗能力更全
  const handleCreateStrategy = () => {
    navigate('/strategy-editor');
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
        message.info(t('backtest_demo_config_filled'));
      }
    } else {
      form.setFieldValue('params', {});
    }

    autoFillFactorNames(strategy || null);
  };

  const renderParamInput = (param: StrategyParam) => {
    const type = param.type ? param.type.toLowerCase() : 'string';

    // 后端覆写的 select 类型（direction 等）优先渲染下拉
    if (type === 'select' || (param.options && param.options.length > 0)) {
      return (
        <Select style={{ width: '100%' }}>
          {(param.options || []).map((opt) => (
            <Select.Option key={opt} value={opt}>
              {opt}
            </Select.Option>
          ))}
        </Select>
      );
    }
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
    console.log('[handleProgressUpdate] Progress data received:', JSON.stringify(data, null, 2));
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

    // 处理终止状态：后端已把任务/进度置为 stopped（用户终止后的终态信号），
    // 必须在任何 running 态写入之前收尾，否则运行态会覆盖已设的终止界面
    if (data.status === 'stopped') {
      // 收到后端终止终态：停轮询、关闭弹窗即可（终止成功/强制终止的反馈
      // 已由 stop 请求的 toast 展示），不在步骤条里摆终止态
      stopProgressPolling();
      setProgressVisible(false);
      setIsBacktestRunning(false);
      setLoading(false);
      setCurrentTaskId('');
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
        message: data.execution?.message || t('backtest_preparing_execution'),
      },
      analysis: {
        percent: data.analysis?.progress || 0,
        message: data.analysis?.message || t('backtest_waiting_stats'),
      },
    };

    // 更新所有状态
    setProgressData(newProgressData);
    setStepStatus(newStepStatus);
    setCurrentStep(newCurrentStep);

    console.log('[handleProgressUpdate] Updated state:', {
      progressData: newProgressData,
      stepStatus: newStepStatus,
      currentStep: newCurrentStep,
    });

    // 处理完成状态
    if (data.status === 'completed') {
      stopProgressPolling();
      setIsBacktestRunning(false);
      setLoading(false);
      message.success(t('backtest_success_complete'));
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
        message.error(t('backtest_execute_failed'));
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
          return t('backtest_step_checking_data');
        case 'downloading':
          return t('backtest_step_downloading_data');
        case 'loading':
          return t('backtest_step_loading_data');
        default:
          return t('backtest_step_preparing_data');
      }
    }
    return t('backtest_step_processing');
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
        message: t('backtest_step_ready_to_start'),
      },
      execution: {
        percent: 0,
        current: 0,
        total: 1,
        currentSymbol: '',
        message: t('backtest_step_waiting_data'),
      },
      analysis: {
        percent: 0,
        message: t('backtest_step_waiting_execution'),
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
        message.error(t('backtest_start_timeout'));
        setErrorMessage(t('backtest_start_timeout'));
        setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
        setIsBacktestRunning(false);
        setLoading(false);
      }
    }, 30000);

    try {
      const backtestResult = await backtestApi.runBacktest(backtestData, abortControllerRef.current.signal);
      clearTimeout(startTimeout);

      if (backtestResult?.status === 'failed') {
        const errorMsg = backtestResult.message || t('backtest_start_failed_generic');
        message.error(errorMsg);
        setErrorMessage(errorMsg);
        setStepStatus(prev => ({ ...prev, dataPrep: 'error' }));
        setIsBacktestRunning(false);
        setLoading(false);
        return;
      }

      const serverTaskId = backtestResult?.data?.task_id || backtestResult?.task_id;
      if (!serverTaskId) {
        message.error(t('backtest_no_task_id'));
        setErrorMessage(t('backtest_no_task_id'));
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
        // 前端本地中止（后端任务若已创建会自然跑完结束）：关弹窗复位即可，不摆终止态
        setProgressVisible(false);
        setIsBacktestRunning(false);
        message.info(t('backtest_terminated'));
      } else {
        const errorMsg = error instanceof Error ? error.message : t('backtest_exec_failed_generic');
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
    const missingIntervals = [...new Set(precheckMissing.map(m => m.interval))];
    const cfg = pendingData.backtest_config;

    setPrecheckDownloading(true);
    setPrecheckDownloadProgress(0);
    setPrecheckDownloadMsg(t('backtest_download_creating_task'));
    setPrecheckSymbolsProgress([]);
    precheckAbortRef.current = new AbortController();

    try {
      // 1. 创建下载任务
      const downloadRes: any = await dataApi.downloadCryptoData({
        symbols: missingSymbols,
        interval: missingIntervals,
        start: cfg.start_time,
        end: cfg.end_time,
        candle_type: cfg.trading_mode === 'futures' ? 'future' : 'spot',
      });
      const taskId = downloadRes?.task_id || downloadRes?.data?.task_id;
      if (!taskId) {
        throw new Error(t('backtest_download_task_no_id'));
      }

      // 2. 轮询下载进度（每 2 秒，超时 10 分钟）
      setPrecheckDownloadMsg(t('backtest_downloading'));
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

        // 逐品种进度: 后端 symbols_progress 是 { task_key: {symbol, interval, percentage, status} }
        const symbolsProgressRaw = info?.symbols_progress || {};
        const symList = Object.values(symbolsProgressRaw).map((p: any) => ({
          symbol: p.symbol,
          interval: p.interval,
          percentage: Number(p.percentage || 0),
          status: p.status || 'running',
        }));
        setPrecheckSymbolsProgress(symList);

        // 总体进度 = 已完成品种数 / 总品种数,避免单品种 percentage 反复 0→100 造成进度条跳变
        const totalSyms = symList.length || missingSymbols.length;
        const doneSyms = symList.filter(p => p.status === 'completed').length;
        const overallPct = totalSyms > 0 ? Math.round((doneSyms / totalSyms) * 100) : (progress.percentage || 0);
        setPrecheckDownloadProgress(overallPct);

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
        setPrecheckDownloadMsg(t('backtest_download_cancelled'));
        return;
      }

      // 3. 剔除下载失败的品种，启动回测
      const allSymbols: string[] = cfg.symbols || [];
      const remainingSymbols = failedSymbols.length > 0
        ? allSymbols.filter(s => !failedSymbols.includes(s))
        : allSymbols;

      setPrecheckVisible(false);
      setPrecheckDownloading(false);
      // 预检阶段已关闭进度弹窗，这里重新打开以展示回测进度
      setProgressVisible(true);

      if (remainingSymbols.length === 0) {
        message.error(t('backtest_no_data_at_all'));
        setProgressVisible(false);
        return;
      }

      if (failedSymbols.length > 0) {
        message.warning(t('backtest_download_skipped_some', { failed: failedSymbols.length, remaining: remainingSymbols.length }));
      } else {
        message.success(t('backtest_download_done_start'));
      }

      const modifiedData = {
        ...pendingData,
        backtest_config: { ...cfg, symbols: remainingSymbols },
      };
      await executeBacktest(modifiedData);
    } catch (e: any) {
      setPrecheckDownloadMsg(t('backtest_download_failed_detail', { message: e?.message || t('backtest_unknown_error') }));
      message.error(t('backtest_download_failed_msg', { message: e?.message || t('backtest_unknown_error') }));
    } finally {
      setPrecheckDownloading(false);
    }
  };

  const handleSubmit = async (values: BacktestFormValues) => {
    try {
      setLoading(true);
      setErrorMessage('');
      // 重置上次预检残留状态，避免弹窗被盖住或脏数据干扰
      setPrecheckVisible(false);
      setPrecheckDownloading(false);
      setPrecheckMissing([]);
      pendingBacktestDataRef.current = null;

      if (!values.timeRange || values.timeRange.length !== 2) {
        message.error(t('backtest_invalid_time_range'));
        return;
      }

      // 自选组已由 SymbolSelect 在选择时展开成组内标的（不再提交 pool_ 值）
      const symbols: string[] = values.symbols || [];

      if (symbols.length === 0) {
        message.error(t('backtest_symbols_required_msg'));
        setLoading(false);
        return;
      }

      // 按标的覆盖：逐标的过滤空值、剔除空覆盖标的（留空=继承，与创建弹窗 cleanStrategyParams 口径一致）
      const cleanedBySymbol = Object.fromEntries(
        Object.entries(paramsBySymbol)
          .map(([sym, raw]) => [
            sym,
            Object.fromEntries(Object.entries(raw).filter(([, v]) => v !== '' && v !== null && v !== undefined)),
          ] as const)
          .filter(([, ov]) => Object.keys(ov as Record<string, unknown>).length > 0),
      );

      // 保存回测配置到 localStorage（含按标的覆盖，供下次打开恢复）
      values.params_by_symbol = cleanedBySymbol;
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
          strategy_params_by_symbol: cleanedBySymbol,
        },
        backtest_config: {
          symbols: symbols,
          start_time: startTime.format('YYYY-MM-DD HH:mm:ss'),
          end_time: endTime.format('YYYY-MM-DD HH:mm:ss'),
          interval: values.interval,
          commission: values.commission,
          initial_cash: values.initialCash,
          factor_names: values.factorNames && values.factorNames.length > 0 ? values.factorNames : null,
          trading_mode: values.tradingMode || 'spot',
          capital_mode: values.capitalMode || 'per_symbol',
          // 只有永续合约允许杠杆配置；按本次实际提交的品种过滤，残留键自然丢弃
          margin_specs:
            values.tradingMode === 'futures'
              ? buildMarginSpecsPayload(values.margin_specs, symbols)
              : [],
        },
      };

      // 回测前数据预检：检查哪些品种缺少本地数据
      // candle_type 跟随交易模式: 现货 spot / 永续合约 future
      const candleType = values.tradingMode === 'futures' ? 'future' : 'spot';
      try {
        const precheck = await backtestApi.precheckData({
          symbols: symbols,
          intervals: [values.interval || '15m'],
          candle_type: candleType,
        });
        if (!precheck.all_available && precheck.missing.length > 0) {
          // 回测尚未启动，关闭进度弹窗，避免盖住下方的"数据缺失提醒"弹窗
          setProgressVisible(false);
          // 有缺失品种：弹窗提示，等待用户确认下载
          pendingBacktestDataRef.current = backtestData;
          setPrecheckMissing(precheck.missing);
          setPrecheckVisible(true);
          setLoading(false);
          return;
        }
      } catch (e) {
        // 预检失败不阻塞回测，降级走原有流程让引擎自行处理
        console.warn('[BacktestConfig] Data precheck failed, skipping:', e);
      }

      await executeBacktest(backtestData);
    } catch (error) {
      console.error('Failed to run backtest:', error);
      setErrorMessage(error instanceof Error ? error.message : t('backtest_exec_failed_generic'));
      setIsBacktestRunning(false);
      setCurrentTaskId('');
      abortControllerRef.current = null;
      message.error(error instanceof Error ? error.message : t('backtest_exec_failed_generic'));
    } finally {
      setLoading(false);
    }
  };

  const handleStopBacktest = async () => {
    // 停止轮询
    stopProgressPolling();

    // 已拿到后端任务 ID：真正调用终止接口，等待后端反馈（后端限时等待执行线程退出确认）
    if (currentTaskId) {
      // 复用同一 message key，让 loading → 结果提示原地替换，无残影
      const stopKey = 'backtest-stop';
      message.loading({ content: t('backtest_stopping'), key: stopKey, duration: 0 });
      try {
        const res = await backtestApi.stopBacktest(currentTaskId);
        const data = res?.data;
        if (res?.code !== 0) {
          // 后端拒绝终止（任务不存在/已不在运行）：恢复轮询让进度走到终态
          message.error({ content: res?.message || t('backtest_stop_failed'), key: stopKey, duration: 3 });
          startProgressPolling(currentTaskId);
          return;
        }
        // 后端反馈直接展示给用户；forced = 确认超时已强制标记终止，用警告级提示
        if (data?.status === 'forced') {
          message.warning({ content: data?.message || t('backtest_terminated'), key: stopKey, duration: 5 });
        } else {
          message.success({ content: data?.message || t('backtest_terminated'), key: stopKey, duration: 3 });
        }
      } catch (error) {
        console.error('Failed to stop backtest:', error);
        message.error({
          content: error instanceof Error ? error.message : t('backtest_stop_failed'),
          key: stopKey,
          duration: 3,
        });
        startProgressPolling(currentTaskId);
        return;
      }
    } else {
      // /run 请求尚未返回任务 ID（有的话先中断前端请求）：后端任务完成后自然落库结束
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      message.info(t('backtest_terminated'));
    }

    // 终止已受理：成功/强制终止的反馈已 toast，直接关闭进度弹窗并复位运行态
    abortControllerRef.current = null;
    setProgressVisible(false);
    setIsBacktestRunning(false);
    setCurrentTaskId('');
  };

  const handleViewProgress = () => {
    setProgressVisible(true);
  };

  return (
    <PageContainer
      title={t('backtest_config')}
      onBack={handleBack}
      subtitle={t('bc_subtitle', {
        cash: formatCashGrouped(watchedInitialCash ?? 1000000),
        fee: formatFeePercent(watchedCommission ?? 0.001),
      })}
      actions={
        <>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={handleBack}
            style={{ height: 30, padding: '0 12px', fontSize: 12 }}
          >
            {t('back')}
          </Button>
          {isBacktestRunning && !progressVisible && (
            <Tooltip title={t('backtest_view_progress_tooltip')}>
              <Button
                icon={<EyeOutlined />}
                onClick={handleViewProgress}
                style={{ height: 30, padding: '0 12px', fontSize: 12 }}
              >
                {t('backtest_view_progress')}
              </Button>
            </Tooltip>
          )}
          {/* 提交入口移到页头（demo page-actions）：form.submit() 与 htmlType="submit" 同一校验链路 */}
          <Button
            type="primary"
            loading={loading}
            disabled={isBacktestRunning}
            onClick={() => form.submit()}
            style={{ height: 30, padding: '0 12px', fontSize: 12, fontWeight: 550 }}
          >
            {t('backtest_run')}
          </Button>
        </>
      }
    >
      <Spin spinning={loading}>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          className="bc-form"
          initialValues={{
            interval: '15m',
            commission: 0.001,
            initialCash: 1000000,
            timeRange: [dayjs().subtract(30, 'day'), dayjs()],
            tradingMode: 'spot',
          }}
        >
          <div className="bc-grid">
            {/* 卡 1 · 回测范围 */}
            <Card title={t('backtest_scope')} className="qc-card bc-card">
              <Form.Item
                name="strategy"
                label={t('backtest_strategy_name')}
                rules={[{ required: true, message: t('backtest_strategy_name_required') }]}
              >
                <Select
                  placeholder={t('backtest_strategy_placeholder')}
                  style={{ width: '100%' }}
                  onChange={handleStrategyChange}
                  // options + optionRender：选中回显只用 label（纯策略名），下拉项额外渲染描述
                  options={strategies.map((s) => ({ value: s.name, label: s.name, strategy: s }))}
                  // 下拉底部常驻创建入口：找不到目标策略时就地创建，无需在页面上独占一行
                  popupRender={(menu) => (
                    <>
                      {menu}
                      <div style={{ padding: 4, borderTop: `1px solid ${token.colorBorderSecondary}` }}>
                        <Button
                          type="text"
                          block
                          icon={<PlusOutlined />}
                          // mousedown 不 preventDefault 会让 Select 收起、click 丢失（antd 官方要求）
                          onMouseDown={(e) => e.preventDefault()}
                          onClick={handleCreateStrategy}
                        >
                          {t('backtest_create_strategy')}
                        </Button>
                      </div>
                    </>
                  )}
                  optionRender={(option) => {
                    const s = option.data.strategy as Strategy;
                    return (
                      <span style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                        <span style={{ flexShrink: 0 }}>{option.label}</span>
                        {s.tags?.includes('demo') && (
                          <Tag color="processing" style={{ marginRight: 0 }}>demo</Tag>
                        )}
                        {s.description && (
                          <span
                            title={s.description}
                            style={{
                              flex: 1,
                              minWidth: 0,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              fontSize: 12,
                              color: token.colorTextTertiary,
                            }}
                          >
                            {s.description}
                          </span>
                        )}
                      </span>
                    );
                  }}
                />
              </Form.Item>

              <Form.Item
                name="symbols"
                label={t('backtest_symbols')}
                rules={[{ required: true, message: t('backtest_symbols_required') }]}
              >
                <SymbolSelect
                  mode="multiple"
                  placeholder={t('backtest_symbols_placeholder')}
                  style={{ width: '100%' }}
                  query={{ type: 'spot', exchange: 'binance' }}
                  maxTagCount={3}
                  maxTagPlaceholder={(omittedValues) => t('backtest_max_tags_more', { num: omittedValues.length })}
                />
              </Form.Item>

              {/* demo .m2col 位：时间范围一个 RangePicker 占两列，起止两个输入框即两个日期位 */}
              <Form.Item
                name="timeRange"
                label={t('backtest_time_range')}
                rules={[{ required: true, message: t('backtest_time_range_required') }]}
              >
                <RangePicker
                  format="YYYY-MM-DD"
                  placeholder={[t('backtest_start_date'), t('backtest_end_date')]}
                  style={{ width: '100%' }}
                />
              </Form.Item>

              <Form.Item
                name="interval"
                label={t('bc_kline_interval')}
                rules={[{ required: true, message: t('backtest_interval_required') }]}
              >
                {/* demo .qc-seg 形制：档位与原 Select 全集一致，不设第二种能力 */}
                <Segmented className="qc-mono" options={INTERVAL_OPTIONS} />
              </Form.Item>

              <Form.Item
                name="tradingMode"
                label={t('backtest_trading_mode')}
                rules={[{ required: true, message: t('backtest_trading_mode_required') }]}
                extra={t('backtest_trading_mode_extra')}
              >
                <Select placeholder={t('backtest_trading_mode_required')}>
                  <Option value="spot">{t('trading_mode_spot')}</Option>
                  <Option value="futures">{t('backtest_futures')}</Option>
                </Select>
              </Form.Item>

              {/* demo 2276/2735 参数卡脚注：预计 bar 数（前端纯算术估算） */}
              {estimatedBars !== null && (
                <div className="bc-est-bars">
                  {t('backtest_estimated_bars', { bars: estimatedBars.toLocaleString() })}
                </div>
              )}
            </Card>

            {/* 卡 2 · 成本与账户 */}
            <Card title={t('backtest_cost_account')} className="qc-card bc-card">
              <div className="bc-m2col">
                <Form.Item
                  name="commission"
                  label={t('bc_commission_side')}
                  rules={[{ required: true, message: t('backtest_commission_placeholder') }]}
                >
                  <InputNumber
                    placeholder={t('backtest_commission_placeholder')}
                    min={0}
                    max={1}
                    step={0.0001}
                    style={{ width: '100%' }}
                  />
                </Form.Item>

                <Form.Item
                  name="initialCash"
                  label={t('backtest_initial_cash')}
                  rules={[{ required: true, message: t('backtest_initial_cash_placeholder') }]}
                >
                  <InputNumber
                    placeholder={t('backtest_initial_cash_placeholder')}
                    min={1000}
                    max={100000000}
                    step={1000}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </div>

              <Form.Item
                name="capitalMode"
                label={t('backtest_capital_mode')}
                initialValue="per_symbol"
                extra={
                  isMultiSymbol
                    ? t('backtest_capital_mode_multi_hint')
                    : t('backtest_capital_mode_single_hint')
                }
              >
                {/* demo .qc-seg 形制；value 仍是后端契约 per_symbol/shared，含义不变 */}
                <Segmented disabled={!isMultiSymbol} options={capitalOptions} />
              </Form.Item>

              <Form.Item
                name="factorNames"
                label={t('backtest_factors')}
                extra={
                  watchedStrategy === 'factor_timing'
                    ? t('backtest_factor_timing_hint')
                    : t('backtest_factor_optional_hint')
                }
              >
                <Select
                  mode="multiple"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  placeholder={t('backtest_factors_placeholder')}
                  options={factorOptions.map((f) => ({
                    value: f.name,
                    label: `${f.label} (${f.name})`,
                  }))}
                />
              </Form.Item>

              {/* 仅永续合约出现；Space.Compact / noStyle 的历史坑见下方注释，结构逻辑不动 */}
              {watchedTradingMode === 'futures' && (
                <Form.Item
                  label={t('backtest_margin_specs')}
                  extra={t('backtest_margin_specs_extra')}
                >
                  {/* antd v6 下 space-y-* 会被 CSS-in-JS 覆盖失效，行间距必须用 Space 自己产生 */}
                  <Space orientation="vertical" size="middle" style={{ display: 'flex' }}>
                    {specSymbols.length === 0 ? (
                      <span style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>{t('backtest_select_symbols_first')}</span>
                    ) : (
                      // 行按品种键绑定：字段名里带 symbol，不再用下标对齐，
                      // 品种增删时自然对应，也就不会被 watch 与条件渲染互锁
                      specSymbols.map((symbol) => (
                        <Flex key={symbol} gap="small" align="center">
                          <span className="qc-mono" style={{ minWidth: 100 }}>{symbol}</span>
                          {/* addonAfter 在 antd v6 已废弃，官方迁移方式是 Space.Compact + 禁用按钮作后缀。
                              注意 Space.Compact 必须在 Form.Item 外面：noStyle Form.Item 通过 cloneElement
                              把 value/onChange 注入直接子元素，若直接子元素是 Compact div 容器则 InputNumber 拿不到值 */}
                          <Space.Compact>
                            <Form.Item
                              name={['margin_specs', symbol, 'leverage']}
                              initialValue={1}
                              noStyle
                            >
                              <InputNumber min={1} max={125} step={1} style={{ width: 96 }} />
                            </Form.Item>
                            <Button disabled style={{ width: 36, paddingInline: 0 }}>
                              x
                            </Button>
                          </Space.Compact>
                          <Form.Item
                            name={['margin_specs', symbol, 'margin_mode']}
                            initialValue="cross"
                            noStyle
                          >
                            <Select
                              style={{ width: 110 }}
                              options={[
                                { value: 'cross', label: t('backtest_margin_cross') },
                                { value: 'isolated', label: t('backtest_margin_isolated') },
                              ]}
                            />
                          </Form.Item>
                        </Flex>
                      ))
                    )}
                  </Space>
                </Form.Item>
              )}
            </Card>
          </div>

          {/* 卡 3 · 策略参数配置（通栏）：策略选中后渲染参数表单，未选时占位 */}
          <Card
            title={t('backtest_params_config')}
            className="qc-card bc-card"
            style={{ marginTop: 12 }}
            extra={
              selectedStrategy ? (
                <span className="qc-card-sub qc-mono">
                  {t('bc_params_from', { name: selectedStrategy.name })}
                </span>
              ) : undefined
            }
          >
            {selectedStrategy?.params && selectedStrategy.params.length > 0 ? (
              <div className="bc-params-box">
                <Flex vertical gap="small">
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
                                  <InfoCircleOutlined style={{ marginLeft: 4, color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }} />
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
                  {/* 按标的参数覆盖入口（spec 2026-11-28）：多标的逐标的差异参数 */}
                  <SymbolParamOverrides
                    schema={selectedStrategy.params}
                    symbols={watchedSymbols ?? []}
                    value={paramsBySymbol}
                    onChange={setParamsBySymbol}
                    baseValues={(watchedParams ?? {}) as Record<string, unknown>}
                  />
                </Flex>
              </div>
            ) : (
              <div className="bc-params-empty">
                {selectedStrategy ? t('backtest_no_configurable_params') : t('backtest_select_strategy_for_params')}
              </div>
            )}
            {/* LLM 策略回测只从录制 JSONL 回放，未命中直接失败、不降级（backend/strategy/llm_replay.py） */}
            {isLlmStrategy && (
              <div className="bt-note" style={{ marginTop: 8 }}>{t('bt_llm_replay_note')}</div>
            )}
          </Card>
        </Form>
      </Spin>

      {/* 回测前数据预检弹窗。zIndex 高于进度弹窗，避免被盖住导致用户无法操作 */}
      <Modal
        title={t('backtest_precheck_title')}
        open={precheckVisible}
        zIndex={1100}
        onCancel={() => {
          if (precheckDownloading) {
            precheckAbortRef.current?.abort();
          }
          setPrecheckVisible(false);
          setPrecheckDownloading(false);
        }}
        footer={precheckDownloading ? null : [
          <Button key="cancel" onClick={() => setPrecheckVisible(false)}>{t('cancel')}</Button>,
          <Button
            key="download"
            type="primary"
            onClick={handlePrecheckDownload}
          >
            {t('backtest_download_and_run')}
          </Button>,
        ]}
        width={560}
      >
        <Space orientation="vertical" size="middle" style={{ display: 'flex', width: '100%' }}>
          <div>
            {t('backtest_precheck_missing_before')} <b>{precheckMissing.length}</b>{t('backtest_precheck_missing_after')}
          </div>
          <div style={{ maxHeight: 240, overflowY: 'auto', border: '1px solid var(--tw-color-border-secondary)', borderRadius: 6, padding: 12 }}>
            <Space wrap size={[8, 8]}>
              {precheckMissing.map((m, i) => (
                <Tag key={`${m.symbol}-${m.interval}-${i}`} color="orange" style={{ fontFamily: 'monospace' }}>
                  {m.symbol} · {m.interval}
                </Tag>
              ))}
            </Space>
          </div>
          {precheckDownloading && (
            <>
              <Progress percent={precheckDownloadProgress} status="active" />
              <div style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 60%, transparent)', fontSize: 13 }}>{precheckDownloadMsg}</div>
              {/* 逐品种下载进度: 已完成品种绿色背景 */}
              {precheckSymbolsProgress.length > 0 && (
                <div style={{ maxHeight: 200, overflowY: 'auto', border: '1px solid var(--tw-color-border-secondary)', borderRadius: 6 }}>
                  {precheckSymbolsProgress.map((p) => {
                    const done = p.status === 'completed';
                    return (
                      <div
                        key={`${p.symbol}-${p.interval}`}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '6px 12px',
                          borderBottom: '1px solid var(--tw-color-border-secondary)',
                          background: done ? 'color-mix(in srgb, var(--tw-color-success) 8%, var(--tw-color-background))' : undefined,
                        }}
                      >
                        <span style={{ fontFamily: 'monospace', fontSize: 13 }}>
                          {p.symbol} · {p.interval}
                        </span>
                        <span style={{ fontSize: 12, color: done ? 'var(--tw-color-success)' : 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)' }}>
                          {done ? t('backtest_download_completed') : `${p.percentage}%`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
          <div style={{ color: 'color-mix(in srgb, var(--tw-color-foreground) 50%, transparent)', fontSize: 12 }}>
            {t('backtest_precheck_hint_before')}
            <Button type="link" size="small" style={{ padding: 0 }} onClick={() => navigate('/data-management')}>
              {t('backtest_goto_data_management')}
            </Button>
            {t('backtest_precheck_hint_after')}
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
    </PageContainer>
  );
};

export default BacktestConfig;
