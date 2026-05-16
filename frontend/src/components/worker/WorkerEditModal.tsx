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
import { strategyApi, dataApi, configApi } from '../../api';
import type { StrategyParameter } from '../../types/worker';

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

interface WorkerEditModalProps {
  visible: boolean;
  worker: any; // 使用 any 类型以支持 worker 对象的所有属性
  onCancel: () => void;
  onSuccess?: () => void;
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
  const [strategies, setStrategies] = useState<any[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [selectedStrategyId, setSelectedStrategyId] = useState<number | null>(null);

  // 交易所相关
  const [exchanges, setExchanges] = useState<any[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  // 交易相关
  const [symbolOptions, setSymbolOptions] = useState<any[]>([]);
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
  }, [visible, worker]);

  // 设置表单值（从 worker 对象）
  const setFormValuesFromWorker = () => {
    if (!worker) return;

    // 从 trading_config JSON 中提取配置
    const tradingConfig = typeof worker.trading_config === 'string'
      ? JSON.parse(worker.trading_config || '{}')
      : (worker.trading_config || {});

    const config = typeof worker.config === 'string'
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
      fetchStrategyParams(currentStrategyId);
    }

    // 加载当前策略的参数值到表单
    if (worker.strategy_params && typeof worker.strategy_params === 'object') {
      const paramsFormValue: Record<string, any> = {};
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
      const response = await strategyApi.getStrategies() as any;
      console.log('策略列表响应:', response);

      let strategyList: any[] = [];

      if (Array.isArray(response)) {
        strategyList = response;
      } else if (response?.strategies) {
        strategyList = response.strategies;
      } else if (response?.data?.strategies) {
        strategyList = response.data.strategies;
      } else if (response?.data?.strategies?.[0]) {
        strategyList = response.data.strategies[0];
      }

      console.log('解析后的策略列表:', strategyList);
      setStrategies(strategyList);
    } catch (error) {
      console.error('获取策略列表失败:', error);
      message.error('获取策略列表失败');
      setStrategies([]);
    } finally {
      setLoadingStrategies(false);
    }
  };

  // 根据策略ID获取策略参数
  const fetchStrategyParams = async (strategyId: number) => {
    if (!strategyId) {
      setStrategyParams([]);
      return;
    }

    setLoadingParams(true);
    try {
      const response = await strategyApi.getStrategyParams(strategyId) as any;
      let params: StrategyParameter[] = [];

      if (Array.isArray(response)) {
        params = response;
      } else if (response?.data && Array.isArray(response.data)) {
        params = response.data;
      } else if (response?.data?.parameters && Array.isArray(response.data.parameters)) {
        params = response.data.parameters;
      }

      console.log('编辑页策略参数:', params);
      setStrategyParams(params);

      // 将参数默认值设置到表单中
      const paramsFormValue: Record<string, any> = {};
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
      const response = await configApi.getConfig();
      const configs = Array.isArray(response) ? response : response?.data || [];

      const exchangeConfigs = configs.filter(
        (config: any) =>
          config.plugin === 'exchange' &&
          config.key === 'is_enabled' &&
          config.value === 'true'
      );

      const enabledExchanges = exchangeConfigs.map((config: any) => {
        const nameConfig = configs.find(
          (c: any) => c.plugin === 'exchange' && c.key === 'name' && c.scope === config.scope
        );
        return {
          value: config.scope,
          label: nameConfig?.value || config.scope,
        };
      });

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

      const dataPoolOptions: any[] = [];
      let directSymbolOptions: any[] = [];

      if (response) {
        const dataPools = response.data_pools || response.pools || [];
        if (Array.isArray(dataPools)) {
          dataPools.forEach((pool: any) => {
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
        }

        const directSymbols = response.direct_symbols || response.symbols || [];
        if (Array.isArray(directSymbols)) {
          directSymbols.forEach((symbol: any) => {
            const symbolValue = typeof symbol === 'string' ? symbol : (symbol.symbol || symbol.name || String(symbol));
            directSymbolOptions.push({
              label: symbolValue,
              value: symbolValue,
              type: 'direct_symbol',
            });
          });
        }
      }

      if (directSymbolOptions.length === 0) {
        try {
          const cryptoResponse = await dataApi.getCryptoSymbols({
            limit: 2000,
            offset: 0,
          });

          const symbolList = cryptoResponse?.symbols || [];

          if (Array.isArray(symbolList)) {
            directSymbolOptions = symbolList.map((item: any) => {
              const symbolValue = typeof item === 'string' ? item : (item.symbol || item.name || String(item));
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
        }, {} as Record<string, any>),

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
    } catch (error: any) {
      console.error('更新Worker失败:', error);
      message.error(error.message || '更新Worker失败');
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
                  fetchStrategyParams(value);
                }}
              >
                {strategies
                  .filter((strategy) => {
                    const hasName = strategy.name !== undefined && strategy.name !== null && strategy.name !== '';
                    return hasName;
                  })
                  .map((strategy) => {
                    const strategyId = strategy.id !== undefined && strategy.id !== null
                      ? strategy.id
                      : Math.abs(strategy.name.split('').reduce((a: number, b: string) => {
                          a = ((a << 5) - a) + b.charCodeAt(0);
                          return a & a;
                        }, 0)) % 2147483647 + 1;
                    return (
                      <Option key={strategyId} value={strategyId}>
                        {strategy.name}
                      </Option>
                    );
                  })}
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
              <InputNumber
                min={100}
                step={1000}
                style={{ width: '100%' }}
                formatter={(value) => `$ ${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                parser={(value) => value?.replace(/\$\s?|(,*)/g, '') as any}
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
