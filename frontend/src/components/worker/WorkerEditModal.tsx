import { QUANT_COLORS } from '@/utils/colors';
/**
 * Worker Edit Modal
 *
 * 用于编辑现有的Worker实例
 * 允许修改配置、参数等 - 与创建页面保持一致的字段和布局
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Modal,
  Form,
  Input,
  Select,
  Button,
  Space,
  Divider,
  Row,
  Col,
  InputNumber,
  Tooltip,
  App,
  Card,
  Spin,
  Tag,
  Typography,
} from 'antd';
import {
  EditOutlined,
  QuestionCircleOutlined,
  InfoCircleOutlined,
  StarFilled,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import { useWorkerStore } from '../../store/workerStore';
import { strategyApi, configApi } from '../../api';
import { dataApi, type DataPoolRecord, type CryptoSymbol } from '../../api/dataApi';
import { getRiskControl, getStrategyParameters, updateStrategyParameters, upsertRiskControl } from '../../api/workerApi';
import RiskControlForm, {
  EMPTY_RISK_VALUES,
  RISK_FORM_FIELDS,
  formValueToPayload,
  payloadToFormValue,
  sameRiskValues,
  type RiskFormValues,
} from './RiskControlForm';
import type { StrategyInfo, StrategyParameter, TradingConfig, UpdateWorkerRequest, Worker as WorkerModel } from '../../types/worker';

const { Option } = Select;
const { TextArea } = Input;
const { Text } = Typography;

// 根据参数类型渲染不同的输入控件
const renderParamInput = (param: StrategyParameter, t: ReturnType<typeof useTranslation>['t']) => {
  const { param_type, min_value, max_value } = param;

  switch (param_type) {
    case 'int':
      return (
        <InputNumber
          min={min_value}
          max={max_value}
          style={{ width: '100%' }}
          placeholder={t('worker_param_placeholder_int', { min: min_value ?? '-', max: max_value ?? '-' })}
        />
      );
    case 'float':
      return (
        <InputNumber
          min={min_value}
          max={max_value}
          step={0.01}
          precision={2}
          style={{ width: '100%' }}
          placeholder={t('worker_param_placeholder_float', { min: min_value ?? '-', max: max_value ?? '-' })}
        />
      );
    case 'bool':
      return (
        <Select placeholder={t('please_select')}>
          <Option value={true}>{t('yes')}</Option>
          <Option value={false}>{t('no')}</Option>
        </Select>
      );
    case 'json':
      return (
        <TextArea
          rows={2}
          placeholder={t('worker_param_placeholder_json')}
        />
      );
    case 'string':
    default:
      return (
        <Input placeholder={param.description || t('please_input_value')} />
      );
  }
};

// 时间周期列表
// label 存 i18n key，渲染处经 t() 翻译
const TIMEFRAMES = [
  { value: '1m', label: 'period_1m' },
  { value: '5m', label: 'period_5m' },
  { value: '15m', label: 'period_15m' },
  { value: '30m', label: 'period_30m' },
  { value: '1h', label: 'period_1h' },
  { value: '4h', label: 'period_4h' },
  { value: '1d', label: 'period_1d' },
];

// 市场类型
// label 存 i18n key，渲染处经 t() 翻译
const MARKET_TYPES = [
  { value: 'spot', label: 'spot' },
  { value: 'futures', label: 'futures' },
  { value: 'margin', label: 'margin' },
];

// 交易模式（与后端 worker/config.py 保持一致：live/testnet/paper）
// label 存 i18n key，渲染处经 t() 翻译
const TRADING_MODES = [
  { value: 'live', label: 'worker_trading_mode_live' },
  { value: 'testnet', label: 'worker_trading_mode_testnet' },
  { value: 'paper', label: 'worker_trading_mode_paper' },
];

// 可编辑的 worker 对象（含本地表单预填用的扩展字段）
type EditableWorker = WorkerModel & {
  strategy_params?: Record<string, unknown>;
};

interface WorkerEditModalProps {
  visible: boolean;
  worker: EditableWorker | null;
  onCancel: () => void;
  onSuccess?: () => void;
}

// 交易标的选项（数据池 / 直接货币对）
interface SymbolOption {
  label: React.ReactNode;
  value: string;
  type: 'data_pool' | 'direct_symbol';
  symbols?: string[];
  poolName?: string;
}

const WorkerEditModal: React.FC<WorkerEditModalProps> = ({
  visible,
  worker,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message, modal } = App.useApp();
  const [form] = Form.useForm();
  const { updateWorker } = useWorkerStore();

  const [loading, setLoading] = useState(false);
  
  // 策略相关
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);

  // 交易所相关
  const [exchanges, setExchanges] = useState<{ value: string; label: string }[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  // 交易相关
  const [symbolOptions, setSymbolOptions] = useState<SymbolOption[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  // 策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);

  // 人工风控：弹窗打开时 GET 回填，这份快照用于判断用户是否改过风控字段（改过才走确认/PUT）
  const riskSnapshotRef = useRef<RiskFormValues>(EMPTY_RISK_VALUES);

  // 获取所有数据
  useEffect(() => {
    if (visible && worker) {
      fetchStrategies();
      fetchExchanges();
      fetchSymbolsAndGroups();
      fetchRiskControl();

      // 设置表单初始值
      setTimeout(() => {
        setFormValuesFromWorker();
      }, 500); // 延迟以确保策略列表已加载
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [visible, worker]);

  // 人工风控：拉取当前配置回填表单并记快照；GET 失败不阻断编辑（快照保持全空，用户未改动就不会误提交）
  const fetchRiskControl = () => {
    if (!worker) return;
    // 先复位快照与表单：换 worker 打开弹窗时，上一 worker 的风控残留若不清掉，
    // 会在 GET 失败/竞态时被当作「当前 worker 的改动」提交出去
    riskSnapshotRef.current = EMPTY_RISK_VALUES;
    form.setFieldsValue(EMPTY_RISK_VALUES);
    getRiskControl(worker.id)
      .then((out) => {
        const formValue = payloadToFormValue(out);
        riskSnapshotRef.current = formValue;
        form.setFieldsValue(formValue);
      })
      .catch((error) => {
        console.error('获取风控配置失败:', error);
      });
  };

  // 提交风控配置：按 applied 分文案（hot=运行中已实时生效 / on_start=下次启动生效），成功后刷新快照。
  // 返回是否保存成功，供确认弹窗决定去留（失败保持弹窗打开可重试）
  const pushRiskControl = async (workerId: number, values: Partial<RiskFormValues>): Promise<boolean> => {
    try {
      const out = await upsertRiskControl(workerId, formValueToPayload(values));
      if (out?.applied === 'hot') {
        message.success(t('worker_risk_applied_hot'));
      } else {
        message.info(t('worker_risk_applied_on_start'));
      }
      if (out) {
        riskSnapshotRef.current = payloadToFormValue(out);
      }
      return true;
    } catch (error) {
      // 不向上抛：确认弹窗已有 OK 按钮 loading，这里给提示并返回失败
      console.error('保存风控配置失败:', error);
      message.error(t('worker_risk_save_failed'));
      return false;
    }
  };

  // live 运行中改风控的二次确认：旧值 → 新值逐行对照，放宽标橙▲、收紧标绿▼。
  // 返回 'saved'=已保存成功 / 'cancelled'=取消（含失败后放弃），调用方据此决定主弹窗去留
  const confirmRiskUpdate = (workerId: number, next: Partial<RiskFormValues>): Promise<'saved' | 'cancelled'> =>
    new Promise((resolve) => {
      const prev = riskSnapshotRef.current;
      // 数值型风控项；cooldown 特殊：值越大限制越严（锁仓更久），方向与其余上限项相反
      const FIELDS: { f: keyof RiskFormValues; label: string; suffix: string; invert?: boolean }[] = [
        { f: 'risk_max_position_pct', label: t('worker_risk_label_max_position_pct'), suffix: '%' },
        { f: 'risk_max_position_size', label: t('worker_risk_label_max_position_size'), suffix: 'USDT' },
        { f: 'risk_daily_loss_limit', label: t('worker_risk_label_daily_loss_pct'), suffix: '%' },
        { f: 'risk_daily_loss_amount', label: t('worker_risk_label_daily_loss_amount'), suffix: 'USDT' },
        { f: 'risk_max_drawdown', label: t('worker_risk_label_max_drawdown'), suffix: '%' },
        { f: 'risk_max_leverage', label: t('worker_risk_label_max_leverage'), suffix: 'x' },
        { f: 'risk_circuit_breaker_cooldown_secs', label: t('worker_risk_label_cooldown'), suffix: t('worker_risk_unit_minute'), invert: true },
      ];
      const fmtVal = (v: number | null | undefined, suffix: string) =>
        v === null || v === undefined ? '—' : `${v}${suffix ? ' ' : ''}${suffix}`;

      const rows: { key: string; label: string; before: string; after: string; loosen: boolean | null }[] = [];
      let switchingOff = false;

      if (prev.risk_enabled && next.risk_enabled === false) {
        // 启用 → 停用 单独置顶提示
        switchingOff = true;
        rows.push({ key: 'enabled', label: t('worker_risk_protection'), before: t('enabled'), after: t('worker_risk_disable'), loosen: null });
      } else {
        for (const { f, label, suffix, invert } of FIELDS) {
          // TS 联合索引带出 boolean（risk_enabled），运行时这里只会取到数值字段，断言收窄
          const b = (prev[f] as number | null | undefined) ?? null;
          const a = (next[f] as number | null | undefined) ?? null;
          if (b === a) continue;
          // 一侧为 null（引擎默认，具体值未知）时不标注方向
          const loosen: boolean | null =
            b === null || a === null ? null : invert ? a < b : a > b;
          rows.push({
            key: f as string,
            label,
            before: fmtVal(b, suffix),
            after: fmtVal(a, suffix),
            loosen,
          });
        }
      }
      if (rows.length === 0) {
        // sameRiskValues 已挡住，兜底防御
        resolve('cancelled');
        return;
      }

      modal.confirm({
        title: t('worker_risk_confirm_update_title'),
        width: 560,
        content: (
          <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
            {/* spec §5.3 要求的顶部提示：live 运行中热推即刻生效，未运行则下次启动生效 */}
            <Text strong>{t('worker_risk_confirm_effect_note')}</Text>
            {rows.map((r) => (
              <Row key={r.key} gutter={8}>
                <Col span={9}>{r.label}</Col>
                <Col span={15}>
                  <Space size={6}>
                    <Text type="secondary">{r.before}</Text>
                    <span>→</span>
                    <Text>{r.after}</Text>
                    {r.loosen === true && <Tag color="orange">{t('worker_risk_loosen')}</Tag>}
                    {r.loosen === false && <Tag color="green">{t('worker_risk_tighten')}</Tag>}
                  </Space>
                </Col>
              </Row>
            ))}
            {switchingOff && (
              <Text strong type="warning">{t('worker_risk_disable_warning')}</Text>
            )}
          </Space>
        ),
        onOk: async () => {
          // 保存失败返回 false：antd 确认框保持打开，用户可直接重试（失败提示已弹）
          const ok = await pushRiskControl(workerId, next);
          if (!ok) return false;
          resolve('saved');
          return true;
        },
        onCancel: () => resolve('cancelled'),
      });
    });

  // 设置表单值（从 worker 对象）
  const setFormValuesFromWorker = () => {
    if (!worker) return;

    // 从 trading_config JSON 中提取交易参数（唯一来源）
    const tradingConfig: Partial<TradingConfig> =
      typeof worker.trading_config === 'string'
        ? JSON.parse(worker.trading_config || '{}')
        : (worker.trading_config || {});
    const symbolsConfig = tradingConfig.symbols_config;

    const config: Record<string, unknown> =
      typeof worker.config === 'string'
        ? JSON.parse(worker.config || '{}')
        : (worker.config || {});

    // 获取当前策略 ID
    const currentStrategyId = worker.strategy_info?.id || worker.strategy_id;

    form.setFieldsValue({
      name: worker.name,
      description: worker.description,
      strategy_id: currentStrategyId,
      exchange: tradingConfig.exchange || 'binance',
      symbol: symbolsConfig?.symbols ?? [],
      timeframe: tradingConfig.timeframe || '1h',
      market_type: tradingConfig.market_type || 'futures',
      trading_mode: tradingConfig.trading_mode || 'paper',
      initial_capital: config.initial_capital || 10000,
      max_position_size: config.max_position_size || 0.1,
      leverage: config.leverage || 1,
    });

    // 设置当前选中的策略
    if (currentStrategyId) {
      if (worker.id) {
        fetchStrategyParams(worker.id);
      }
    }

    // 加载当前策略的参数值到表单
    if (worker.strategy_params && typeof worker.strategy_params === 'object') {
      const paramsFormValue: Record<string, unknown> = {};
      Object.entries(worker.strategy_params).forEach(([key, value]) => {
        paramsFormValue[`param_${key}`] = value;
      });
      form.setFieldsValue(paramsFormValue);
    }
  };

  // 获取策略列表
  const fetchStrategies = async () => {
    setLoadingStrategies(true);
    try {
      const response = await strategyApi.getStrategies();

      // 兼容后端历史返回格式（数组 / { strategies: [...] }）
      let strategyList: StrategyInfo[] = [];
      if (Array.isArray(response)) {
        strategyList = response as StrategyInfo[];
      } else if (response?.strategies) {
        strategyList = response.strategies;
      }

      setStrategies(strategyList);
    } catch (error) {
      console.error('获取策略列表失败:', error);
      message.error(t('worker_fetch_strategies_failed'));
      setStrategies([]);
    } finally {
      setLoadingStrategies(false);
    }
  };

  // 根据 Worker ID 获取策略参数（参数挂在 worker 上：GET /workers/{id}/strategy/parameters）
  const fetchStrategyParams = async (workerId: number) => {
    if (!workerId) {
      setStrategyParams([]);
      return;
    }

    setLoadingParams(true);
    try {
      const params = await getStrategyParameters(workerId);
      setStrategyParams(params);

      // 将参数默认值设置到表单中
      const paramsFormValue: Record<string, unknown> = {};
      params.forEach((p) => {
        const key = `param_${p.param_name}`;
        // 如果当前 worker 有该参数值，使用它；否则使用默认值
        if (worker?.strategy_params && worker.strategy_params[p.param_name] !== undefined) {
          paramsFormValue[key] = worker.strategy_params[p.param_name];
        } else {
          paramsFormValue[key] = p.default_value ?? p.param_value ?? '';
        }
      });
      form.setFieldsValue(paramsFormValue);
    } catch (error) {
      console.error('获取策略参数失败:', error);
      setStrategyParams([]);
    } finally {
      setLoadingParams(false);
    }
  };

  // 获取已启用的交易所列表
  const fetchExchanges = async () => {
    setLoadingExchanges(true);
    try {
      // GET /config/ 返回按 name 分组的配置：
      // { exchange: { 'exchange.binance.is_enabled': 'true', 'exchange.binance.name': 'Binance', ... } }
      const response = await configApi.getConfig();
      const exchangeGroup =
        response && typeof response.exchange === 'object' && response.exchange !== null
          ? (response.exchange as Record<string, string>)
          : {};

      // 解析启用状态的交易所：key 形如 exchange.<scope>.is_enabled
      const enabledExchanges: { value: string; label: string }[] = [];
      for (const [key, value] of Object.entries(exchangeGroup)) {
        const parts = key.split('.');
        if (parts[0] === 'exchange' && parts[2] === 'is_enabled' && value === 'true') {
          const scope = parts[1];
          const name = exchangeGroup[`exchange.${scope}.name`] || scope;
          enabledExchanges.push({ value: scope, label: name });
        }
      }

      if (enabledExchanges.length === 0) {
        setExchanges([
          { value: 'binance', label: 'Binance' },
          { value: 'okx', label: 'OKX' },
          { value: 'bybit', label: 'Bybit' },
        ]);
      } else {
        setExchanges(enabledExchanges);
      }
    } catch (error) {
      console.error('获取交易所列表失败:', error);
      setExchanges([
        { value: 'binance', label: 'Binance' },
        { value: 'okx', label: 'OKX' },
        { value: 'bybit', label: 'Bybit' },
      ]);
    } finally {
      setLoadingExchanges(false);
    }
  };

  // 获取交易对和自选组
  const fetchSymbolsAndGroups = async () => {
    setLoadingSymbols(true);
    try {
      const response = await dataApi.getCollectionSymbols({
        type: 'crypto',
      });

      console.log('getCollectionSymbols response:', response);

      const dataPoolOptions: SymbolOption[] = [];
      let directSymbolOptions: SymbolOption[] = [];

      if (response) {
        // 数据池（自选组）- 只显示组名，不展开内部货币对
        const dataPools = response.data_pools ?? [];
        dataPools.forEach((pool: DataPoolRecord) => {
          dataPoolOptions.push({
            label: (
              <Space>
                <StarFilled style={{ color: QUANT_COLORS.warning }} />
                <span>{pool.name}</span>
                <span style={{ color: '#999', fontSize: 12 }}>({t('favorite_group')})</span>
              </Space>
            ),
            value: `pool_${pool.id}`,
            type: 'data_pool',
            symbols: pool.symbols || [],
            poolName: pool.name,
          });
        });

        // 直接交易标的
        const directSymbols = response.direct_symbols ?? [];
        directSymbols.forEach((symbol: string) => {
          directSymbolOptions.push({
            label: symbol,
            value: symbol,
            type: 'direct_symbol',
          });
        });
      }

      if (directSymbolOptions.length === 0) {
        try {
          const cryptoResponse = await dataApi.getCryptoSymbols({
            limit: 2000,
            offset: 0,
          });

          const symbolList = cryptoResponse.symbols ?? cryptoResponse.data?.symbols ?? [];

          if (Array.isArray(symbolList)) {
            directSymbolOptions = symbolList.map((item: CryptoSymbol) => {
              const symbolValue = item.symbol || String(item);
              return {
                label: symbolValue,
                value: symbolValue,
                type: 'direct_symbol',
              };
            });
          }
        } catch (cryptoError) {
          console.error('获取全部货币对失败:', cryptoError);
        }
      }

      setSymbolOptions([...dataPoolOptions, ...directSymbolOptions]);
    } catch (error) {
      console.error('获取交易对失败:', error);
      setSymbolOptions([]);
    } finally {
      setLoadingSymbols(false);
    }
  };

  // 处理表单提交
  const handleSubmit = async () => {
    if (!worker) return;

    try {
      const values = await form.validateFields();
      setLoading(true);

      // 处理交易标的：多选值可能是直接货币对或 pool_ 前缀的自选组，统一展开为大写货币对数组
      const selectedValues: string[] = values.symbol || [];
      const expandedSymbols: string[] = [];
      for (const item of selectedValues) {
        if (item.startsWith('pool_')) {
          // 自选组展开为组内全部货币对
          const pool = symbolOptions.find((opt) => opt.value === item);
          if (pool?.symbols?.length) {
            expandedSymbols.push(...pool.symbols);
          }
        } else {
          expandedSymbols.push(item);
        }
      }
      // 去重 + 统一大写（后端按扩写后的符号列表启动独立策略实例）
      const symbols = Array.from(new Set(expandedSymbols.map((s) => s.toUpperCase())));
      if (symbols.length === 0) {
        message.error(t('worker_select_valid_trading_target'));
        return;
      }

      // 策略值可能是数值 id（列表策略有 DB 行）或名称字符串（缺 DB 行时的兜底 value）。
      // 未匹配到选项说明 worker 上的旧 id 已失效（如策略库重建后 id 变化），
      // 保留原 id 并用 worker 冗余的 strategy_info.name 兜底，交给后端按 id→名称双路解析；
      // 连名称都没有时后端无法定位策略，前置拦截给出明确提示，而不是等保存报错。
      const rawStrategyValue = values.strategy_id;
      const selectedStrategy = strategies.find(
        (s) => (s.id != null && s.id === rawStrategyValue) || s.name === rawStrategyValue,
      );

      let strategyId: number | null = null;
      let strategyName: string | null = null;
      if (selectedStrategy) {
        // id 缺失时必须显式传 null：后端 id 查询优先，带旧 id 可能命中错误策略
        strategyId = selectedStrategy.id ?? null;
        strategyName = selectedStrategy.name;
      } else {
        strategyId = typeof rawStrategyValue === 'number' ? rawStrategyValue : worker.strategy_id;
        strategyName = worker.strategy_info?.name ?? null;
        if (!strategyName) {
          message.error(t('worker_strategy_invalid_reselect'));
          return;
        }
      }

      // 获取策略文件名
      const strategyFileName = selectedStrategy?.file_name || null;

      console.log('[EditWorker] 提交数据:', {
        strategy_id: strategyId,
        strategy_file_name: strategyFileName,
        strategy_name: strategyName,
      });

      // 策略参数走独立端点持久化：此前只塞进 worker payload 的 strategy_params，
      // 后端 schema 从未声明该字段，所填值被静默丢弃。
      const parameters = strategyParams.reduce<Record<string, unknown>>((acc, param) => {
        const fieldValue = values[`param_${param.param_name}`];
        if (fieldValue !== undefined && fieldValue !== null && fieldValue !== '') {
          acc[param.param_name] = fieldValue;
        }
        return acc;
      }, {});

      const requestData: UpdateWorkerRequest = {
        name: values.name,
        description: values.description,
        strategy_id: strategyId,
        strategy_file_name: strategyFileName,
        strategy_name: strategyName,
        // 交易参数统一走 trading_config（旧扁平字段已被后端 extra="forbid" 拒绝）
        trading_config: {
          exchange: values.exchange,
          symbols_config: { type: 'symbols', symbols },
          timeframe: values.timeframe,
          market_type: values.market_type,
          trading_mode: values.trading_mode,
        },
        config: {
          initial_capital: values.initial_capital || 10000,
          max_position_size: values.max_position_size || 0.1,
          leverage: values.leverage || 1,
        },
      };

      const result = await updateWorker(worker.id, requestData);

      if (result) {
        if (Object.keys(parameters).length > 0) {
          await updateStrategyParameters(worker.id, { parameters });
        }
        // 人工风控：仅在用户改动过风控字段时提交；live 运行中需逐项确认后再应用（PUT 不阻断主流程）
        const riskValues = form.getFieldsValue([...RISK_FORM_FIELDS]) as Partial<RiskFormValues>;
        if (!sameRiskValues(riskValues, riskSnapshotRef.current)) {
          const tc: Record<string, unknown> =
            typeof worker.trading_config === 'string'
              ? JSON.parse(worker.trading_config || '{}')
              : worker.trading_config || {};
          const isLiveRunning = tc.trading_mode === 'live' && worker.status === 'running';
          if (isLiveRunning) {
            // 等待二次确认结果：用户取消时不关闭主弹窗（Worker 其余修改已保存，可继续编辑）
            const outcome = await confirmRiskUpdate(worker.id, riskValues);
            if (outcome === 'cancelled') {
              message.info(t('worker_risk_update_cancelled'));
              return;
            }
          } else {
            await pushRiskControl(worker.id, riskValues);
          }
        }
        message.success(t('worker_update_success'));
        onSuccess?.();
        handleCancel();
      }
    } catch (error) {
      console.error('更新Worker失败:', error);
      message.error(error instanceof Error ? error.message : t('worker_update_failed'));
    } finally {
      setLoading(false);
    }
  };

  // 处理取消
  const handleCancel = () => {
    form.resetFields();
    setStrategyParams([]);
    onCancel();
  };

  if (!worker) return null;

  return (
    <Modal
      title={
        <Space>
          <EditOutlined />
          {t('edit_worker')}: {worker.name}
        </Space>
      }
      open={visible}
      onCancel={handleCancel}
      width={720}
      footer={
        <Space>
          <Button onClick={handleCancel}>{t('cancel')}</Button>
          <Button
            type="primary"
            onClick={handleSubmit}
            loading={loading}
            icon={<EditOutlined />}
          >
            {t('save')}
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
      >
        {/* 基本信息 */}
        <Divider>{t('basic_info')}</Divider>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="name"
              label={t('worker_name')}
              rules={[
                { required: true, message: t('worker_name_required') },
                { max: 50, message: t('worker_name_max_length') },
              ]}
            >
              <Input
                placeholder={t('worker_name_placeholder')}
                prefix={<InfoCircleOutlined />}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="strategy_id"
              label={
                <Space>
                  {t('strategy')}
                  <Tooltip title={t('worker_strategy_tooltip')}>
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: t('select_strategy') }]}
            >
              <Select
                placeholder={t('select_strategy_title')}
                loading={loadingStrategies}
                showSearch
                // 回填到选择框只显示策略名，完整信息（名称+描述）在下拉项里展示
                optionLabelProp="label"
                // 下拉搜索同时匹配策略名与描述
                filterOption={(input, option) => {
                  const strategy = strategies.find(
                    (s) => String(s.id ?? s.name) === String(option?.value)
                  );
                  const text = `${strategy?.name ?? ''} ${strategy?.description ?? ''}`.toLowerCase();
                  return text.includes(input.toLowerCase());
                }}
                notFoundContent={loadingStrategies ? <Spin size="small" /> : t('no_strategies')}
                onChange={() => {
                  if (worker.id) {
                    fetchStrategyParams(worker.id);
                  }
                }}
              >
                {strategies
                  // 只要求 name：/strategy/list 的 id 可能为 null（策略缺 DB 行），
                  // 按 id 过滤会把有效策略全部丢弃、下拉变空
                  .filter((strategy) => strategy?.name)
                  .map((strategy) => (
                    // 缺 id 的策略用 name 作为 value，保存时让后端按名称解析回真实 id
                    <Option
                      key={strategy.id ?? strategy.name}
                      value={strategy.id ?? strategy.name}
                      label={strategy.name}
                    >
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        <span style={{ flexShrink: 0 }}>{strategy.name}</span>
                        {strategy.description && (
                          <span
                            style={{
                              color: '#999',
                              fontSize: 12,
                              marginLeft: 8,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {strategy.description}
                          </span>
                        )}
                      </div>
                    </Option>
                  ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        <Form.Item
          name="description"
          label={t('description')}
        >
          <TextArea
            rows={2}
            placeholder={t('worker_description_placeholder')}
            maxLength={200}
            showCount
          />
        </Form.Item>

        {/* 策略参数 */}
        {strategyParams.length > 0 && (
          <>
            <Divider>
              <Space>
                {t('strategy_params')}
                {loadingParams && <Spin size="small" />}
              </Space>
            </Divider>
            <Card size="small" variant="borderless" style={{ background: '#fafafa', marginBottom: 16 }}>
              <Row gutter={[12, 12]}>
                {strategyParams.map((param) => (
                  <Col span={12} key={param.param_name}>
                    <Form.Item
                      name={`param_${param.param_name}`}
                      label={
                        <Space>
                          <span>{param.param_name}</span>
                          {param.description && (
                            <Tooltip title={param.description}>
                              <QuestionCircleOutlined style={{ color: '#999' }} />
                            </Tooltip>
                          )}
                        </Space>
                      }
                      tooltip={param.description}
                      rules={param.required ? [{ required: true, message: t('worker_please_input_param', { name: param.param_name }) }] : []}
                    >
                      {renderParamInput(param, t)}
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </Card>
          </>
        )}

        {/* 交易配置 */}
        <Divider>{t('trading_config')}</Divider>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="exchange"
              label={t('exchange')}
              rules={[{ required: true, message: t('worker_please_select_exchange') }]}
            >
              <Select
                placeholder={t('worker_select_exchange')}
                loading={loadingExchanges}
                showSearch
              >
                {exchanges.map((exchange) => (
                  <Option key={exchange.value} value={exchange.value}>
                    {exchange.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="symbol"
              label={
                <Space>
                  {t('trading_target')}
                  <Tooltip title={t('trading_target_tooltip')}>
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: t('please_select_trading_target') }]}
            >
              <Select
                mode="multiple"
                placeholder={t('select_trading_target')}
                loading={loadingSymbols}
                showSearch
                allowClear
                filterOption={(input, option) => {
                  if (!input) return true;
                  const value = option?.value as string;
                  const children = option?.children;
                  const labelText = typeof children === 'string' ? children : value;
                  return (
                    value?.toLowerCase().includes(input.toLowerCase()) ||
                    labelText?.toLowerCase().includes(input.toLowerCase())
                  );
                }}
                notFoundContent={loadingSymbols ? <Spin size="small" /> : t('no_trading_target')}
              >
                {symbolOptions.map((option) => (
                  <Option key={option.value} value={option.value}>
                    {option.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="timeframe"
              label={t('timeframe')}
              rules={[{ required: true, message: t('worker_please_select_timeframe') }]}
            >
              <Select placeholder={t('select_interval_placeholder')}>
                {TIMEFRAMES.map((tf) => (
                  <Option key={tf.value} value={tf.value}>
                    {t(tf.label)}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="market_type"
              label={t('market_type')}
              rules={[{ required: true, message: t('worker_please_select_market_type') }]}
            >
              <Select placeholder={t('worker_select_market_type')}>
                {MARKET_TYPES.map((type) => (
                  <Option key={type.value} value={type.value}>
                    {t(type.label)}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="trading_mode"
              label={
                <Space>
                  {t('trading_mode')}
                  <Tooltip title={t('worker_trading_mode_tooltip')}>
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: t('backtest_trading_mode_required') }]}
            >
              <Select placeholder={t('worker_select_trading_mode')}>
                {TRADING_MODES.map((mode) => (
                  <Option key={mode.value} value={mode.value}>
                    {t(mode.label)}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="leverage"
              label={t('leverage')}
            >
              <InputNumber
                min={1}
                max={125}
                style={{ width: '100%' }}
                placeholder={t('leverage')}
              />
            </Form.Item>
          </Col>
        </Row>

        {/* 资金配置 */}
        <Divider>{t('capital_config')}</Divider>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="initial_capital"
              label={t('initial_capital')}
            >
              <InputNumber<number>
                min={100}
                step={1000}
                style={{ width: '100%' }}
                formatter={(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                parser={(value) => Number(value?.replace(/\$|,/g, '') || 0)}
              />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="max_position_size"
              label={
                <Space>
                  {t('max_position_size')}
                  <Tooltip title={t('worker_max_position_tooltip')}>
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
            >
              <InputNumber
                min={0.01}
                max={1}
                step={0.01}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
        </Row>

        {/* 人工风控（运行中 PUT 实时生效，live 变更需逐项确认） */}
        <RiskControlForm form={form} />
      </Form>
    </Modal>
  );
};

export default WorkerEditModal;
