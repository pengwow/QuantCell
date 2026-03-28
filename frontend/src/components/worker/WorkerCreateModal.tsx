/**
 * Worker Create Modal
 *
 * 用于创建新的Worker实例
 * 包含表单验证、策略选择、交易所配置等功能
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
  message,
  Switch,
  Card,
  Spin,
} from 'antd';
import {
  PlusOutlined,
  QuestionCircleOutlined,
  InfoCircleOutlined,
  StarFilled,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { CreateWorkerRequest } from '../../types/worker';
import { useWorkerStore } from '../../store/workerStore';
import { strategyApi, dataApi, configApi } from '../../api';

const { Option } = Select;
const { TextArea } = Input;

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

// 交易模式
const TRADING_MODES = [
  { value: 'paper', label: '模拟交易' },
  { value: 'live', label: '实盘交易' },
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
  const [form] = Form.useForm();
  const { createWorker } = useWorkerStore();

  const [loading, setLoading] = useState(false);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [loadingStrategies, setLoadingStrategies] = useState(false);
  const [enableResourceConfig, setEnableResourceConfig] = useState(false);

  // 交易所相关
  const [exchanges, setExchanges] = useState<any[]>([]);
  const [loadingExchanges, setLoadingExchanges] = useState(false);

  // 交易相关
  const [symbolOptions, setSymbolOptions] = useState<any[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  // 获取所有数据
  useEffect(() => {
    if (visible) {
      fetchStrategies();
      fetchExchanges();
      fetchSymbolsAndGroups();
    }
  }, [visible]);

  // 获取策略列表 - 参考策略管理页面的实现
  const fetchStrategies = async () => {
    setLoadingStrategies(true);
    try {
      const response = await strategyApi.getStrategies() as { strategies: any[] };
      // 参考 StrategyManagement.tsx 的处理方式
      if (response && response.strategies) {
        setStrategies(response.strategies);
      } else {
        setStrategies([]);
      }
    } catch (error) {
      console.error('获取策略列表失败:', error);
      message.error('获取策略列表失败');
      setStrategies([]);
    } finally {
      setLoadingStrategies(false);
    }
  };

  // 获取已启用的交易所列表
  const fetchExchanges = async () => {
    setLoadingExchanges(true);
    try {
      // 从系统配置获取交易所配置
      const response = await configApi.getConfig();
      const configs = Array.isArray(response) ? response : response?.data || [];

      // 过滤出启用的交易所
      const exchangeConfigs = configs.filter(
        (config: any) =>
          config.plugin === 'exchange' &&
          config.key === 'is_enabled' &&
          config.value === 'true'
      );

      // 获取交易所名称
      const enabledExchanges = exchangeConfigs.map((config: any) => {
        const nameConfig = configs.find(
          (c: any) => c.plugin === 'exchange' && c.key === 'name' && c.scope === config.scope
        );
        return {
          value: config.scope,
          label: nameConfig?.value || config.scope,
        };
      });

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

  // 获取交易对和自选组 - 参考数据管理页面的实现
  const fetchSymbolsAndGroups = async () => {
    setLoadingSymbols(true);
    try {
      // 使用 getCollectionSymbols 接口获取数据池和直接交易标的
      const response = await dataApi.getCollectionSymbols({
        type: 'crypto',
      });

      console.log('getCollectionSymbols response:', response);

      const dataPoolOptions: any[] = [];
      let directSymbolOptions: any[] = [];

      if (response) {
        // 数据池（自选组）- 只显示组名，不展开内部货币对
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

        // 直接交易标的
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

      // 如果 direct_symbols 为空，尝试使用 getCryptoSymbols 获取全部货币对
      if (directSymbolOptions.length === 0) {
        console.log('direct_symbols 为空，尝试使用 getCryptoSymbols 获取全部货币对');
        try {
          const cryptoResponse = await dataApi.getCryptoSymbols({
            limit: 2000,
            offset: 0,
          });
          console.log('getCryptoSymbols response:', cryptoResponse);

          // 处理响应格式 { data: { total, symbols } } 或 { symbols }
          const responseData = cryptoResponse?.data || cryptoResponse;
          const symbolList = responseData?.symbols || responseData?.items || responseData;

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

      console.log('dataPoolOptions:', dataPoolOptions);
      console.log('directSymbolOptions:', directSymbolOptions);

      // 合并选项：数据池在前，直接交易标的在后
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
    try {
      const values = await form.validateFields();
      setLoading(true);

      // 处理交易标的：将数据池展开为内部的所有货币对
      const processedSymbols: string[] = [];
      values.symbols?.forEach((s: string) => {
        if (s.startsWith('pool_')) {
          // 如果是数据池，找到对应的数据池并展开其中的货币对
          const pool = symbolOptions.find((opt) => opt.value === s);
          if (pool && pool.symbols) {
            processedSymbols.push(...pool.symbols);
          }
        } else {
          // 直接交易标的
          processedSymbols.push(s);
        }
      });

      const requestData: CreateWorkerRequest = {
        name: values.name,
        description: values.description,
        strategy_id: values.strategy_id,
        exchange: values.exchange,
        symbols: processedSymbols.map((s: string) => s.toUpperCase()),
        timeframe: values.timeframe,
        market_type: values.market_type,
        trading_mode: values.trading_mode,
        // 只有在启用资源配置时才包含这些字段
        ...(enableResourceConfig && {
          cpu_limit: values.cpu_limit,
          memory_limit: values.memory_limit,
        }),
        config: {
          initial_capital: values.initial_capital || 10000,
          max_position_size: values.max_position_size || 0.1,
          leverage: values.leverage || 1,
        },
      };

      const result = await createWorker(requestData);

      if (result) {
        message.success('Worker创建成功');
        form.resetFields();
        setEnableResourceConfig(false);
        onSuccess?.();
        onCancel();
      }
    } catch (error: any) {
      console.error('创建Worker失败:', error);
      message.error(error.message || '创建Worker失败');
    } finally {
      setLoading(false);
    }
  };

  // 处理取消
  const handleCancel = () => {
    form.resetFields();
    setEnableResourceConfig(false);
    onCancel();
  };

  return (
    <Modal
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
        layout="vertical"
        initialValues={{
          market_type: 'futures',
          trading_mode: 'paper',
          timeframe: '1h',
          initial_capital: 10000,
          leverage: 1,
        }}
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
              >
                {strategies
                  .filter((strategy) => strategy.id !== undefined && strategy.id !== null)
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
              name="symbols"
              label={
                <Space>
                  {t('trading_target')}
                  <Tooltip title={t('trading_target_tooltip')}>
                    <QuestionCircleOutlined />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: t('please_select_trading_target'), type: 'array' }]}
            >
              <Select
                mode="multiple"
                placeholder={t('select_trading_target')}
                loading={loadingSymbols}
                showSearch
                allowClear
                filterOption={(input, option) => {
                  if (!input) return true;
                  // 搜索时同时搜索 value 和 label
                  const value = option?.value as string;
                  const children = option?.children;
                  const labelText = typeof children === 'string' ? children : value;
                  return (
                    value?.toLowerCase().includes(input.toLowerCase()) ||
                    labelText?.toLowerCase().includes(input.toLowerCase())
                  );
                }}
                notFoundContent={loadingSymbols ? <Spin size="small" /> : t('no_trading_target')}
                maxTagCount={3}
                tagRender={(props) => {
                  const { value, closable, onClose } = props;
                  const option = symbolOptions.find((opt) => opt.value === value);
                  const label = option?.poolName || value;
                  return (
                    <span className="ant-select-selection-item">
                      <span className="ant-select-selection-item-content">{label}</span>
                      {closable && (
                        <span
                          className="ant-select-selection-item-remove"
                          onClick={onClose}
                        >
                          ×
                        </span>
                      )}
                    </span>
                  );
                }}
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

        {/* 资源配置 */}
        <Row align="middle" style={{ marginBottom: 16 }}>
          <Col flex="auto">
            <Divider style={{ margin: 0 }}>
              {t('resource_config')}
            </Divider>
          </Col>
          <Col>
            <Switch
              size="small"
              checked={enableResourceConfig}
              onChange={setEnableResourceConfig}
              checkedChildren={t('enabled')}
              unCheckedChildren={t('disabled')}
            />
          </Col>
        </Row>

        {enableResourceConfig && (
          <Card size="small" bordered={false} style={{ background: '#fafafa', marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={12}>
                <Form.Item
                  name="cpu_limit"
                  label={
                    <Space>
                      {t('cpu_limit')}
                      <Tooltip title="CPU使用限制百分比">
                        <QuestionCircleOutlined />
                      </Tooltip>
                    </Space>
                  }
                  initialValue={50}
                >
                  <InputNumber
                    min={10}
                    max={100}
                    formatter={(value) => `${value}%`}
                    parser={(value) => value?.replace('%', '') as any}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item
                  name="memory_limit"
                  label={
                    <Space>
                      {t('memory_limit')}
                      <Tooltip title="内存使用限制(MB)">
                        <QuestionCircleOutlined />
                      </Tooltip>
                    </Space>
                  }
                  initialValue={512}
                >
                  <InputNumber
                    min={128}
                    max={4096}
                    step={128}
                    formatter={(value) => `${value}MB`}
                    parser={(value) => value?.replace('MB', '') as any}
                    style={{ width: '100%' }}
                  />
                </Form.Item>
              </Col>
            </Row>
          </Card>
        )}
      </Form>
    </Modal>
  );
};

export default WorkerCreateModal;
