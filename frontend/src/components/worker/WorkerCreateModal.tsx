/**
 * Worker Create Modal
 *
 * 用于创建新的Worker实例
 * 包含表单验证、策略选择、交易所配置等功能
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
  Alert,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  QuestionCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import { useWorkerStore } from '../../store/workerStore';
import { buildWorkerName } from './workerName';
import { strategyApi, configApi } from '../../api';
import { upsertRiskControl } from '../../api/workerApi';
import { usePricePlan } from '../../hooks/usePricePlan';
import PricePlanSection from '../pricePlan/PricePlanSection';
import PricePlanMiniChart from '../pricePlan/PricePlanMiniChart';
import RiskControlForm, {
  EMPTY_RISK_VALUES,
  RISK_FORM_FIELDS,
  formValueToPayload,
  sameRiskValues,
  type RiskFormValues,
} from './RiskControlForm';
import type { CreateWorkerRequest, StrategyInfo, StrategyParameter } from '../../types/worker';
import SymbolSelect from '@/components/SymbolSelect';

const { Option } = Select;
const { TextArea } = Input;

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

interface WorkerCreateModalProps {
  visible: boolean;
  onCancel: () => void;
  onSuccess?: () => void;
}

const WorkerCreateModal: React.FC<WorkerCreateModalProps> = ({
  visible,
  onCancel,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const { createWorker, workers } = useWorkerStore();

  const [loading, setLoading] = useState(false);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  // 交易所相关
  const [exchanges, setExchanges] = useState<{ value: string; label: string }[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  // 交易相关

  // 策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null);

  // Worker名称自动生成：用户手输过就不再覆盖（onChange 只在真实键入时触发，
  // setFieldValue 不触发，正好用作"是否手输"的判定标志）
  const nameTouchedByUserRef = useRef(false);

  // 获取所有数据
  useEffect(() => {
    if (visible) {
      fetchStrategies();
      fetchExchanges();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [visible]);

  // 获取策略列表 - 参考策略管理页面的实现
  const fetchStrategies = async () => {
    setLoadingStrategies(true);
    try {
      // 拦截器已解包 data，直接得到 { strategies: [...] }
      const response = await strategyApi.getStrategies();
      console.log('策略列表响应:', response);

      setStrategies(response.strategies ?? []);
    } catch (error) {
      console.error('获取策略列表失败:', error);
      message.error(t('worker_fetch_strategies_failed'));
      setStrategies([]);
    } finally {
      setLoadingStrategies(false);
    }
  };

  // 策略参数在 worker 创建完成后才存在（后端 GET /workers/{id}/strategy/parameters），
  // 创建流程无 worker_id 可查询，参数区块按空数据隐藏，避免无效请求
  const fetchStrategyParams = async (_strategyId: number) => {
    setStrategyParams([]);
    setLoadingParams(false);
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

      // 如果没有从配置获取到，使用默认列表
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
      // 使用默认列表
      setExchanges([
        { value: 'binance', label: 'Binance' },
        { value: 'okx', label: 'OKX' },
        { value: 'bybit', label: 'Bybit' },
      ]);
    } finally {
      setLoadingExchanges(false);
    }
  };

  // 处理表单提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      // 自选组已由 SymbolSelect 在选择时展开成组内标的；统一大写后提交
      const selectedValues: string[] = values.symbol || [];
      const symbols = Array.from(new Set(selectedValues.map((s) => s.toUpperCase())));
      if (symbols.length === 0) {
        message.error(t('worker_select_valid_trading_target'));
        return;
      }

      // 确保 strategy_id 是数字类型
      const strategyId = typeof values.strategy_id === 'string'
        ? parseInt(values.strategy_id, 10)
        : values.strategy_id;

      // 获取策略文件名（用于三层回退机制）
      const selectedStrategy = strategies.find(
        (s) => s.id === strategyId || s.name === values.strategy_id
      );
      const strategyFileName = selectedStrategy?.file_name || null;

      console.log('[CreateWorker] 策略信息:', {
        strategy_id: strategyId,
        strategy_file_name: strategyFileName,
        strategy_source: selectedStrategy?.source,
        strategy_name: selectedStrategy?.name,
      });

      const requestData: CreateWorkerRequest = {
        // 选策略时已自动生成（或用户手改）；此处兜底用户清空后直接提交的场景
        name: (values.name || '').trim() || buildWorkerName(
          selectedStrategy?.name || '',
          workers.map((w) => w.name)
        ),
        description: values.description,
        strategy_id: strategyId,
        strategy_file_name: strategyFileName,  // 策略文件名
        strategy_name: selectedStrategy?.name || null,  // 策略名称（冗余存储）
        // 交易参数统一走 trading_config（旧扁平字段已被后端 extra="forbid" 拒绝）
        trading_config: {
          exchange: values.exchange,
          symbols_config: { type: 'symbols', symbols },
          interval: values.interval,
          market_type: values.market_type,
          trading_mode: values.trading_mode,
        },
        config: {
          initial_capital: values.initial_capital || 10000,
          max_position_size: values.max_position_size || 0.1,
          leverage: values.leverage || 1,
        },
      };

      const result = await createWorker(requestData);

      if (result) {
        // 人工风控：字段被用户改过才提交（empty-is-null，全空=不启用）；失败不阻断主流程，可稍后在编辑中补配。
        // 新建的 worker 必然不在运行，无需 hot 生效确认弹窗。
        const riskValues = form.getFieldsValue([...RISK_FORM_FIELDS]) as Partial<RiskFormValues>;
        if (!sameRiskValues(riskValues, EMPTY_RISK_VALUES)) {
          try {
            await upsertRiskControl(result.id, formValueToPayload(riskValues));
          } catch (riskError) {
            console.error('保存风控配置失败:', riskError);
            message.warning(t('worker_risk_save_failed_editable'));
          }
        }
        message.success(t('worker_create_success'));
        form.resetFields();
        nameTouchedByUserRef.current = false;
        setStrategyParams([]);
        setSelectedStrategyId(null);
        onSuccess?.();
        onCancel();
      }
    } catch (error) {
      console.error('创建Worker失败:', error);
      message.error(error instanceof Error ? error.message : t('worker_create_failed'));
    } finally {
      setLoading(false);
    }
  };

  // 处理取消
  const handleCancel = () => {
    form.resetFields();
    nameTouchedByUserRef.current = false;
    setStrategyParams([]);
    setSelectedStrategyId(null);
    onCancel();
  };

  return (
    <Modal
      className="qc-modal"
      title={
        <Space>
          <PlusOutlined />
          {t('create_worker')}
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
            icon={<PlusOutlined />}
          >
            {t('create')}
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        className="qc-form"
        layout="vertical"
        initialValues={{
          market_type: 'futures',
          trading_mode: 'paper',
          interval: '1h',
          initial_capital: 10000,
          leverage: 1,
          risk_enabled: false,
        }}
      >
        {/* 基本信息 */}
        <Divider>{t('basic_info')}</Divider>

        <Row gutter={16}>
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
                onChange={(value: number) => {
                  setSelectedStrategyId(value);
                  fetchStrategyParams(value);
                  // 名称未手输时按所选策略自动生成（策略名+短码，避开现有 Worker 名单）
                  if (!nameTouchedByUserRef.current) {
                    // 与下方 Option 的 value 逻辑一致：无 id 策略用名称 hash 当 id
                    const hashName = (n: string) =>
                      Math.abs(n.split('').reduce((a: number, b: string) => {
                        a = ((a << 5) - a) + b.charCodeAt(0);
                        return a & a;
                      }, 0)) % 2147483647 + 1;
                    const strategy = strategies.find(
                      (s) => (s.id !== undefined && s.id !== null ? s.id : hashName(s.name)) === value
                    );
                    if (strategy) {
                      form.setFieldValue(
                        'name',
                        buildWorkerName(strategy.name, workers.map((w) => w.name))
                      );
                    }
                  }
                }}
              >
                {strategies
                  .filter((strategy) => {
                    // 策略必须有 name 字段才能被选择
                    const hasName = strategy.name !== undefined && strategy.name !== null && strategy.name !== '';
                    console.log('策略:', strategy.name, 'id:', strategy.id, 'hasName:', hasName);
                    return hasName;
                  })
                  .map((strategy) => {
                    // 如果没有 id，使用 name 的 hash 作为 id（与后端逻辑一致）
                    const strategyId = strategy.id !== undefined && strategy.id !== null
                      ? strategy.id
                      : Math.abs(strategy.name.split('').reduce((a: number, b: string) => {
                          a = ((a << 5) - a) + b.charCodeAt(0);
                          return a & a;
                        }, 0)) % 2147483647 + 1;
                    return (
                      <Option key={strategyId} value={strategyId} label={strategy.name}>
                        <div style={{ display: 'flex', alignItems: 'center' }}>
                          <span style={{ flexShrink: 0 }}>{strategy.name}</span>
                          {strategy.description && (
                            <span
                              style={{
                                color: 'var(--qc-text-tertiary)',
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
                    );
                  })}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="name"
              label={t('worker_name')}
              rules={[
                { max: 50, message: t('worker_name_max_length') },
              ]}
            >
              <Input
                placeholder={t('worker_name_placeholder')}
                prefix={<InfoCircleOutlined />}
                // 用户键入后不再被选策略的自动生成覆盖
                onChange={() => {
                  nameTouchedByUserRef.current = true;
                }}
              />
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
            <Card size="small" variant="borderless" className="qc-card" style={{ background: 'var(--qc-surface-muted)', marginBottom: 16, boxShadow: 'none' }}>
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
                              <QuestionCircleOutlined style={{ color: 'var(--qc-text-tertiary)' }} />
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
              <SymbolSelect
                mode="multiple"
                placeholder={t('select_trading_target')}
                notFoundContent={t('no_trading_target')}
              />
            </Form.Item>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={12}>
            <Form.Item
              name="interval"
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

        {/* 价格计划自检区：策略含 price_plan 时出现，创建前可见买卖/止盈档位结构 */}
        <PricePlanSelfCheck
          strategy={strategies.find((s) => s.id === selectedStrategyId && s.has_price_plan) ?? null}
        />

        {/* 人工风控（可选：默认关闭，全空字段不提交） */}
        <RiskControlForm form={form} />
      </Form>
    </Modal>
  );
};

/**
 * 创建弹窗自检区：所选策略声明 price_plan 时显示，创建前即可见订单价格范围。
 * 参数预览语义：不解析 strategyParams 定义（结构宽松），只支持 JSON 覆盖——
 * 默认参数由后端 preview resolved merge 补齐（策略文件是唯一权威）。
 */
function PricePlanSelfCheck({ strategy }: { strategy: StrategyInfo | null }) {
  const { t } = useTranslation();
  const [refPrice, setRefPrice] = useState<number | null>(null);
  const [overrideText, setOverrideText] = useState('');

  let overrides: Record<string, unknown> = {};
  try {
    overrides = overrideText.trim() ? (JSON.parse(overrideText) as Record<string, unknown>) : {};
  } catch {
    // 非法 JSON 静默忽略：预览退回策略默认参数，不阻断创建流程
    overrides = {};
  }

  const { data, error, loading } = usePricePlan({
    strategyName: strategy?.name ?? '',
    params: overrides,
    refPrice,
  });

  if (!strategy?.has_price_plan) return null;

  return (
    <Card size="small" title={t('pricePlan.create_self_check_title')} style={{ marginTop: 16 }}>
      <Space orientation="vertical" size="small" style={{ display: 'flex' }}>
        <Space size="small" wrap>
          <Typography.Text>{t('pricePlan.worker_ref_price')}</Typography.Text>
          <InputNumber min={0} value={refPrice} onChange={(v) => setRefPrice(v ?? null)} />
          <Input
            style={{ width: 220 }}
            placeholder={t('pricePlan.create_override_placeholder')}
            value={overrideText}
            onChange={(e) => setOverrideText(e.target.value)}
          />
        </Space>
        {error && <Alert type="warning" message={error} />}
        <PricePlanMiniChart plan={data ?? null} refPrice={refPrice} loading={loading} />
        <PricePlanSection plan={data ?? null} compact maxHeight={120} />
      </Space>
    </Card>
  );
}

export default WorkerCreateModal;
