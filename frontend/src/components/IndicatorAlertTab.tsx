/**
 * 指标信号提醒 Tab（P2-07）
 *
 * 在指标编辑器内展示/管理当前指标的信���提醒规则：
 * 规则列表（启停、测试发送、删除）+ 新建规则弹窗。
 * 条件语义与后端 indicators/alerts.py 对齐：gt/lt 比较最新值，cross_up/cross_down 比较最近两根。
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  BellOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  Alert,
  App,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tooltip,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { indicatorApi } from '../api';

interface AlertRule {
  id: number;
  indicator_id: number;
  name: string;
  symbol: string;
  period: string;
  market_type: string;
  crypto_type: string;
  plot_name: string;
  op: string;
  threshold: number;
  channels: string[];
  frequency: number;
  enabled: boolean;
  last_fired_at: string | null;
}

const OP_LABEL_KEYS: Record<string, string> = {
  gt: 'indicator.alertOpGt',
  lt: 'indicator.alertOpLt',
  cross_up: 'indicator.alertOpCrossUp',
  cross_down: 'indicator.alertOpCrossDown',
};

const IndicatorAlertTab: React.FC<{ indicatorId: number }> = ({ indicatorId }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const [rules, setRules] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const loadRules = useCallback(async () => {
    setLoading(true);
    try {
      const data = await indicatorApi.listAlertRules(indicatorId);
      setRules(Array.isArray(data) ? data : []);
    } catch {
      message.error(t('indicator.alertLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [indicatorId, message, t]);

  useEffect(() => {
    if (indicatorId) {
      loadRules();
    }
  }, [indicatorId, loadRules]);

  const handleToggle = async (rule: AlertRule, checked: boolean) => {
    try {
      await indicatorApi.updateAlertRule(rule.id, { enabled: checked });
      message.success(checked ? t('indicator.alertEnabled') : t('indicator.alertDisabled'));
      loadRules();
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    }
  };

  const handleDelete = async (rule: AlertRule) => {
    try {
      await indicatorApi.deleteAlertRule(rule.id);
      message.success(t('indicator.alertDeleted'));
      loadRules();
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    }
  };

  const handleTestSend = async (rule: AlertRule) => {
    try {
      const result = await indicatorApi.testAlertRule(rule.id);
      const evaluation = (result as { evaluation?: { triggered?: boolean } })?.evaluation;
      message.success(
        evaluation?.triggered ? t('indicator.alertTestFired') : t('indicator.alertTestOk'),
      );
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    }
  };

  const handleCreate = async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      // 校验失败：表单项内已展示错误提示，阻断提交即可
      return;
    }
    setSaving(true);
    try {
      await indicatorApi.createAlertRule({
        ...values,
        indicator_id: indicatorId,
        market_type: 'crypto',
        crypto_type: 'spot',
      });
      message.success(t('indicator.alertSaved'));
      setModalOpen(false);
      form.resetFields();
      loadRules();
    } catch {
      message.error(t('indicator.alertSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {
      title: t('indicator.alertName'),
      dataIndex: 'name',
      render: (name: string) => name || '-',
    },
    {
      title: t('indicator.alertCondition'),
      render: (_: unknown, rule: AlertRule) =>
        `${rule.plot_name || t('indicator.alertDefaultPlot')} ${t(OP_LABEL_KEYS[rule.op] ?? rule.op)} ${rule.threshold}`,
    },
    {
      title: t('indicator.alertTarget'),
      render: (_: unknown, rule: AlertRule) => `${rule.symbol} · ${rule.period}`,
    },
    {
      title: t('indicator.alertChannels'),
      dataIndex: 'channels',
      render: (channels: string[]) => (channels || []).join(', '),
    },
    {
      title: t('indicator.alertFrequency'),
      dataIndex: 'frequency',
      render: (frequency: number) => t('indicator.alertFrequencyUnit', { minutes: frequency }),
    },
    {
      title: t('indicator.alertLastFired'),
      dataIndex: 'last_fired_at',
      render: (time: string | null) =>
        time ? new Date(time).toLocaleString() : t('indicator.alertNever'),
    },
    {
      title: t('indicator.alertEnabled'),
      dataIndex: 'enabled',
      render: (enabled: boolean, rule: AlertRule) => (
        <Switch size="small" checked={enabled} onChange={(checked) => handleToggle(rule, checked)} />
      ),
    },
    {
      title: t('indicator.alertActions'),
      key: 'actions',
      width: 140,
      render: (_: unknown, rule: AlertRule) => (
        <Space size="small">
          <Tooltip title={t('indicator.alertTestSend')}>
            <Button size="small" icon={<SendOutlined />} onClick={() => handleTestSend(rule)} />
          </Tooltip>
          <Button size="small" danger onClick={() => handleDelete(rule)}>
            {t('common.delete')}
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="indicator-alert-container">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title={t('indicator.alertsTip')}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button type="primary" icon={<BellOutlined />} onClick={() => setModalOpen(true)}>
          {t('indicator.alertAdd')}
        </Button>
      </div>
      <Table
        size="small"
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rules}
        pagination={false}
        locale={{ emptyText: t('indicator.alertsEmpty') }}
      />

      <Modal
        title={t('indicator.alertAddTitle')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleCreate}
        confirmLoading={saving}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ name: '', symbol: '', period: '1h', op: 'gt', threshold: 0, frequency: 30, channels: ['websocket'] }}
        >
          <Form.Item name="name" label={t('indicator.alertName')}>
            <Input placeholder={t('indicator.alertNamePlaceholder')} maxLength={100} />
          </Form.Item>
          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item
              name="symbol"
              label={t('indicator.alertSymbol')}
              rules={[{ required: true, message: t('indicator.alertSymbolRequired') }]}
              style={{ width: 200 }}
            >
              <Input placeholder="BTCUSDT" maxLength={50} />
            </Form.Item>
            <Form.Item name="period" label={t('indicator.alertPeriod')} style={{ width: 120 }}>
              <Select
                options={['5m', '15m', '30m', '1h', '4h', '1d'].map((p) => ({ value: p, label: p }))}
              />
            </Form.Item>
          </Space>
          <Space size="middle" style={{ display: 'flex' }} align="center">
            <Form.Item name="plot_name" label={t('indicator.alertPlot')} style={{ width: 160 }}>
              <Input maxLength={100} placeholder={t('indicator.alertDefaultPlot')} />
            </Form.Item>
            <Form.Item name="op" label={t('indicator.alertOp')} style={{ width: 130 }}>
              <Select
                options={[
                  { value: 'gt', label: t('indicator.alertOpGt') },
                  { value: 'lt', label: t('indicator.alertOpLt') },
                  { value: 'cross_up', label: t('indicator.alertOpCrossUp') },
                  { value: 'cross_down', label: t('indicator.alertOpCrossDown') },
                ]}
              />
            </Form.Item>
            <Form.Item
              name="threshold"
              label={t('indicator.alertThreshold')}
              style={{ width: 140 }}
            >
              <InputNumber style={{ width: '100%' }} step="any" />
            </Form.Item>
          </Space>
          <Space size="middle" style={{ display: 'flex' }}>
            <Form.Item
              name="channels"
              label={t('indicator.alertChannels')}
              rules={[{ required: true, message: t('indicator.alertChannelsRequired') }]}
            >
              <Select
                mode="multiple"
                style={{ width: 260 }}
                options={['websocket', 'email', 'feishu', 'wecom'].map((c) => ({ value: c, label: c }))}
              />
            </Form.Item>
            <Form.Item
              name="frequency"
              label={t('indicator.alertFrequency')}
              tooltip={t('indicator.alertFrequencyTip')}
              style={{ width: 160 }}
            >
              <InputNumber min={1} max={1440} style={{ width: '100%' }} addonAfter="min" />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
};

export default IndicatorAlertTab;
