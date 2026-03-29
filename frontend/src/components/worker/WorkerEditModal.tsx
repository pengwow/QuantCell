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
  message,
  Tabs,
  Card,
} from 'antd';
import {
  EditOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
  SlidersOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { Worker, UpdateWorkerRequest } from '../../types/worker';
import { useWorkerStore } from '../../store/workerStore';
import { dataApi } from '../../api';

const { Option } = Select;
const { TextArea } = Input;
const { TabPane } = Tabs;

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

// 交易模式
const TRADING_MODES = [
  { value: 'paper', label: '模拟交易' },
  { value: 'live', label: '实盘交易' },
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
  const [form] = Form.useForm();
  const { updateWorker } = useWorkerStore();

  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('basic');
  const [symbolOptions, setSymbolOptions] = useState<any[]>([]);
  const [loadingSymbols, setLoadingSymbols] = useState(false);

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

  // 当worker变化时，设置表单值
  useEffect(() => {
    if (visible && worker) {
      form.setFieldsValue({
        name: worker.name,
        description: worker.description,
        symbols: worker.symbols,
        timeframe: worker.timeframe,
        trading_mode: worker.trading_mode,
        cpu_limit: worker.cpu_limit,
        memory_limit: worker.memory_limit,
        initial_capital: worker.config?.initial_capital || 10000,
        max_position_size: worker.config?.max_position_size || 0.1,
        leverage: worker.config?.leverage || 1,
      });
      // 加载交易对列表
      fetchSymbols();
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
        cpu_limit: values.cpu_limit,
        memory_limit: values.memory_limit,
        config: {
          initial_capital: values.initial_capital,
          max_position_size: values.max_position_size,
          leverage: values.leverage,
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
      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane
          tab={
            <span>
              <SettingOutlined />
              {t('basic_config')}
            </span>
          }
          key="basic"
        >
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
          </Form>
        </TabPane>

        <TabPane
          tab={
            <span>
              <SlidersOutlined />
              {t('resource_config')}
            </span>
          }
          key="resource"
        >
          <Form form={form} layout="vertical">
            <Card title={t('resource_limits')} bordered={false}>
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

            <Card title={t('capital_config')} bordered={false} style={{ marginTop: 16 }}>
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
            </Card>
          </Form>
        </TabPane>
      </Tabs>
    </Modal>
  );
};

export default WorkerEditModal;
