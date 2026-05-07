/**
 * Worker Edit Modal
 *
 * 用于编辑现有的Worker实例
 * 允许修改配置、参数等
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
  Tabs,
  Card,
  Tag,
  Spin,
} from 'antd';
import {
  EditOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
  SlidersOutlined,
  CodeOutlined,
  TagOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Worker, UpdateWorkerRequest } from '../../types/worker';
import type { StrategyParameter } from '../../types/worker';
import { useWorkerStore } from '../../store/workerStore';
import { dataApi, strategyApi } from '../../api';

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

// 交易模式（与后端 worker/config.py 保持一致：live/testnet/paper）
const TRADING_MODES = [
  { value: 'live', label: '实盘交易' },
  { value: 'testnet', label: '测试网' },
  { value: 'paper', label: '本地模拟' },
];

interface WorkerEditModalProps {
  visible: boolean;
  worker: Worker | null;
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
  const { message: apiMessage } = App.useApp();
  const [form] = Form.useForm();
  const { updateWorker } = useWorkerStore();

  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('basic');
  const [symbolOptions, setSymbolOptions] = useState<any[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

  // 策略参数
  const [strategyParams, setStrategyParams] = useState<StrategyParameter[]>([]);
  const [loadingParams, setLoadingParams] = useState(false);

  // 获取交易对列表
  const fetchSymbols = async () => {
    setLoadingSymbols(true);
    try {
      const response = await dataApi.getCryptoSymbols({
        limit: 2000,
        offset: 0,
      });

      // API 已经通过拦截器解包，response 直接是 data 字段的内容
      // 结构为: { symbols: [...], total: ..., offset: ..., limit: ..., exchange: ... }
      const symbolList = response?.symbols || [];

      if (Array.isArray(symbolList)) {
        const options = symbolList.map((item: any) => {
          const symbolValue = typeof item === 'string' ? item : (item.symbol || item.name || String(item));
          return {
            label: symbolValue,
            value: symbolValue,
          };
        });
        setSymbolOptions(options);
      }
    } catch (error) {
      console.error('获取交易对失败:', error);
      setSymbolOptions([]);
    } finally {
      setLoadingSymbols(false);
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

      // 将参数默认值设置到表单中（首次加载时）
      const paramsFormValue: Record<string, any> = {};
      params.forEach((p) => {
        const key = `param_${p.param_name}`;
        paramsFormValue[key] = p.default_value ?? p.param_value ?? '';
      });
      form.setFieldsValue(paramsFormValue);
    } catch (error) {
      console.error('获取策略参数失败:', error);
      setStrategyParams([]);
    } finally {
      setLoadingParams(false);
    }
  };

  // 当worker变化时，设置表单值
  useEffect(() => {
    if (visible && worker) {
      // 从 trading_config JSON 中提取 trading_mode
      const tradingConfig = typeof worker.trading_config === 'string'
        ? JSON.parse(worker.trading_config || '{}')
        : (worker.trading_config || {});

      const config = typeof worker.config === 'string'
        ? JSON.parse(worker.config || '{}')
        : (worker.config || {});

      form.setFieldsValue({
        name: worker.name,
        description: worker.description,
        symbols: worker.symbols,
        timeframe: worker.timeframe,
        trading_mode: tradingConfig.trading_mode || 'paper',
        initial_capital: config.initial_capital || 10000,
        max_position_size: config.max_position_size || 0.1,
        leverage: config.leverage || 1,
      });
      // 加载交易对列表
      fetchSymbols();
      // 加载策略参数（从 strategy_info 获取 strategy_id）
      if (worker.strategy_info?.id) {
        fetchStrategyParams(worker.strategy_info.id);
      }
    }
  }, [visible, worker, form]);

  // 处理表单提交
  const handleSubmit = async () => {
    if (!worker) return;

    try {
      const values = await form.validateFields();
      setLoading(true);

      const requestData: UpdateWorkerRequest = {
        name: values.name,
        description: values.description,
        symbols: values.symbols?.map((s: string) => s.toUpperCase()),
        timeframe: values.timeframe,
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
          initial_capital: values.initial_capital,
          max_position_size: values.max_position_size,
          leverage: values.leverage,
        },
      };

      const result = await updateWorker(worker.id, requestData);

      if (result) {
        apiMessage.success('Worker更新成功');
        onSuccess?.();
        onCancel();
      }
    } catch (error: any) {
      console.error('更新Worker失败:', error);
      apiMessage.error(error.message || '更新Worker失败');
    } finally {
      setLoading(false);
    }
  };

  // 处理取消
  const handleCancel = () => {
    form.resetFields();
    setActiveTab('basic');
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
      {/* 策略信息（只读展示） */}
      {worker.strategy_info && (
        <Card
          size="small"
          style={{ marginBottom: 16, background: '#fafafa' }}
        >
          <Row gutter={16} align="middle">
            <Col>
              <CodeOutlined style={{ color: '#1890ff', marginRight: 8 }} />
              <span style={{ fontWeight: 600 }}>{worker.strategy_info.name}</span>
            </Col>
            <Col>
              <Tag icon={<TagOutlined />} color={worker.strategy_info.strategy_type === 'default' ? 'green' : 'purple'}>
                {worker.strategy_info.strategy_type === 'default' ? '默认策略' : '旧版策略'}
              </Tag>
            </Col>
            <Col>
              <span style={{ color: '#999' }}>v{worker.strategy_info.version}</span>
            </Col>
            {worker.strategy_info.description && (
              <Col flex="auto" style={{ textAlign: 'right' }}>
                <span style={{ color: '#666', fontSize: 13 }}>{worker.strategy_info.description}</span>
              </Col>
            )}
          </Row>
        </Card>
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'basic',
            label: (
              <span>
                <SettingOutlined />
                {t('basic_config')}
              </span>
            ),
            children: (
              <Form form={form} layout="vertical">
                {/* 基本信息 */}
                <Divider>{t('basic_info')}</Divider>

                <Row gutter={16}>
                  <Col span={24}>
                    <Form.Item
                      name="name"
                      label={t('worker_name')}
                      rules={[
                        { required: true, message: '请输入Worker名称' },
                        { max: 50, message: '名称不能超过50个字符' },
                      ]}
                    >
                      <Input placeholder="Worker名称" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item
                  name="description"
                  label={t('description')}
                >
                  <TextArea
                    rows={3}
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
                      name="symbols"
                      label={t('trading_target')}
                      rules={[
                        { required: true, message: t('please_select_trading_target'), type: 'array' },
                      ]}
                    >
                      <Select
                        mode="multiple"
                        placeholder={t('select_trading_target')}
                        allowClear
                        maxTagCount={3}
                        loading={loadingSymbols}
                        showSearch
                        filterOption={(input, option) => {
                          const value = option?.value as string;
                          return value?.toLowerCase().includes(input.toLowerCase());
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
                </Row>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item
                      name="trading_mode"
                      label={
                        <Space>
                          {t('trading_mode')}
                          <Tooltip title="切换交易模式需要重启Worker才能生效">
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
            ),
          },
          {
            key: 'params',
            label: (
              <span>
                <SlidersOutlined />
                策略参数
              </span>
            ),
            children: (
              <Form form={form} layout="vertical">
                {strategyParams.length > 0 ? (
                  <Card size="small" variant="borderless" style={{ background: '#fafafa' }}>
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
                ) : (
                  <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                    {loadingParams ? (
                      <Spin />
                    ) : (
                      <span>该策略无可编辑参数</span>
                    )}
                  </div>
                )}
              </Form>
            ),
          },
        ]}
      />
    </Modal>
  );
};

export default WorkerEditModal;
