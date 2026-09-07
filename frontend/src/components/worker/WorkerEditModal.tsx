/**
 * Worker Edit Modal
 *
 * 用于编辑现有的Worker实例
 * 允许修改配置、参数等 - 与创建页面保持一致的字段和布局
 */

import React, { useState, useEffect } from 'react';
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
} from 'antd';
import {
  EditOutlined,
  QuestionCircleOutlined,
  InfoCircleOutlined,
  StarFilled,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import { useWorkerStore } from '../../store/workerStore';
import { strategyApi, dataApi, configApi, type DataPoolRecord, type CryptoSymbol } from '../../api';
import { getStrategyParameters } from '../../api/workerApi';
import type { StrategyInfo, StrategyParameter, Worker as WorkerModel } from '../../types/worker';

const { Option } = Select;
const { TextArea } = Input;

// 根据参数类型渲染不同的输入控件
const renderParamInput = (param: StrategyParameter) => {
  const { param_type, min_value, max_value } = param;

  switch (param_type) {
    case 'int':
      return (
        <InputNumber
          min={min_value}
          max={max_value}
          style={{ width: '100%' }}
          placeholder={`整数 (${min_value ?? '-'} ~ ${max_value ?? '-'})`}
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
          placeholder={`浮点数 (${min_value ?? '-'} ~ ${max_value ?? '-'})`}
        />
      );
    case 'bool':
      return (
        <Select placeholder="选择">
          <Option value={true}>是</Option>
          <Option value={false}>否</Option>
        </Select>
      );
    case 'json':
      return (
        <TextArea
          rows={2}
          placeholder='JSON 格式，如: {"key": "value"}'
        />
      );
    case 'string':
    default:
      return (
        <Input placeholder={param.description || '请输入值'} />
      );
  }
};

// 时间周期列表
const TIMEFRAMES = [
  { value: '1m', label: '1分钟' },
  { value: '5m', label: '5分钟' },
  { value: '15m', label: '15分钟' },
  { value: '30m', label: '30分钟' },
  { value: '1h', label: '1小时' },
  { value: '4h', label: '4小时' },
  { value: '1d', label: '1天' },
];

// 市场类型
const MARKET_TYPES = [
  { value: 'spot', label: '现货' },
  { value: 'futures', label: '合约' },
  { value: 'margin', label: '杠杆' },
];

// 交易模式（与后端 worker/config.py 保持一致：live/testnet/paper）
const TRADING_MODES = [
  { value: 'live', label: '实盘交易' },
  { value: 'testnet', label: '测试网' },
  { value: 'paper', label: '本地模拟' },
];

// 可编辑的 worker 对象（含历史兼容字段）
type EditableWorker = WorkerModel & {
  symbol?: string;
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
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const { updateWorker } = useWorkerStore();

  const [loading, setLoading] = useState(false);
  
  // 策略相关
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [, setSelectedStrategyId] = useState<number | null>(null);

  // 交易所相关
  const [exchanges, setExchanges] = useState<{ value: string; label: string }[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  // 交易相关
  const [symbolOptions, setSymbolOptions] = useState<SymbolOption[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  // 策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);

  // 获取所有数据
  useEffect(() => {
    if (visible && worker) {
      fetchStrategies();
      fetchExchanges();
      fetchSymbolsAndGroups();
      
      // 设置表单初始值
      setTimeout(() => {
        setFormValuesFromWorker();
      }, 500); // 延迟以确保策略列表已加载
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 组件函数每渲染重建，补 deps 会重复执行
  }, [visible, worker]);

  // 设置表单值（从 worker 对象）
  const setFormValuesFromWorker = () => {
    if (!worker) return;

    // 从 trading_config JSON 中提取配置
    const tradingConfig: Record<string, unknown> =
      typeof worker.trading_config === 'string'
        ? JSON.parse(worker.trading_config || '{}')
        : (worker.trading_config || {});

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
      exchange: worker.exchange || tradingConfig.exchange || 'binance',
      symbol: worker.symbol || (worker.symbols && worker.symbols[0]) || '',
      timeframe: worker.timeframe || '1h',
      market_type: worker.market_type || tradingConfig.market_type || 'futures',
      trading_mode: tradingConfig.trading_mode || 'paper',
      initial_capital: config.initial_capital || 10000,
      max_position_size: config.max_position_size || 0.1,
      leverage: config.leverage || 1,
    });

    // 设置当前选中的策略
    if (currentStrategyId) {
      setSelectedStrategyId(currentStrategyId);
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
      message.error('获取策略列表失败');
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
                <StarFilled style={{ color: '#faad14' }} />
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

      // 处理交易标的：后端期望单个 symbol 字符串
      let selectedSymbol = values.symbol || '';
      if (selectedSymbol.startsWith('pool_')) {
        const pool = symbolOptions.find((opt) => opt.value === selectedSymbol);
        if (pool && pool.symbols && pool.symbols.length > 0) {
          selectedSymbol = pool.symbols[0];
        }
      }

      // 确保 strategy_id 是数字类型
      const strategyId = typeof values.strategy_id === 'string'
        ? parseInt(values.strategy_id, 10)
        : values.strategy_id;

      // 获取策略文件名
      const selectedStrategy = strategies.find(
        (s) => s.id === strategyId || s.name === values.strategy_id
      );
      const strategyFileName = selectedStrategy?.file_name || null;

      console.log('[EditWorker] 提交数据:', {
        strategy_id: strategyId,
        strategy_file_name: strategyFileName,
        strategy_name: selectedStrategy?.name,
      });

      const requestData = {
        name: values.name,
        description: values.description,
        strategy_id: strategyId,
        strategy_file_name: strategyFileName,
        strategy_name: selectedStrategy?.name || null,  // 新增：策略名称（冗余存储）
        exchange: values.exchange,
        symbol: selectedSymbol.toUpperCase(),
        timeframe: values.timeframe,
        market_type: values.market_type,
        trading_mode: values.trading_mode,

        // 策略参数
        strategy_params: strategyParams.reduce((acc, param) => {
          const fieldValue = values[`param_${param.param_name}`];
          if (fieldValue !== undefined && fieldValue !== null && fieldValue !== '') {
            acc[param.param_name] = fieldValue;
          } else if (param.default_value !== undefined && param.default_value !== null) {
            acc[param.param_name] = param.default_value;
          }
          return acc;
        }, {} as Record<string, unknown>),

        config: {
          initial_capital: values.initial_capital || 10000,
          max_position_size: values.max_position_size || 0.1,
          leverage: values.leverage || 1,
        },
      };

      const result = await updateWorker(worker.id, requestData);

      if (result) {
        message.success('Worker更新成功');
        onSuccess?.();
        onCancel();
      }
    } catch (error) {
      console.error('更新Worker失败:', error);
      message.error(error instanceof Error ? error.message : '更新Worker失败');
    } finally {
      setLoading(false);
    }
  };

  // 处理取消
  const handleCancel = () => {
    form.resetFields();
    setStrategyParams([]);
    setSelectedStrategyId(null);
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
                { required: true, message: '请输入Worker名称' },
                { max: 50, message: '名称不能超过50个字符' },
              ]}
            >
              <Input
                placeholder="例如：BTC趋势跟踪策略"
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
                  <Tooltip title="选择要运行的策略">
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: '请选择策略' }]}
            >
              <Select
                placeholder="选择策略"
                loading={loadingStrategies}
                showSearch
                optionFilterProp="children"
                notFoundContent={loadingStrategies ? <Spin size="small" /> : '暂无策略'}
                onChange={(value: number) => {
                  setSelectedStrategyId(value);
                  if (worker.id) {
                    fetchStrategyParams(worker.id);
                  }
                }}
              >
                {strategies
                  .filter((strategy) => strategy?.id && strategy?.name)
                  .map((strategy) => (
                    <Option key={strategy.id} value={strategy.id}>
                      {strategy.name}
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
            placeholder="描述这个Worker的用途..."
            maxLength={200}
            showCount
          />
        </Form.Item>

        {/* 策略参数 */}
        {strategyParams.length > 0 && (
          <>
            <Divider>
              <Space>
                策略参数
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
                      rules={param.required ? [{ required: true, message: `请输入 ${param.param_name}` }] : []}
                    >
                      {renderParamInput(param)}
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
              rules={[{ required: true, message: '请选择交易所' }]}
            >
              <Select
                placeholder="选择交易所"
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
              rules={[{ required: true, message: '请选择时间周期' }]}
            >
              <Select placeholder="选择时间周期">
                {TIMEFRAMES.map((tf) => (
                  <Option key={tf.value} value={tf.value}>
                    {tf.label}
                  </Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item
              name="market_type"
              label={t('market_type')}
              rules={[{ required: true, message: '请选择市场类型' }]}
            >
              <Select placeholder="选择市场类型">
                {MARKET_TYPES.map((type) => (
                  <Option key={type.value} value={type.value}>
                    {type.label}
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
                  <Tooltip title="模拟交易不会产生真实交易，实盘交易将使用真实资金">
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: '请选择交易模式' }]}
            >
              <Select placeholder="选择交易模式">
                {TRADING_MODES.map((mode) => (
                  <Option key={mode.value} value={mode.value}>
                    {mode.label}
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
                placeholder="杠杆倍数"
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
                  <Tooltip title="最大仓位比例(0-1)">
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

      </Form>
    </Modal>
  );
};

export default WorkerEditModal;
